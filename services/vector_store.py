import json
import re
import chromadb
from pydantic import BaseModel, Field
from typing import List, Literal
from sentence_transformers import SentenceTransformer
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from config import USE_GROQ, GROQ_API_KEY, LOCAL_LLM_MODEL

# ── Location boost for grant ranking ─────────────────────────────────────────
# Grants that mention the proposal's geography in their title/description/focus
# get a score bump. This is valid because many grants are geography-restricted
# (e.g. "Los Angeles County only", "California nonprofits", "US-based orgs").

def _location_boost_grant(proposal_geo: list, grant: dict) -> int:
    """
    Returns +15, +8, +4, or 0 based on geographic overlap between
    the proposal's focus and the grant's location signals.
    Only applied when proposal_geo is non-empty and non-global.
    """
    if not proposal_geo:
        return 0

    GLOBAL_TERMS = {"global","international","worldwide","remote","online","national"}
    geo_lower = {g.lower().strip() for g in proposal_geo}
    # Skip boost if proposal is explicitly global
    if geo_lower <= GLOBAL_TERMS:
        return 0

    # Build a searchable string from grant fields
    grant_text = " ".join(filter(None, [
        str(grant.get("title", "")),
        str(grant.get("agency", "")),
        str(grant.get("description", ""))[:500],
        str(grant.get("focus_areas", "")),
    ])).lower()

    for geo_term in geo_lower:
        if geo_term in GLOBAL_TERMS:
            continue
        # Exact phrase match — strong boost
        if geo_term in grant_text:
            return 15
        # State/country abbreviation match (e.g. "CA", "LA")
        if len(geo_term) == 2 and geo_term.upper() in grant_text.upper():
            return 8
        # Partial word match for longer terms (e.g. "california" in "californian")
        if len(geo_term) > 4:
            for word in geo_term.split():
                if word in grant_text and len(word) > 3:
                    return 4

    return 0


CHROMA_PATH = "./chroma_db"
COLLECTION  = "grants"
MODEL_NAME  = "all-MiniLM-L6-v2"

_embedding_model = None
_collection      = None

def _get_resources():
    global _embedding_model, _collection
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(MODEL_NAME)
        client      = chromadb.PersistentClient(path=CHROMA_PATH)
        _collection = client.get_collection(COLLECTION)
    return _embedding_model, _collection


def clean_html(text: str) -> str:
    return re.sub(r'<[^>]+>', ' ', text or '').strip()

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

class ReRankedGrant(BaseModel):
    grant_id: str = Field(description="The exact ID of the grant")
    refined_fit_score: int = Field(description="Score 0-100 based on eligibility/logic, not just keywords")
    match_explanation: str = Field(description="2-3 sentences explaining the logical match")
    fit_level: Literal["strong", "moderate", "weak"]
    application_tip: str = Field(description="One concrete, actionable tip")


class GrantMatchInsight(BaseModel):
    grant_id: str = Field(description="The exact ID of the grant being evaluated")
    match_explanation: str = Field(description="2-3 sentences explaining EXACTLY why this grant matches the proposal's mission or location.")
    fit_level: Literal["strong", "moderate", "weak"] = Field(description="How good of a fit is this grant?")
    application_tip: str = Field(description="One concrete, actionable tip to strengthen the application for this specific funder.")

class ReRankerList(BaseModel):
    rankings: List[ReRankedGrant] = Field(description="Evaluation for all retrieved candidates")

class GrantMatchInsightsList(BaseModel):
    insights: List[GrantMatchInsight] = Field(description="A list containing exactly one insight for every retrieved grant provided in the prompt.")

RAG_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert grant advisor helping NGOs find the best funding matches.
You will be given an NGO proposal and a list of retrieved grants.
For every single grant in the 'Retrieved Grants' list, evaluate the fit, explain the match, and provide an application tip.
Do not skip any grants."""),
    ("user", """NGO Proposal:
{proposal}

