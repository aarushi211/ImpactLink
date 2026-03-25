"""
services/vector_store.py

Grant similarity search using PostgreSQL + pgvector.
Replaces ChromaDB — all vectors live in the same Postgres instance
as the rest of the app, so there is no stale local folder to manage.

Schema (created by load_vectors.py):
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE TABLE IF NOT EXISTS grants (
        grant_id        TEXT PRIMARY KEY,
        title           TEXT,
        agency          TEXT,
        award_floor     INT,
        award_ceiling   INT,
        application_url TEXT,
        portal_url      TEXT,
        close_date      TEXT,
        focus_areas     TEXT,
        contact_email   TEXT,
        contact_name    TEXT,
        funding_method  TEXT,
        estimated_total TEXT,
        description     TEXT,
        eligibility     JSONB,
        document        TEXT,          -- full text used for embedding
        embedding       vector(384)    -- all-MiniLM-L6-v2 dims
    );
    CREATE INDEX ON grants USING hnsw (embedding vector_cosine_ops);
"""

import os
import json
import re
import time
import random
import logging
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from pydantic import BaseModel, Field
from typing import List, Literal
from sentence_transformers import SentenceTransformer
from utils.llm import RotatingGroq
from langchain_core.prompts import ChatPromptTemplate
from config import USE_GROQ, GROQ_API_KEY

log = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"
DB_URL     = os.getenv("DATABASE_URL")
if not DB_URL:
    raise ValueError("DATABASE_URL environment variable is required.")

# Parse keys once at module level (same as RotatingGroq does)
_RAW_KEYS = os.getenv("GROQ_API_KEY", "")
GROQ_KEYS = [k.strip() for k in _RAW_KEYS.split(",") if k.strip()]

_pool: ConnectionPool | None = None
_embedding_model = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=DB_URL,
            max_size=5,
            kwargs={"autocommit": True, "prepare_threshold": None},  # None = disable prepared statements (required for PgBouncer/Supabase)
        )
    return _pool


def _get_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(
            MODEL_NAME,
            cache_folder=os.getenv("SENTENCE_TRANSFORMERS_HOME", "/app/.cache"),
        )
    return _embedding_model


def _get_llm() -> RotatingGroq:
    """
    Always constructs a fresh RotatingGroq with a pre-selected valid key.

    Why: with_structured_output() initialises the underlying Groq client
    at chain-build time, BEFORE _generate() is ever called.  If we rely
    solely on the key rotation inside _generate/_agenerate, the client is
    created with whatever stale/empty key was set on the instance, causing
    a 401 before a single token is produced.

    Passing the key explicitly at construction time guarantees the Groq
    client is initialised with a real key on every call.
    """
    key = random.choice(GROQ_KEYS) if GROQ_KEYS else GROQ_API_KEY
    log.info("🔄 Using Groq Key: %s...", str(key)[:7])
    return RotatingGroq(
        model="llama-3.3-70b-versatile",
        groq_api_key=key,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def proposal_to_text(proposal: dict) -> str:
    return f"""
    Title: {proposal.get('project_title', '')}
    Mission: {proposal.get('primary_mission', '')}
    Beneficiaries: {', '.join(proposal.get('target_beneficiaries', []))}
    Geography: {', '.join(proposal.get('geographic_focus', []))}
    Activities: {', '.join(proposal.get('key_activities', []))}
    SDGs: {', '.join(proposal.get('sdg_alignment', []))}
    Cause Area: {proposal.get('cause_area', '')}
    """.strip()


def _location_boost_grant(proposal_geo: list, grant: dict) -> int:
    if not proposal_geo:
        return 0
    GLOBAL_TERMS = {"global", "international", "worldwide", "remote", "online", "national"}
    geo_lower = {g.lower().strip() for g in proposal_geo}
    if geo_lower <= GLOBAL_TERMS:
        return 0
    grant_text = " ".join(filter(None, [
        str(grant.get("title", "")),
        str(grant.get("agency", "")),
        str(grant.get("description", ""))[:500],
        str(grant.get("focus_areas", "")),
    ])).lower()
    for geo_term in geo_lower:
        if geo_term in GLOBAL_TERMS:
            continue
        if geo_term in grant_text:
            return 15
        if len(geo_term) == 2 and geo_term.upper() in grant_text.upper():
            return 8
        if len(geo_term) > 4:
            for word in geo_term.split():
                if word in grant_text and len(word) > 3:
                    return 4
    return 0


def _vector_search(embedding: list, n_results: int) -> list[dict]:
    """Run cosine ANN search — returns rows ordered by similarity desc."""
    pool = _get_pool()
    vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT
                    grant_id, title, agency, award_floor, award_ceiling,
                    application_url, portal_url, close_date, focus_areas,
                    contact_email, contact_name, funding_method, estimated_total,
                    description, eligibility,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM grants
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, (vec_str, vec_str, n_results))
            return cur.fetchall()


