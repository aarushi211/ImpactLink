"""
services/ngo_collab.py
──────────────────────────────────────────────────────────────
Finds NGOs whose mission/activities are most similar to a given
proposal so ImpactLink can surface collaboration opportunities.

Algorithm
─────────
1. Load all collab_open NGO profiles from ngo_profiles.json
2. Embed each profile as text (mission + cause + activities + SDGs
   + geographic_focus) using the same MiniLM model as grant search
3. Embed the incoming proposal the same way
4. Cosine-rank and return top_k with similarity scores
5. LLM pass generates a specific "why collaborate" explanation +
   suggested collaboration type for each match

CollabResult schema
───────────────────
{
  ngo_id, org_name, mission, cause_area, sdgs, location,
  geographic_focus, key_activities, collab_interests,
  website, team_size, founding_year,
  similarity_score,        ← 0-100
  collab_explanation,      ← LLM: why these two orgs should work together
  collab_type,             ← LLM: "Joint proposal" | "Sub-grant" | "Referral" | "Data sharing" | "Capacity building"
  shared_focus,            ← LLM: 1-2 specific overlap areas
}
"""

import json, re
from sentence_transformers import SentenceTransformer
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

MODEL_NAME = "all-MiniLM-L6-v2"

_embedding_model = None

def _get_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(MODEL_NAME)
    return _embedding_model


def _ngo_to_text(ngo: dict) -> str:
    """Convert NGO profile to a single embeddable string."""
    parts = []
    if ngo.get("mission"):         parts.append(f"Mission: {ngo['mission']}")
    if ngo.get("cause_area"):      parts.append(f"Cause: {ngo['cause_area']}")
    if ngo.get("key_activities"):  parts.append(f"Activities: {', '.join(ngo['key_activities'])}")
    if ngo.get("sdgs"):            parts.append(f"SDGs: {', '.join(ngo['sdgs'])}")
    if ngo.get("geographic_focus"):parts.append(f"Geography: {', '.join(ngo['geographic_focus'])}")
    if ngo.get("collab_interests"):parts.append(f"Collab interests: {', '.join(ngo['collab_interests'])}")
    return " | ".join(parts) if parts else ngo.get("org_name", "")


def _proposal_to_text(proposal: dict) -> str:
    parts = []
    if proposal.get("primary_mission"):    parts.append(f"Mission: {proposal['primary_mission']}")
    if proposal.get("cause_area"):         parts.append(f"Cause: {proposal['cause_area']}")
    if proposal.get("key_activities"):     parts.append(f"Activities: {', '.join(proposal['key_activities'])}")
    if proposal.get("sdg_alignment"):      parts.append(f"SDGs: {', '.join(proposal['sdg_alignment'])}")
    if proposal.get("geographic_focus"):   parts.append(f"Geography: {', '.join(proposal['geographic_focus'])}")
    if proposal.get("target_beneficiaries"):parts.append(f"Beneficiaries: {', '.join(proposal['target_beneficiaries'])}")
    return " | ".join(parts) if parts else proposal.get("project_title", "")


COLLAB_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert NGO partnership advisor.
Given one NGO's proposal and a list of similar NGOs, explain why each would be a good collaboration partner.

CRITICAL RULES:
- Return exactly one JSON object per NGO in the input
- Use the EXACT ngo_id from input — never change IDs
- Return ONLY a valid JSON array, nothing else

Each object must have:
- ngo_id: string (copy exactly from input)
- collab_explanation: string (2-3 sentences on WHY these two orgs specifically should collaborate, referencing both orgs' work)
- collab_type: one of "Joint proposal" | "Sub-grant" | "Referral" | "Data sharing" | "Capacity building"
- shared_focus: string (1-2 specific overlapping focus areas, e.g. "Youth education in East Africa")
"""),
    ("user", """Proposal NGO:
{proposal}

Similar NGOs to evaluate:
{ngos}""")
])


def find_similar_ngos(proposal: dict, all_ngos: list, top_k: int = 5) -> list:
    """
    Find top_k NGOs most similar to the given proposal.
    all_ngos: list of stripped NGO profile dicts (collab_open=True)
    Returns list of CollabResult dicts sorted by similarity_score desc.
    """
    if not all_ngos:
        return []

    model = _get_model()

    # Embed proposal
    prop_text = _proposal_to_text(proposal)
    prop_vec  = model.encode(prop_text)

    # Embed all NGOs and score
    scored = []
    for ngo in all_ngos:
        ngo_text = _ngo_to_text(ngo)
        if not ngo_text.strip():
            continue
        ngo_vec = model.encode(ngo_text)

        # Cosine similarity
        dot   = float(sum(a * b for a, b in zip(prop_vec, ngo_vec)))
        mag_p = float(sum(a * a for a in prop_vec) ** 0.5)
        mag_n = float(sum(a * a for a in ngo_vec) ** 0.5)
        cos   = dot / (mag_p * mag_n) if mag_p and mag_n else 0.0
        score = round(max(0.0, min(1.0, (cos + 1) / 2)) * 100, 1)

        scored.append({**ngo, "_score": score})

    # Take top_k
    top = sorted(scored, key=lambda x: x["_score"], reverse=True)[:top_k]

    # LLM pass — generate collaboration explanations
    llm   = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.2)
    chain = COLLAB_PROMPT | llm

    ngo_summary = [
        {
            "ngo_id":   n["id"],
            "org_name": n.get("org_name", ""),
            "mission":  n.get("mission", ""),
            "cause":    n.get("cause_area", ""),
            "activities": n.get("key_activities", []),
            "geography":  n.get("geographic_focus", []),
        }
        for n in top
    ]

    try:
        resp    = chain.invoke({
            "proposal": json.dumps({
                "org_name":    proposal.get("organization_name", ""),
                "mission":     proposal.get("primary_mission", ""),
                "cause":       proposal.get("cause_area", ""),
                "activities":  proposal.get("key_activities", []),
                "geography":   proposal.get("geographic_focus", []),
            }),
            "ngos": json.dumps(ngo_summary, indent=2),
        })
        content = resp.content.strip()
        if "```" in content:
            content = re.sub(r"```json|```", "", content).strip()
        insights = {r["ngo_id"]: r for r in json.loads(content)}
    except Exception:
        insights = {}

    # Merge
    results = []
    for ngo in top:
        ins = insights.get(ngo["id"], {})
        results.append({
            "ngo_id":             ngo["id"],
            "org_name":           ngo.get("org_name", ""),
            "mission":            ngo.get("mission", ""),
            "cause_area":         ngo.get("cause_area", ""),
            "sdgs":               ngo.get("sdgs", []),
            "location":           ngo.get("location", ""),
            "geographic_focus":   ngo.get("geographic_focus", []),
            "key_activities":     ngo.get("key_activities", []),
            "collab_interests":   ngo.get("collab_interests", []),
            "website":            ngo.get("website", ""),
            "team_size":          ngo.get("team_size", ""),
            "founding_year":      ngo.get("founding_year"),
            "similarity_score":   ngo["_score"],
            "collab_explanation": ins.get("collab_explanation", "Strong mission alignment detected."),
            "collab_type":        ins.get("collab_type", "Joint proposal"),
            "shared_focus":       ins.get("shared_focus", ""),
        })

    return results