Retrieved Grants:
{grants}""")
])

RERANK_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a Senior Grant Consultant. 
Your job is to RE-RANK potential grants based on STRICT ELIGIBILITY and LOGIC.
Keyword matches (Stage 1) are often misleading. You must look for:
- Geographic hard-stops (If the NGO is in LA but the grant is for NY, it's a 'weak' fit).
- Mission alignment (Does the specific activity match the funder's goal?).
- Award size (Is the request realistic for this funder?)."""),
    ("user", """NGO PROPOSAL:
{proposal}

CANDIDATE GRANTS (Top 20 from Vector Search):
{grants}""")
])

def get_llm(USE_GROQ):
    if USE_GROQ:
        return ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=GROQ_API_KEY)
    return ChatOllama(model=LOCAL_LLM_MODEL)

def find_similar_grants(proposal: dict, top_k: int = 5) -> list:
    model, collection = _get_resources()

    with open("data/grants_enriched.json", "r", encoding="utf-8") as f:
        raw = json.load(f)
        grant_list = raw.get("grants", raw) if isinstance(raw, dict) else raw
        all_grants = {str(g["grant_id"]): g for g in grant_list}

    proposal_embedding = model.encode(proposal_to_text(proposal)).tolist()
    results = collection.query(
        query_embeddings=[proposal_embedding],
        n_results=10, 
        include=["metadatas", "distances"]
    )

    initial_candidates = []
    for grant_id, distance, metadata in zip(results["ids"][0], results["distances"][0], results["metadatas"][0]):
        full_grant = all_grants.get(grant_id, {})
        initial_candidates.append({
            "grant_id": grant_id,
            "title": metadata.get("title", ""),
            "agency": metadata.get("agency", ""),
            "description": clean_html(full_grant.get("description", ""))[:300], # Keep context manageable
            "award_ceiling": metadata.get("award_ceiling", 0),
            "vector_score": round((1 - distance) * 100, 1)
        })

    print(f"🧐 Re-ranking 20 candidates using {'Groq' if USE_GROQ else 'Local LLM'} for precision...")
    
    llm = get_llm(USE_GROQ)
    structured_llm = llm.with_structured_output(ReRankerList)
    chain = RERANK_PROMPT | structured_llm

    try:
        result = chain.invoke({
            "proposal": json.dumps(proposal, indent=2),
            "grants": json.dumps(initial_candidates, indent=2)
        })
        
        refined_data = {str(r.grant_id): r for r in result.rankings}
        
    except Exception as e:
        print(f"⚠️ Re-ranking Error: {e}")
        refined_data = {}

    final_ranked_list = []
    for grant in initial_candidates:
        idx = results["ids"][0].index(grant["grant_id"])
        full_metadata = results["metadatas"][0][idx]
        full_grant_source = all_grants.get(str(grant["grant_id"]), {})
        
        llm_insight = refined_data.get(str(grant["grant_id"]))
        
        final_ranked_list.append({
            "grant_id": grant["grant_id"],
            "title": grant["title"],
            "agency": grant["agency"],
            "award_ceiling": grant["award_ceiling"],
            "award_floor": full_metadata.get("award_floor", 0),
            "application_url": full_metadata.get("application_url", ""),
            "close_date": full_metadata.get("close_date", ""),
            "focus_areas": full_metadata.get("focus_areas", ""),
            "contact_email": full_metadata.get("contact_email", ""),
            "description": clean_html(full_grant_source.get("description", "")),
            "eligibility": full_grant_source.get("eligibility", []),
            
            "similarity_score": llm_insight.refined_fit_score if llm_insight else grant["vector_score"],
            "match_explanation": llm_insight.match_explanation if llm_insight else "Keyword match only.",
            "fit_level": llm_insight.fit_level if llm_insight else "unknown",
            "application_tip": llm_insight.application_tip if llm_insight else "Standard review recommended."
        })

    # Apply location boost — add to LLM score then re-sort
    proposal_geo = proposal.get("geographic_focus") or []
    for item in final_ranked_list:
        full_g = all_grants.get(str(item["grant_id"]), {})
        boost  = _location_boost_grant(proposal_geo, full_g)
        item["similarity_score"]   = min(100, item["similarity_score"] + boost)
        item["location_boosted"]   = boost > 0
        item["location_boost_pts"] = boost

    final_ranked_list.sort(key=lambda x: x["similarity_score"], reverse=True)
    
    return final_ranked_list[:top_k]

