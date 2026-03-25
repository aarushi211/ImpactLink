"""
services/ngo_collab.py — fixed: no module-level LLM singleton
"""

import os
import json
import re
import random
from sentence_transformers import SentenceTransformer
from utils.llm import RotatingGroq
from langchain_core.prompts import ChatPromptTemplate

MODEL_NAME = "all-MiniLM-L6-v2"

_RAW_KEYS = os.getenv("GROQ_API_KEY", "")
GROQ_KEYS = [k.strip() for k in _RAW_KEYS.split(",") if k.strip()]

_embedding_model = None


def _get_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(MODEL_NAME)
    return _embedding_model


def _get_llm(temperature: float = 0.2) -> RotatingGroq:
    from config import GROQ_API_KEY
    key = random.choice(GROQ_KEYS) if GROQ_KEYS else GROQ_API_KEY
    return RotatingGroq(model="llama-3.3-70b-versatile", temperature=temperature, groq_api_key=key)


# ── Location helpers ──────────────────────────────────────────────────────────

REGION_MAP = {
    "west_africa":     ["nigeria","ghana","senegal","côte d'ivoire","ivory coast","mali","burkina","togo","benin","guinea","liberia","sierra leone","gambia","cabo verde"],
    "east_africa":     ["kenya","tanzania","uganda","ethiopia","rwanda","burundi","somalia","eritrea","djibouti","south sudan"],
    "southern_africa": ["south africa","zimbabwe","zambia","mozambique","malawi","namibia","botswana","lesotho","eswatini"],
    "north_africa":    ["egypt","morocco","algeria","tunisia","libya","sudan"],
    "south_asia":      ["india","pakistan","bangladesh","nepal","sri lanka","bhutan","maldives","afghanistan"],
    "southeast_asia":  ["philippines","indonesia","vietnam","thailand","cambodia","myanmar","laos","malaysia","singapore","timor"],
    "central_america": ["guatemala","honduras","el salvador","nicaragua","costa rica","panama","belize"],
    "south_america":   ["brazil","colombia","peru","chile","argentina","bolivia","ecuador","venezuela","paraguay","uruguay"],
    "middle_east":     ["jordan","lebanon","palestine","israel","iraq","syria","yemen","oman","kuwait","bahrain","qatar","uae","saudi"],
    "central_asia":    ["kazakhstan","uzbekistan","kyrgyzstan","tajikistan","turkmenistan"],
    "eastern_europe":  ["ukraine","poland","romania","bulgaria","serbia","croatia","czech","slovak","hungary","moldova"],
    "la_us":           ["los angeles","la","southern california","so cal","socal"],
    "ny_us":           ["new york","nyc","brooklyn","bronx","manhattan","queens"],
}


def _geo_tokens(geo_list: list) -> set:
    tokens = set()
    for g in (geo_list or []):
        for word in g.lower().replace(",", " ").replace("/", " ").split():
            tokens.add(word.strip())
    return tokens


def _location_boost(proposal_geo: list, ngo_geo: list, ngo_location: str = "") -> tuple[int, str]:
    if not proposal_geo and not ngo_location:
        return 0, "none"

    prop_tokens = _geo_tokens(proposal_geo)
    ngo_tokens  = _geo_tokens(ngo_geo)
    if ngo_location:
        for word in ngo_location.lower().replace(",", " ").split():
            ngo_tokens.add(word.strip())

    if not prop_tokens or not ngo_tokens:
        return 0, "none"

    if prop_tokens & ngo_tokens:
        generic      = {"global","international","worldwide","remote","online","virtual","national"}
        real_overlap = (prop_tokens & ngo_tokens) - generic
        return (20, "exact") if real_overlap else (5, "regional")

    def _regions_for(tokens):
        return {region for region, keywords in REGION_MAP.items() if any(kw in tokens for kw in keywords)}

    if _regions_for(prop_tokens) & _regions_for(ngo_tokens):
        return 10, "regional"

    common = prop_tokens & ngo_tokens
    if common - {"city","area","region","province","county","district"}:
        return 8, "national"

    return -5, "none"


def _ngo_to_text(ngo: dict) -> str:
    parts = []
    if ngo.get("mission"):          parts.append(f"Mission: {ngo['mission']}")
    if ngo.get("cause_area"):       parts.append(f"Cause: {ngo['cause_area']}")
    if ngo.get("key_activities"):   parts.append(f"Activities: {', '.join(ngo['key_activities'])}")
    if ngo.get("sdgs"):             parts.append(f"SDGs: {', '.join(ngo['sdgs'])}")
    if ngo.get("geographic_focus"): parts.append(f"Geography: {', '.join(ngo['geographic_focus'])}")
    if ngo.get("collab_interests"): parts.append(f"Collab interests: {', '.join(ngo['collab_interests'])}")
    return " | ".join(parts) if parts else ngo.get("org_name", "")


