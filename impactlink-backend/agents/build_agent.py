"""
agents/build_agent.py
─────────────────────────────────────────────────────────────────
Guided proposal builder — a streaming conversational agent that
walks an NGO through building a proposal from scratch.

Flow (7 guided steps):
  1. Project Vision      — what problem, who benefits, where
  2. Key Activities      — what you will actually do
  3. Target Beneficiaries — who and how many
  4. Org Capacity        — why your org is right for this
  5. Goals & KPIs        — measurable outcomes
  6. Budget Overview     — rough cost categories
  7. Sustainability      — life after grant funding

After each step, the agent drafts that section using the
existing draft_agent SECTION_PROMPT, giving the user real
proposal text they can edit and approve.

Streaming protocol (same as draft_proposal_stream):
  { "type": "question",  "step": 1, "key": "vision",    "text": "..." }
  { "type": "draft",     "step": 1, "key": "vision",    "title": "...", "content": "..." }
  { "type": "complete",  "proposal": { ... full proposal dict ... } }
"""

import json
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.35)

# ── Build steps definition ─────────────────────────────────────

STEPS = [
    {
        "key":        "vision",
        "title":      "Project Vision",
        "section_map": "executive_summary",   # maps to draft_agent section key
        "question":   "Let's start with the big picture. **What problem does your project solve, and who does it help?** Describe the core challenge your community faces and what change you want to create. (2–4 sentences is perfect)",
        "draft_instructions": "Write a compelling executive summary. Lead with the specific problem, introduce the organization's mission, then describe the proposed solution and expected impact. Be concrete and funder-facing.",
    },
    {
        "key":        "activities",
        "title":      "Key Activities",
        "section_map": "proposed_solution",
        "question":   "Great. Now let's get specific. **What will your team actually do?** List the main activities — workshops, trainings, services, infrastructure — and roughly how often. Think of this as your project's action plan.",
        "draft_instructions": """Describe the project activities in detail. Lead with an activities summary table in markdown:
| Activity | Frequency | Who Leads | # Served | Outcome |
|----------|-----------|-----------|---------|---------|
Fill one row per activity using the user's stated activities. Then write the narrative explanation for each. Show clear cause-effect logic between activities and impact.""",
    },
    {
        "key":        "beneficiaries",
        "title":      "Target Beneficiaries",
        "section_map": "target_beneficiaries",
        "question":   "Who will directly benefit from this project? **Tell me about your target community** — their demographics, how many people, how you'll reach them, and why they need this intervention specifically.",
        "draft_instructions": "Describe who will benefit, how many people, and how they will be selected and reached. Include demographic details, geographic context, and evidence of community need.",
    },
    {
        "key":        "capacity",
        "title":      "Organizational Capacity",
        "section_map": "organizational_capacity",
        "question":   "Funders want to know your org can actually deliver. **What makes your organization uniquely qualified?** Mention your track record, team expertise, any past programs, and key partnerships.",
        "draft_instructions": "Describe why this organization is uniquely positioned to execute this project. Reference past programs with outcomes, team qualifications, partnerships, and organizational infrastructure.",
    },
    {
        "key":        "goals",
        "title":      "Goals & Measurement",
        "section_map": "evaluation_plan",
        "question":   "How will you know you've succeeded? **What are your 3–5 measurable goals or KPIs?** For example: '200 youth trained', '80% pass rate', '3 partner schools onboarded'. Be as specific as possible.",
        "draft_instructions": """Write an evaluation plan. Start with a SMART goals table in markdown:
| Goal | Metric | Baseline | Target | Timeline |
|------|--------|----------|--------|----------|
Then list 3–5 KPIs using the user's stated goals. Explain data collection methods, who is responsible, and the reporting timeline. Derive table values from user inputs.""",
    },
    {
        "key":        "budget",
        "title":      "Budget Overview",
        "section_map": "budget_narrative",
        "question":   "Let's talk money. **What are your main cost categories?** For example: staff salaries, training materials, venue rental, technology, travel. Give me rough estimates or percentages if you have them.",
        "draft_instructions": """Write a budget narrative. Lead with a budget breakdown table in markdown:
| Category | Est. Amount (USD) | % of Total | Notes |
|----------|------------------|------------|-------|
Use rows for: Personnel, Fringe, Consultants, Supplies, Travel, Indirect Costs.
Derive amounts from user's stated figures. Then write the prose justification for each line.""",
    },
    {
        "key":        "sustainability",
        "title":      "Sustainability Plan",
        "section_map": "sustainability",
        "question":   "Last step. **How will this project continue after the grant ends?** Describe your plan for long-term sustainability — follow-on funding, community ownership, earned income, or partnerships.",
        "draft_instructions": "Explain how the project will continue after grant funding ends. Reference diversified funding pipelines, community ownership mechanisms, partnerships, or earned income strategies.",
    },
]

# ── Prompts ────────────────────────────────────────────────────

DRAFT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert grant writer with 20 years of experience.
Your task: take the user's raw answer and turn it into polished, professional grant proposal text for ONE section.