# ── Pydantic models ───────────────────────────────────────────────────────────

class ReRankedGrant(BaseModel):
    grant_id: str = Field(description="The exact ID of the grant")
    refined_fit_score: int = Field(description="Score 0-100 based on eligibility/logic, not just keywords")
    match_explanation: str = Field(description="2-3 sentences explaining the logical match")
    fit_level: Literal["strong", "moderate", "weak"]
    application_tip: str = Field(description="One concrete, actionable tip")


class GrantMatchInsight(BaseModel):
    grant_id: str = Field(description="The exact ID of the grant being evaluated")
    match_explanation: str = Field(description="2-3 sentences explaining EXACTLY why this grant matches.")
    fit_level: Literal["strong", "moderate", "weak"] = Field(description="How good of a fit is this grant?")
    application_tip: str = Field(description="One concrete, actionable tip to strengthen the application.")


class ReRankerList(BaseModel):
    rankings: List[ReRankedGrant] = Field(description="Evaluation for all retrieved candidates")


class GrantMatchInsightsList(BaseModel):
    insights: List[GrantMatchInsight] = Field(description="One insight per retrieved grant.")


# ── LLM prompts ───────────────────────────────────────────────────────────────

RERANK_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a Senior Grant Consultant.
Your job is to RE-RANK potential grants based on STRICT ELIGIBILITY and LOGIC.
Keyword matches (Stage 1) are often misleading. You must look for:
- Geographic hard-stops (If the NGO is in LA but the grant is for NY, it's a 'weak' fit).
- Mission alignment (Does the specific activity match the funder's goal?).
- Award size (Is the request realistic for this funder?)."""),
    ("user", """NGO PROPOSAL:
{proposal}

CANDIDATE GRANTS (Top candidates from Vector Search):
{grants}""")
])

TOPIC_SEARCH_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a grant advisor. A user typed a search topic to find relevant grants.
Your job: evaluate each retrieved grant's relevance to the topic and explain the connection.

RULES:
- Return ONLY a valid JSON array, nothing else
- One object per grant in the input, in any order
- Each object: {{ "grant_id": "...", "relevance_score": 0-100, "match_reason": "1 sentence" }}
- relevance_score: 90-100 = directly on-topic, 60-89 = related, 30-59 = tangential, <30 = not relevant
- Be strict — if a grant is clearly off-topic, score it low"""),
    ("user", """User search topic: "{query}"

Retrieved grants to evaluate:
{grants}

Return JSON array now:""")
])


# ── Public API ────────────────────────────────────────────────────────────────

def find_similar_grants(proposal: dict, top_k: int = 5) -> list:
    """
    Full proposal → vector search → LLM re-rank → top_k results.
    Replaces the ChromaDB-backed version; no local file dependency.
    """
    model = _get_model()
    proposal_embedding = model.encode(proposal_to_text(proposal)).tolist()

    rows = _vector_search(proposal_embedding, n_results=20)
    if not rows:
        log.warning("find_similar_grants: no rows returned from pgvector")
        return []

    initial_candidates = []
    for row in rows:
        initial_candidates.append({
            "grant_id":      row["grant_id"],
            "title":         row["title"] or "",
            "agency":        row["agency"] or "",
            "description":   clean_html(row["description"] or "")[:300],
            "award_ceiling": row["award_ceiling"] or 0,
            "vector_score":  round(float(row["similarity"]) * 100, 1),
        })

    # ── LLM re-rank with retry + key rotation per attempt ────────────────────
    log.info("Re-ranking %d candidates with LLM", len(initial_candidates))
    refined_data: dict = {}

    for attempt in range(3):
        try:
            # Fresh instance each attempt — guarantees with_structured_output()
            # initialises the Groq client with a valid, freshly-rotated key.
            llm = _get_llm()
            structured_llm = llm.with_structured_output(ReRankerList)
            chain = RERANK_PROMPT | structured_llm
            result = chain.invoke({
                "proposal": json.dumps(proposal, indent=2),
                "grants":   json.dumps(initial_candidates, indent=2),
            })
            refined_data = {str(r.grant_id): r for r in result.rankings}
            break  # success — exit retry loop
        except Exception as e:
            log.warning("Re-rank attempt %d/3 failed: %s", attempt + 1, e)
            if attempt < 2:
                time.sleep(1.5 ** attempt)  # 1 s, then 1.5 s back-off
            else:
                log.warning("All re-rank attempts failed — using vector scores only")
    # ─────────────────────────────────────────────────────────────────────────

    proposal_geo = proposal.get("geographic_focus") or []
    final = []
    for grant in initial_candidates:
        llm_insight = refined_data.get(str(grant["grant_id"]))
        row = next((r for r in rows if r["grant_id"] == grant["grant_id"]), {})

        score = llm_insight.refined_fit_score if llm_insight else grant["vector_score"]
        boost = _location_boost_grant(proposal_geo, dict(row))
        score = min(100, score + boost)

        eligibility = row.get("eligibility") or []
        if isinstance(eligibility, str):
            try:
                eligibility = json.loads(eligibility)
            except Exception:
                eligibility = []

        final.append({
            "grant_id":           grant["grant_id"],
            "title":              grant["title"],
            "agency":             grant["agency"],
            "award_ceiling":      row.get("award_ceiling") or 0,
            "award_floor":        row.get("award_floor") or 0,
            "application_url":    row.get("application_url") or "",
            "close_date":         row.get("close_date") or "",
            "focus_areas":        row.get("focus_areas") or "",
            "contact_email":      row.get("contact_email") or "",
            "description":        clean_html(row.get("description") or ""),
            "eligibility":        eligibility,
            "similarity_score":   score,
            "match_explanation":  llm_insight.match_explanation if llm_insight else "Semantic similarity match.",
            "fit_level":          llm_insight.fit_level if llm_insight else "unknown",
            "application_tip":    llm_insight.application_tip if llm_insight else "Standard review recommended.",
            "location_boosted":   boost > 0,
            "location_boost_pts": boost,
        })

    final.sort(key=lambda x: x["similarity_score"], reverse=True)
    return final[:top_k]


