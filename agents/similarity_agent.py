import json
import os
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0,
)

# Load funder database
FUNDERS_PATH = os.path.join(os.path.dirname(__file__), "../data/funders.json")
with open(FUNDERS_PATH, "r") as f:
    FUNDERS_DB = json.load(f)

SIMILARITY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a grant matching expert. Given an NGO proposal and a list of funders,
score each funder's fit with the proposal.

For each funder return:
- funder_id: string
- fit_score: number 0-100
- match_reason: string (1-2 sentences explaining why they match)
- gaps: string (1 sentence on what's missing or misaligned)
- recommendation: string (one specific thing to adjust in the proposal to improve fit)

Return ONLY a JSON array of funder match objects, nothing else."""),
    ("human", """Proposal:
{proposal_json}

Available Funders:
{funders_json}

Return ranked matches from highest to lowest fit score.""")
])

def find_similar_grants(proposal: dict, top_k: int = 5) -> list:
    """
    Takes parsed proposal JSON, scores it against funder database,
    returns top_k matches ranked by fit score.
    """
    chain = SIMILARITY_PROMPT | llm

    response = chain.invoke({
        "proposal_json": json.dumps(proposal, indent=2),
        "funders_json": json.dumps(FUNDERS_DB, indent=2)
    })

    content = response.content.strip()

    # Strip markdown fences if present
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]

    matches = json.loads(content)

    # Sort by fit score descending
    matches = sorted(matches, key=lambda x: x.get("fit_score", 0), reverse=True)

    # Enrich with full funder details from DB
    funder_map = {f["id"]: f for f in FUNDERS_DB}
    enriched = []
    for match in matches[:top_k]:
        funder_detail = funder_map.get(match["funder_id"], {})
        enriched.append({
            **funder_detail,
            **match,
        })

    return enriched