# ── Agentic topic search ──────────────────────────────────────────────────────

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


def topic_search_grants(query: str, top_k: int = 10) -> list:
    """
    Agentic semantic search by topic/keyword (not a full proposal).
    1. Embed the query string
    2. Retrieve top 20 candidates from ChromaDB  
    3. LLM scores each for topical relevance
    4. Return top_k sorted by relevance score

    This is distinct from find_similar_grants (which takes a full proposal dict).
    Here the input is a plain text query like "affordable housing LA" or "youth education Kenya".
    """
    model, collection = _get_resources()

    with open("data/grants_enriched.json", "r", encoding="utf-8") as f:
        raw = json.load(f)
        grant_list = raw.get("grants", raw) if isinstance(raw, dict) else raw
        all_grants = {str(g["grant_id"]): g for g in grant_list}

    # Embed the query text directly
    query_embedding = model.encode(query).tolist()

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(20, len(all_grants)),
        include=["metadatas", "distances"]
    )

    candidates = []
    for grant_id, distance, metadata in zip(
        results["ids"][0], results["distances"][0], results["metadatas"][0]
    ):
        full_grant = all_grants.get(grant_id, {})
        candidates.append({
            "grant_id":      grant_id,
            "title":         metadata.get("title", ""),
            "agency":        metadata.get("agency", ""),
            "focus_areas":   metadata.get("focus_areas", ""),
            "award_ceiling": metadata.get("award_ceiling", 0),
            "description":   clean_html(full_grant.get("description", ""))[:250],
            "vector_score":  round((1 - distance) * 100, 1),
        })

    # LLM agentic re-ranking for topical relevance
    llm = get_llm(USE_GROQ)
    try:
        resp = llm.invoke(
            TOPIC_SEARCH_PROMPT.format_messages(
                query=query,
                grants=json.dumps(candidates, indent=2)
            )
        )
        content = resp.content.strip()
        if "```" in content:
            import re as _re
            content = _re.sub(r"```json|```", "", content).strip()
        scored = {str(r["grant_id"]): r for r in json.loads(content)}
    except Exception as e:
        print(f"⚠ Topic search LLM error: {e}")
        scored = {}

    # Merge LLM scores with full grant data
    final = []
    for g in candidates:
        full_g = all_grants.get(str(g["grant_id"]), {})
        insight = scored.get(str(g["grant_id"]), {})
        relevance = insight.get("relevance_score", g["vector_score"])

        final.append({
            "grant_id":          g["grant_id"],
            "title":             g["title"],
            "agency":            g["agency"],
            "focus_areas":       g["focus_areas"],
            "award_ceiling":     g["award_ceiling"],
            "award_floor":       full_g.get("award_floor", 0),
            "close_date":        full_g.get("close_date", ""),
            "application_url":   full_g.get("grants_gov_url", ""),
            "description":       clean_html(full_g.get("description", "")),
            "eligibility":       full_g.get("eligibility", []),
            "similarity_score":  relevance,
            "match_explanation": insight.get("match_reason", "Semantic similarity match."),
            "fit_level":         "strong" if relevance >= 70 else "moderate" if relevance >= 45 else "weak",
            "application_tip":   "",
        })

    # Sort by relevance, return top_k
    final.sort(key=lambda x: x["similarity_score"], reverse=True)
    return final[:top_k]