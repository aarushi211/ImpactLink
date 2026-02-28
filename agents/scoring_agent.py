import json
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0,
)

SCORING_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert grant evaluator with 20 years of experience reviewing NGO proposals.
You understand what funders look for and what makes proposals succeed or fail.

Score the proposal on the following dimensions (0-100 each):

1. clarity_score: How clearly are goals and activities defined?
2. impact_score: Is the expected impact measurable and realistic?
3. budget_score: Does the budget seem realistic for the locality and activities?
4. locality_alignment: Is the geographic focus clear and appropriate?
5. beneficiary_definition: Are target beneficiaries specific and well-defined?
6. overall_score: Weighted average of above scores

Also provide:
- strengths: list of 3 things the proposal does well
- weaknesses: list of 3 things that could get it rejected
- recommendations: list of 3 specific improvements before submitting
- funder_readiness: "strong" | "moderate" | "needs_work"

Return ONLY valid JSON, nothing else.

FUTURE SCOPE NOTE: In future versions, this agent will compare against a database 
of historically successful grants to give data-driven scoring."""),
    ("human", """Score this NGO proposal:

{proposal_json}""")
])

def score_proposal(proposal: dict) -> dict:
    """
    Takes the parsed proposal JSON and returns a scoring analysis.
    Single LLM call for now — future scope: compare against historical grants DB.
    """
    chain = SCORING_PROMPT | llm
    
    response = chain.invoke({
        "proposal_json": json.dumps(proposal, indent=2)
    })

    content = response.content.strip()

    # Strip markdown fences if present
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]

    scored = json.loads(content)
    scored["agent"] = "scoring_agent_v1"
    scored["note"] = "Single LLM evaluation. Future: compared against historical successful grants."

    return scored