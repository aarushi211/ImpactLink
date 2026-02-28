"""
services/vector_store.py
Vector search + RAG layer.
Retrieves similar grants then uses LLM to reason over them.
"""

import json
import re
import chromadb
from sentence_transformers import SentenceTransformer
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

# ── Config ───────────────────────────────────────────────
CHROMA_PATH = "./chroma_db"
COLLECTION  = "grants"
MODEL_NAME  = "all-MiniLM-L6-v2"
# ────────────────────────────────────────────────────────

# Singletons — load once, reuse across all requests
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


RAG_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert grant advisor helping NGOs find the best funding matches.
You will be given an NGO proposal and a list of retrieved grants.

For each grant, explain:
- Why it matches this proposal (be specific, reference actual proposal content)
- What makes it a strong or weak fit
- One specific tip to strengthen the application for this funder

Return a JSON array where each item has:
- grant_id: string
- match_explanation: string (2-3 sentences, specific to this proposal)
- fit_level: "strong" | "moderate" | "weak"
- application_tip: string (one concrete, actionable tip)

Return ONLY valid JSON, nothing else."""),
    ("user", """NGO Proposal:
{proposal}

Retrieved Grants:
{grants}""")
])


def find_similar_grants(proposal: dict, top_k: int = 5) -> list:
    """
    1. Embed proposal
    2. Retrieve top_k similar grants from ChromaDB
    3. Feed retrieved grants + proposal into LLM (RAG)
    4. Return enriched results with LLM explanations
    """
    model, collection = _get_resources()

    # Load full grant details
    with open("data/grants_enriched.json") as f:
        raw = json.load(f)
        grant_list = raw.get("grants", raw) if isinstance(raw, dict) else raw
        all_grants = {str(g["grant_id"]): g for g in grant_list}

    # Step 1 — Embed proposal and retrieve from ChromaDB
    proposal_embedding = model.encode(proposal_to_text(proposal)).tolist()

    results = collection.query(
        query_embeddings=[proposal_embedding],
        n_results=top_k,
        include=["metadatas", "distances"]
    )

    # Step 2 — Build retrieved grants context for RAG
    retrieved = []
    for grant_id, distance, metadata in zip(
        results["ids"][0],
        results["distances"][0],
        results["metadatas"][0]
    ):
        similarity_score = round((1 - distance) * 100, 1)
        full_grant = all_grants.get(grant_id, {})

        retrieved.append({
            "grant_id":        grant_id,
            "similarity_score": similarity_score,
            "title":           metadata.get("title", ""),
            "agency":          metadata.get("agency", ""),
            "award_floor":     metadata.get("award_floor", 0),
            "award_ceiling":   metadata.get("award_ceiling", 0),
            "application_url": metadata.get("application_url", ""),
            "close_date":      metadata.get("close_date", ""),
            "focus_areas":     metadata.get("focus_areas", ""),
            "contact_email":   metadata.get("contact_email", ""),
            "description":     clean_html(full_grant.get("description", "")),
            "eligibility":     full_grant.get("eligibility", []),
        })

    # Step 3 — RAG: pass proposal + retrieved grants to LLM
    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
    chain = RAG_PROMPT | llm

    response = chain.invoke({
        "proposal": json.dumps(proposal, indent=2),
        "grants": json.dumps(retrieved, indent=2)
    })

    content = response.content.strip()
    if "```" in content:
        content = re.sub(r"```json|```", "", content).strip()

    try:
        rag_insights = {r["grant_id"]: r for r in json.loads(content)}
    except Exception:
        rag_insights = {}

    # Step 4 — Merge vector results with RAG insights
    final = []
    for grant in retrieved:
        insight = rag_insights.get(grant["grant_id"], {})
        final.append({
            **grant,
            "match_explanation": insight.get("match_explanation", ""),
            "fit_level":         insight.get("fit_level", ""),
            "application_tip":   insight.get("application_tip", ""),
        })

    return sorted(final, key=lambda x: x["similarity_score"], reverse=True)