def _proposal_to_text(proposal: dict) -> str:
    parts = []
    if proposal.get("primary_mission"):      parts.append(f"Mission: {proposal['primary_mission']}")
    if proposal.get("cause_area"):           parts.append(f"Cause: {proposal['cause_area']}")
    if proposal.get("key_activities"):       parts.append(f"Activities: {', '.join(proposal['key_activities'])}")
    if proposal.get("sdg_alignment"):        parts.append(f"SDGs: {', '.join(proposal['sdg_alignment'])}")
    if proposal.get("geographic_focus"):     parts.append(f"Geography: {', '.join(proposal['geographic_focus'])}")
    if proposal.get("target_beneficiaries"): parts.append(f"Beneficiaries: {', '.join(proposal['target_beneficiaries'])}")
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
- collab_explanation: string (2-3 sentences on WHY these two orgs specifically should collaborate, referencing both orgs' work AND their geographic proximity if relevant)
- collab_type: one of "Joint proposal" | "Sub-grant" | "Referral" | "Data sharing" | "Capacity building"
- shared_focus: string (1-2 specific overlapping focus areas, e.g. "Youth education in East Africa")
"""),
    ("user", """Proposal NGO:
{proposal}

Similar NGOs to evaluate:
{ngos}""")
])


def find_similar_ngos(
    proposal: dict,
    all_ngos: list,
    top_k: int = 5,
    ngo_profile: dict = None,
) -> list:
    if not all_ngos:
        return []

    model    = _get_model()
    prop_geo = list(proposal.get("geographic_focus") or [])
    if not prop_geo and ngo_profile:
        prof_geo = ngo_profile.get("geographic_focus") or []
        prop_geo = list(prof_geo) if prof_geo else (
            [ngo_profile["location"]] if ngo_profile.get("location") else []
        )

    prop_vec = model.encode(_proposal_to_text(proposal))

    scored = []
    for ngo in all_ngos:
        ngo_text = _ngo_to_text(ngo)
        if not ngo_text.strip():
            continue
        ngo_vec = model.encode(ngo_text)

        dot   = float(sum(a * b for a, b in zip(prop_vec, ngo_vec)))
        mag_p = float(sum(a * a for a in prop_vec) ** 0.5)
        mag_n = float(sum(a * a for a in ngo_vec) ** 0.5)
        cos   = dot / (mag_p * mag_n) if mag_p and mag_n else 0.0
        cosine_score = round(max(0.0, min(1.0, (cos + 1) / 2)) * 100, 1)

        boost, match_level = _location_boost(prop_geo, ngo.get("geographic_focus") or [], ngo.get("location", ""))
        final_score        = round(min(100.0, max(0.0, cosine_score + boost)), 1)

        scored.append({**ngo, "_cosine_score": cosine_score, "_location_boost": boost,
                       "_location_match": match_level, "_score": final_score})

    top = sorted(scored, key=lambda x: x["_score"], reverse=True)[:top_k]

    ngo_summary = [
        {"ngo_id": n["id"], "org_name": n.get("org_name", ""), "mission": n.get("mission", ""),
         "cause": n.get("cause_area", ""), "activities": n.get("key_activities", []),
         "geography": n.get("geographic_focus", []), "location": n.get("location", "")}
        for n in top
    ]

    try:
        # Fresh LLM — plain invoke (no with_structured_output), still needs valid key
        llm      = _get_llm(temperature=0.2)
        chain    = COLLAB_PROMPT | llm
        resp     = chain.invoke({
            "proposal": json.dumps({
                "org_name":   proposal.get("organization_name", ""),
                "mission":    proposal.get("primary_mission", ""),
                "cause":      proposal.get("cause_area", ""),
                "activities": proposal.get("key_activities", []),
                "geography":  prop_geo,
            }),
            "ngos": json.dumps(ngo_summary, indent=2),
        })
        content  = resp.content.strip()
        if "```" in content:
            content = re.sub(r"```json|```", "", content).strip()
        insights = {r["ngo_id"]: r for r in json.loads(content)}
    except Exception:
        insights = {}

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
            "location_match":     ngo["_location_match"],
            "location_boost":     ngo["_location_boost"],
            "collab_explanation": ins.get("collab_explanation", "Strong mission alignment detected."),
            "collab_type":        ins.get("collab_type", "Joint proposal"),
            "shared_focus":       ins.get("shared_focus", ""),
        })

    return results