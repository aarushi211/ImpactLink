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

When a target grant is provided, score the proposal SPECIFICALLY for that funder —
how well has the proposal been tailored to this grant's priorities, language, and requirements?
A generic proposal scores lower even if it is well-written.

Score on the following dimensions (0-100 each):

1. clarity_score: How clearly are goals and activities defined?
2. impact_score: Is the expected impact measurable and realistic?
3. budget_score: Does the budget seem realistic for the locality and activities?
4. locality_alignment: Is the geographic focus appropriate for this funder?
5. beneficiary_definition: Are target beneficiaries specific and well-defined?
6. overall_score: Weighted average — if grant context provided, weight grant alignment heavily (40%)

Also provide:
- strengths: list of 3 things the proposal does well FOR THIS FUNDER
- weaknesses: list of 3 things that could get it rejected BY THIS FUNDER
- recommendations: list of 3 specific improvements to better match this funder
- funder_readiness: "strong" | "moderate" | "needs_work"

Return ONLY valid JSON, nothing else."""),
    ("human", """Score this NGO proposal{grant_context_label}:

{proposal_json}""")
])

GRANT_AWARE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert grant evaluator with 20 years of experience reviewing NGO proposals.
Score this DRAFTED proposal specifically against the target grant below.
Focus on: Does the drafted text mirror the funder's language? Are activities aligned with grant priorities?
Is the budget realistic for this funder's ceiling? Is the geographic fit correct?

Score 0-100 on each dimension. Be strict — a score above 80 requires explicit evidence of tailoring.

Return ONLY valid JSON with these exact keys:
clarity_score, impact_score, budget_score, locality_alignment, beneficiary_definition,
overall_score, strengths (list of 3), weaknesses (list of 3), recommendations (list of 3),
funder_readiness ("strong"|"moderate"|"needs_work")"""),
    ("human", """TARGET GRANT:
Title: {grant_title}
Agency: {grant_agency}
Focus Areas: {grant_focus}
Award Ceiling: ${grant_ceiling:,}
Application Tip: {grant_tip}

DRAFTED PROPOSAL:
{proposal_json}""")
])

def score_proposal(proposal: dict) -> dict:
    """
    Takes the parsed proposal JSON and returns a scoring analysis.
    If proposal contains target_grant/drafted_text fields (set by Draft.js rescore),
    uses the grant-aware prompt for more precise scoring.
    """
    has_grant_context = bool(proposal.get("target_grant") and proposal.get("drafted_text"))

    if has_grant_context:
        chain = GRANT_AWARE_PROMPT | llm
        response = chain.invoke({
            "grant_title":   proposal.get("target_grant", ""),
            "grant_agency":  proposal.get("target_agency", ""),
            "grant_focus":   proposal.get("grant_focus", ""),
            "grant_ceiling": int(proposal.get("grant_ceiling", 0) or 0),
            "grant_tip":     proposal.get("application_tip", ""),
            "proposal_json": json.dumps({
                k: v for k, v in proposal.items()
                if k not in ("target_grant","target_agency","grant_focus","grant_ceiling","application_tip")
            }, indent=2),
        })
    else:
        chain = SCORING_PROMPT | llm
        response = chain.invoke({
            "proposal_json":       json.dumps(proposal, indent=2),
            "grant_context_label": "",
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