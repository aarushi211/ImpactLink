"""
collaboration_agent.py

Finds NGO collaborators by reverse-searching the proposals collection
using the grants returned by your similarity agent.

Drop this file next to similarity_agent.py and call it like:

    from similarity_agent import find_similar_grants
    from collaboration_agent import find_collaborators, add_proposal_to_db

Usage:
    # After your existing similarity search:
    grants  = find_similar_grants(proposal)
    collabs = find_collaborators(proposal, grants, current_org_id="org-042")
"""

import chromadb
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel, Field
from typing import List, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from config import USE_GROQ, GROQ_API_KEY, LOCAL_LLM_MODEL

CHROMA_PATH  = "./chroma_db"
MODEL_NAME   = "all-MiniLM-L6-v2"
TOP_ORGS     = 5   # collaborators to return per grant

# Singletons
_model       = None
_grants_col  = None
_proposals_col = None


def _get_resources():
    global _model, _grants_col, _proposals_col
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        _grants_col    = client.get_collection("grants")
        _proposals_col = client.get_collection("proposals")
    return _model, _grants_col, _proposals_col


# ── Pydantic schema for LLM collaboration summary ────────────────────────────

class CollabInsight(BaseModel):
    org_id: str = Field(description="The org_id of the potential collaborator")
    why_collaborate: str = Field(description="2 sentences on why these two orgs should collaborate on this grant")
    collaboration_angle: str = Field(description="One concrete way they could divide the work or complement each other")


class CollabInsightList(BaseModel):
    insights: List[CollabInsight]


COLLAB_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert in nonprofit collaboration and grant strategy.
Given a user's proposal and a list of other NGOs also interested in the same grant,
explain why each pair should collaborate and how they could divide the work.
Return one insight per NGO."""),
    ("human", """User Proposal:
{user_proposal}

Grant they are both targeting:
{grant_title}

Potential Collaborator NGOs:
{collaborator_ngos}

Return one CollabInsight per NGO.""")
])


def _get_llm():
    if USE_GROQ:
        return ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=GROQ_API_KEY, temperature=0)
    return ChatOllama(model=LOCAL_LLM_MODEL, temperature=0)


# ── Core functions ────────────────────────────────────────────────────────────

def add_proposal_to_db(
    org_id: str,
    org_name: str,
    proposal_text: str,
    location: str = "",
    contact_email: str = "",
    website: str = "",
    focus_areas: str = "",
):
    """
    Call this when a NEW user submits a proposal through your dashboard.
    Embeds and stores their proposal in the proposals collection.
    """
    model, _, proposals_col = _get_resources()
    embedding = model.encode(proposal_text).tolist()

    # Upsert so re-submissions update rather than error
    proposals_col.upsert(
        ids=[org_id],
        embeddings=[embedding],
        documents=[proposal_text],
        metadatas=[{
            "org_name":      org_name,
            "location":      location,
            "contact_email": contact_email,
            "website":       website,
            "focus_areas":   focus_areas,
        }]
    )
    print(f"✅ Stored proposal for {org_name} (id: {org_id})")


def find_collaborators(
    user_proposal: dict,
    similar_grants: list,
    current_org_id: Optional[str] = None,
    top_k_orgs: int = TOP_ORGS,
    min_similarity: float = 0.3,
) -> list:
    """
    Given the output of find_similar_grants(), find other NGOs
    whose proposals are closest to each recommended grant.

    Args:
        user_proposal:   The same proposal dict you passed to find_similar_grants()
        similar_grants:  The return value of find_similar_grants()
        current_org_id:  Exclude the current user's own org from results
        top_k_orgs:      How many collaborators to return per grant
        min_similarity:  Minimum cosine similarity (0-1) to include a match

    Returns:
        List of grants, each with a 'collaborators' key added.
    """
    model, grants_col, proposals_col = _get_resources()
    llm = _get_llm()
    structured_llm = llm.with_structured_output(CollabInsightList)
    chain = COLLAB_PROMPT | structured_llm

    results = []

    for grant in similar_grants:
        grant_id    = str(grant.get("grant_id", ""))
        grant_title = grant.get("title", grant_id)

        # ── Step 1: Get the grant's embedding from ChromaDB ───────────────────
        try:
            grant_data = grants_col.get(ids=[grant_id], include=["embeddings"])
            grant_embedding = grant_data["embeddings"][0]
        except Exception:
            # Grant not in collection — skip
            results.append({**grant, "collaborators": []})
            continue

        # ── Step 2: Find proposals closest to this grant ─────────────────────
        where_filter = {"org_id": {"$ne": current_org_id}} if current_org_id else None

        query_kwargs = {
            "query_embeddings": [grant_embedding],
            "n_results":        min(top_k_orgs + 1, 15),  # fetch extra to filter
            "include":          ["metadatas", "distances", "documents"],
        }
        if where_filter:
            query_kwargs["where"] = where_filter

        raw = proposals_col.query(**query_kwargs)

        # ── Step 3: Filter by min similarity and exclude self ─────────────────
        candidate_orgs = []
        for org_id, distance, metadata, doc in zip(
            raw["ids"][0],
            raw["distances"][0],
            raw["metadatas"][0],
            raw["documents"][0],
        ):
            if current_org_id and org_id == current_org_id:
                continue
            similarity = round(1 - distance, 3)
            if similarity < min_similarity:
                continue
            candidate_orgs.append({
                "org_id":        org_id,
                "similarity":    similarity,
                "proposal_text": doc,
                **metadata,
            })

        candidate_orgs = candidate_orgs[:top_k_orgs]

        if not candidate_orgs:
            results.append({**grant, "collaborators": []})
            continue

        # ── Step 4: LLM collaboration insights ───────────────────────────────
        import json
        slim_orgs = [
            {
                "org_id":      o["org_id"],
                "org_name":    o.get("org_name", ""),
                "location":    o.get("location", ""),
                "focus_areas": o.get("focus_areas", ""),
                "proposal_snippet": o["proposal_text"][:400],
            }
            for o in candidate_orgs
        ]

        try:
            insight_result = chain.invoke({
                "user_proposal":    json.dumps(user_proposal, indent=2),
                "grant_title":      grant_title,
                "collaborator_ngos": json.dumps(slim_orgs, indent=2),
            })
            insight_map = {i.org_id: i for i in insight_result.insights}
        except Exception as e:
            print(f"⚠️  Collab LLM error for grant {grant_id}: {e}")
            insight_map = {}

        # ── Step 5: Merge similarity scores + LLM insights ───────────────────
        collaborators = []
        for org in candidate_orgs:
            insight = insight_map.get(org["org_id"])
            collaborators.append({
                "org_id":               org["org_id"],
                "org_name":             org.get("org_name", ""),
                "location":             org.get("location", ""),
                "focus_areas":          org.get("focus_areas", ""),
                "contact_email":        org.get("contact_email", ""),
                "website":              org.get("website", ""),
                "similarity_score":     org["similarity"],
                "why_collaborate":      insight.why_collaborate if insight else "Mission overlap detected.",
                "collaboration_angle":  insight.collaboration_angle if insight else "Review shared focus areas.",
            })

        # Sort by similarity descending
        collaborators.sort(key=lambda x: x["similarity_score"], reverse=True)
        results.append({**grant, "collaborators": collaborators})

    return results