Rules:
- Write in clear, evidence-based, compelling grant language
- Be specific — use the user's details, don't invent facts
- 180–280 words for this section (tables do not count toward word count)
- USE MARKDOWN TABLES where specified — standard markdown format with | separators
- Return ONLY the section content — markdown tables and headers ARE allowed
- Do NOT add JSON, preamble, or meta-commentary"""),
    ("user", """Section: {section_title}
Instructions: {instructions}

Organization context:
{org_context}

User's specific data inputs:
{user_values}

User's answer for this section:
{user_answer}

Write the section now:"""),
])

FOLLOWUP_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a friendly grant writing coach helping an NGO leader build a proposal.
You just drafted a section based on their answer. They've given you feedback or revisions.
Incorporate their changes and rewrite the section.

Rules:
- Keep the professional grant language
- Incorporate ALL changes the user asks for
- 180–280 words
- Return ONLY the revised section text"""),
    ("user", """Current draft:
{current_draft}

User's feedback/revision:
{feedback}

Write the revised section:"""),
])


def _org_context(profile: dict) -> str:
    """Summarize NGO profile as context for drafting."""
    return "\n".join(filter(None, [
        f"Organization: {profile.get('org_name', '')}",
        f"Mission: {profile.get('mission', '')}",
        f"Location: {profile.get('location', '')}",
        f"Cause Area: {profile.get('cause_area', '')}",
        f"SDGs: {', '.join(profile.get('sdgs', []))}",
        f"Key Activities: {', '.join(profile.get('key_activities', []))}",
        f"Geographic Focus: {', '.join(profile.get('geographic_focus', []))}",
    ]))


# ── Main streaming function ────────────────────────────────────
def _extract_user_values(profile: dict, answered: dict) -> str:
    """Pull concrete numbers the user mentioned for table population."""
    import re
    lines = []
    if profile.get("location"):
        lines.append(f"Location: {profile['location']}")
    if profile.get("key_activities"):
        lines.append(f"Activities: {', '.join(profile['key_activities'])}")
    # Scan answered values for numbers
    for key, answer in answered.items():
        # Pull out dollar amounts, percentages, and counts
        numbers = re.findall(r'\$[\d,]+|\d+%|\d{2,}\s+(?:people|participants|youth|families|units|staff)', answer)
        if numbers:
            lines.append(f"{key}: {', '.join(numbers[:4])}")
    return "\n".join(lines) if lines else "Estimate reasonably from context."




def build_proposal_stream(answers: list, profile: dict, grant: dict = None):
    """
    Generator — drives the guided build flow.

    `answers` is a list of { step_key, user_answer } dicts — everything
    collected so far. The frontend sends the whole list on each call;
    we process whichever step comes next.

    Yields JSON lines:
      { "type": "question",  "step": N, "key": "...", "text": "..." }
      { "type": "draft",     "step": N, "key": "...", "title": "...", "content": "..." }
      { "type": "complete",  "sections": { ... }, "section_order": [...] }
    """
    chain    = DRAFT_PROMPT | llm
    answered = {a["step_key"]: a["user_answer"] for a in answers}
    org_ctx  = _org_context(profile)
    sections = {}

    for i, step in enumerate(STEPS):
        key = step["key"]

        if key not in answered:
            # This step hasn't been answered yet — send the question and stop
            yield json.dumps({
                "type": "question",
                "step": i + 1,
                "total": len(STEPS),
                "key":  key,
                "title": step["title"],
                "text": step["question"],
            }) + "\n"
            return

        # This step has an answer — draft the section
        user_values = _extract_user_values(profile, answered)
        instructions = step["draft_instructions"]

        # Intercept budget generation to use the strict budget calculator script
        if step["section_map"] == "budget_narrative":
            from agents.draft_agent import _inject_budget_calculator
            temp_profile = dict(profile)
            temp_profile["total_budget"] = answered.get("budget", "")
            instructions, user_values = _inject_budget_calculator(
                "budget_narrative", instructions, temp_profile, grant or {}, user_values
            )

        response = chain.invoke({
            "section_title": step["title"],
            "instructions":  instructions,
            "org_context":   org_ctx,
            "user_values":   user_values,
            "user_answer":   answered[key],
        })

        section_content = response.content.strip()
        sections[step["section_map"]] = {
            "title":   step["title"],
            "content": section_content,
        }

        # Stream this section draft back
        yield json.dumps({
            "type":    "draft",
            "step":    i + 1,
            "total":   len(STEPS),
            "key":     key,
            "section_key": step["section_map"],
            "title":   step["title"],
            "content": section_content,
        }) + "\n"

    # All steps answered — emit final complete signal
    section_order = ["executive_summary", "proposed_solution", "target_beneficiaries",
                     "organizational_capacity", "evaluation_plan", "budget_narrative", "sustainability"]
    yield json.dumps({
        "type":          "complete",
        "sections":      sections,
        "section_order": section_order,
        "org_name":      profile.get("org_name", ""),
        "grant_title":   grant.get("title", "") if grant else "",
    }) + "\n"


def revise_section(current_draft: str, feedback: str) -> str:
    """
    One-shot revision of a single section based on user feedback.
    Returns revised text only.
    """
    chain    = FOLLOWUP_PROMPT | llm
    response = chain.invoke({
        "current_draft": current_draft,
        "feedback":      feedback,
    })
    return response.content.strip()