def topic_search_grants(query: str, top_k: int = 10) -> list:
    """
    Plain-text query → vector search → LLM topical relevance scoring → top_k.
    """
    model = _get_model()
    query_embedding = model.encode(query).tolist()

    rows = _vector_search(query_embedding, n_results=20)
    if not rows:
        return []

    candidates = [{
        "grant_id":      row["grant_id"],
        "title":         row["title"] or "",
        "agency":        row["agency"] or "",
        "focus_areas":   row.get("focus_areas") or "",
        "award_ceiling": row.get("award_ceiling") or 0,
        "description":   clean_html(row.get("description") or "")[:250],
        "vector_score":  round(float(row["similarity"]) * 100, 1),
    } for row in rows]

    # ── LLM topic scoring with retry + key rotation per attempt ──────────────
    scored: dict = {}

    for attempt in range(3):
        try:
            llm = _get_llm()  # fresh instance + key per attempt
            resp = llm.invoke(
                TOPIC_SEARCH_PROMPT.format_messages(
                    query=query,
                    grants=json.dumps(candidates, indent=2),
                )
            )
            content = resp.content.strip()
            if "```" in content:
                content = re.sub(r"```json|```", "", content).strip()
            scored = {str(r["grant_id"]): r for r in json.loads(content)}
            break  # success
        except Exception as e:
            log.warning("Topic search LLM attempt %d/3 failed: %s", attempt + 1, e)
            if attempt < 2:
                time.sleep(1.5 ** attempt)
            else:
                log.warning("All topic search LLM attempts failed — using vector scores only")
    # ─────────────────────────────────────────────────────────────────────────

    final = []
    for g in candidates:
        row = next((r for r in rows if r["grant_id"] == g["grant_id"]), {})
        insight = scored.get(str(g["grant_id"]), {})
        relevance = insight.get("relevance_score", g["vector_score"])

        eligibility = row.get("eligibility") or []
        if isinstance(eligibility, str):
            try:
                eligibility = json.loads(eligibility)
            except Exception:
                eligibility = []

        final.append({
            "grant_id":          g["grant_id"],
            "title":             g["title"],
            "agency":            g["agency"],
            "focus_areas":       g["focus_areas"],
            "award_ceiling":     g.get("award_ceiling") or 0,
            "award_floor":       row.get("award_floor") or 0,
            "close_date":        row.get("close_date") or "",
            "application_url":   row.get("application_url") or row.get("portal_url") or "",
            "description":       clean_html(row.get("description") or ""),
            "eligibility":       eligibility,
            "similarity_score":  relevance,
            "match_explanation": insight.get("match_reason", "Semantic similarity match."),
            "fit_level":         "strong" if relevance >= 70 else "moderate" if relevance >= 45 else "weak",
            "application_tip":   "",
        })

    final.sort(key=lambda x: x["similarity_score"], reverse=True)
    return final[:top_k]