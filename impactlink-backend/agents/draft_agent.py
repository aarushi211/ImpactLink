"""
agents/draft_agent.py

Multi-section proposal drafting agent.
Rebuilt with expert grant-writing best practices baked into every prompt.
Target: CA state/foundation grants — 15–25 pages total.
"""

import json
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)

# ── Master system prompt ──────────────────────────────────────────────────────
# This is the single most important thing. Every section inherits this context.

MASTER_SYSTEM = """You are a senior grant writer with 20 years of experience securing \
funding from California state agencies, conservancies, and private foundations. \
You have personally written proposals that won over $50M in competitive grants.

YOUR WRITING PHILOSOPHY:
- Every sentence must earn its place. No filler, no fluff, no vague aspirations.
- Mirror the funder's exact language from their program description. If they say \
"riparian corridor" use that phrase, not "streamside habitat."
- Reviewers use rubrics and score in pods of 3. Write to make scoring easy — \
make the answer to every rubric criterion obvious and locatable.
- Combine hard data with a single human story. Data earns credibility; story earns \
emotional investment. Both are required.
- Never confuse outputs (200 people attended) with outcomes (87% reported improved \
skills, 43% found employment within 6 months).
- Show cause-effect logic. Every activity must connect to an output that connects \
to a measurable outcome that connects to the funder's stated goal.
- Be specific about geography, demographics, dollar amounts, timelines, and staff \
roles. Vagueness is the #1 reason proposals are rejected.
- Show capacity and credibility. Funders bet on organizations, not just ideas.
- Demonstrate equity lens. California funders in 2024–2026 heavily weight \
disadvantaged community impact, BIPOC leadership, and environmental justice.
- Length for state/foundation grants: 15–25 pages total across all sections. \
Each section: 250–450 words unless specified otherwise.

FATAL ERRORS TO NEVER MAKE:
- Using global statistics for a local problem (use county/city/zip-level data)
- Vague objectives ("improve health") instead of SMART objectives
- Budget that doesn't match the narrative activities
- Copying boilerplate that doesn't mention this specific funder
- Passive voice and bureaucratic language
- Overpromising: if you claim 10,000 beneficiaries on a $100K grant, credibility collapses
- Requesting more than the funder's stated maximum
- Forgetting to explain sustainability after grant period ends"""


# ── Section definitions with deep expert instructions ────────────────────────

SECTIONS = [
    {
        "key": "executive_summary",
        "title": "Executive Summary",
        "word_target": "250–300 words (this is a summary, not an introduction)",
        "instructions": """Write the executive summary LAST in the real world, but craft it to stand 
alone — a busy program officer should understand the entire proposal from this section.

REQUIRED structure (do not add headers, flow as 3 tight paragraphs):

PARAGRAPH 1 — THE HOOK + PROBLEM:
Open with one sentence grounding the reader in the local reality of the problem. 
Use a specific statistic tied to the grant's geography. Then state the scale and 
urgency of the problem in 2-3 sentences. End with: why existing efforts are insufficient.

PARAGRAPH 2 — THE SOLUTION + ORG:
Introduce the organization and its mission in one sentence (credibility signal).
State exactly what this project will do, for how many people, over what time period,
in what geography. Name 2–3 concrete, specific activities. Reference the funder's 
stated priority areas by name.

PARAGRAPH 3 — THE ASK + IMPACT:
State the exact dollar amount requested. State the total project cost and other 
funding sources (shows leverage). List 3 measurable outcomes the funder will achieve 
by investing. End with one sentence connecting to the funder's mission.

TONE: Confident, specific, evidence-based. Not humble, not grandiose.""",
    },
    {
        "key": "problem_statement",
        "title": "Statement of Need",
        "word_target": "400–500 words",
        "instructions": """This is the most important section. Reviewers decide here whether your project 
is worth funding. Weak needs statements are the #1 cause of rejection.

STRUCTURE (4 paragraphs):

PARAGRAPH 1 — OPEN WITH A HUMAN STORY (3–4 sentences):
Begin with a brief, specific, anonymized story of one real person from the target 
community experiencing this problem. Do NOT use statistics here. Make it visceral 
and specific: name the situation, the barrier, the consequence. End with a transition 
to the data.

PARAGRAPH 2 — THE DATA (local, recent, credible):
Now prove the story is not an isolated case. Use statistics at the county or city 
level, not state or national averages. Cite 2–3 specific data sources (government 
reports, peer-reviewed research, local surveys). Show: scale of problem, who is 
most affected (demographics), how this community is disproportionately impacted 
compared to state average. This is where equity framing lives.

PARAGRAPH 3 — ROOT CAUSES AND BARRIERS:
Explain WHY this problem exists and persists. Identify 2–3 structural or systemic 
barriers. This shows the funder you understand the problem deeply, not just its 
surface symptoms. Connect each barrier to a specific project activity that addresses it.

PARAGRAPH 4 — THE GAP (why your org, why now):
Describe what currently exists to address this problem. Be fair — acknowledge other 
efforts. Then explain specifically what gap remains and why your organization and 
this project fill it. Cite the funder's program description language to demonstrate 
alignment.

DATA RULES: Never use a statistic older than 5 years. Never use national stats for 
a local problem. If you cite a data source, be specific (e.g., "2023 California 
Health Interview Survey" not just "studies show").""",
    },
    {
        "key": "goals_and_objectives",
        "title": "Goals and Objectives",
        "word_target": "300–400 words",
        "instructions": """Grant reviewers score this section heavily because it defines what they are 
buying. Vague objectives = automatic low scores.

STRUCTURE:
Start with 1–2 broad GOALS (aspirational, long-term, big-picture).
Then list 4–6 SMART OBJECTIVES under those goals.

GOAL FORMAT: "To [broad outcome verb] [what] for [who] in [where]."
Example: "To increase affordable housing availability for extremely low-income 
households in [City/County] through the development of community land trust models."

SMART OBJECTIVE FORMAT — every objective must have ALL five elements:
"[Action verb] [specific number] [specific population] [specific outcome] 
[measurement method] by [specific date]."

Example of WEAK objective (never write this): "Improve housing outcomes for residents."

Example of STRONG objective: "Provide construction financing to 12 affordable 
housing projects serving households earning below 30% AMI in [County], resulting 
in 340 new affordable units by December 2026, as verified by certificate of occupancy records."

OBJECTIVE TYPES TO INCLUDE:
- At least 2 process objectives (activities with numbers and timelines)
- At least 2 outcome objectives (measurable changes in people/communities)
- At least 1 systems/policy objective if relevant

ACTION VERBS TO USE: increase, decrease, reduce, expand, develop, establish, 
provide, train, serve, produce, complete, achieve — never "improve," "address," or "support" alone.

IMPORTANT: The numbers in these objectives must be realistic for the grant amount. 
A $100K grant cannot produce 10,000 direct beneficiaries. Show your math is credible.""",
    },
    {
        "key": "proposed_solution",
        "title": "Project Description & Activities",
        "word_target": "500–600 words",
        "instructions": """This section is the operational heart of the proposal. Reviewers are 
checking: Is this plan coherent? Is it feasible? Will it actually achieve the objectives?

STRUCTURE — use a logic model approach (implicit, not labeled):

OPEN PARAGRAPH — PROJECT OVERVIEW:
One paragraph describing the project holistically: what it is, who implements it, 
where, over what timeframe, with what partners. Reference the specific grant program 
this is for and how the project aligns with its eligible activities.

ACTIVITY BREAKDOWN (one paragraph per major activity, 3–4 activities):
For each activity, answer:
1. WHAT: Exactly what will happen, with specific details (not "workshops" — 
   "eight 3-hour workforce certification workshops in [location]")
2. WHO: Which staff role or partner leads it, with their qualification
3. WHEN: Timeline (Month 1–3, Month 4–12, etc.)
4. HOW MANY: Number of participants/units/events
5. WHY IT WORKS: One sentence citing evidence for this approach (reference an 
   evidence-based model if possible)

PARTNERSHIPS PARAGRAPH:
Name specific partner organizations (not generic "community partners"). For each, 
state: their role, their contribution (in-kind or financial), and why they're 
credible. Partnership strength is a major scoring criterion for CA state grants.

TIMELINE STATEMENT:
One paragraph with a clear start date, key milestones, and completion date. 
If multi-year, describe what happens in each year.

AVOID: Describing activities in the passive voice. Avoid saying "participants will 
receive training" — say "Program Director [Name/Title] will lead bi-weekly 
certification sessions for cohorts of 20 participants at [Location]." """
    },
    {
        "key": "target_beneficiaries",
        "title": "Target Population & Community Engagement",
        "word_target": "300–350 words",
        "instructions": """California state funders in 2024–2026 heavily score on: (1) specificity of 
target population, (2) equity focus, (3) evidence of community voice in design.

STRUCTURE (3 paragraphs):

PARAGRAPH 1 — WHO AND HOW MANY:
Describe the primary beneficiaries with specificity: age range, income level, 
geography, demographics (race/ethnicity if relevant and available), and the 
specific characteristics that make them eligible for this project. Give a 
total number of direct beneficiaries and indirect beneficiaries separately. 
Explain the selection/outreach method.

PARAGRAPH 2 — EQUITY AND PRIORITY POPULATIONS:
Explicitly name whether the target population includes: disadvantaged communities, 
tribal communities, communities of color, low-income households, environmental 
justice communities, or other priority groups named in the funder's RFP.
Connect this to the CA definition of Severely Disadvantaged Community (MHI < 60% 
of statewide median) if applicable. Show data proving disproportionate impact.

PARAGRAPH 3 — COMMUNITY VOICE AND TRUST:
Describe how the community was involved in designing this project (surveys, 
community meetings, advisory boards, lived experience staff). This is increasingly 
required, not optional. Name specific engagement mechanisms and how feedback 
shaped the project design. This builds credibility and shows this isn't a 
top-down program.""",
    },
    {
        "key": "organizational_capacity",
        "title": "Organizational Capacity & Qualifications",
        "word_target": "300–400 words",
        "instructions": """Funders are betting on the ORGANIZATION as much as the project. This section 
answers: "Can they actually do this?" A great project idea from an unproven org 
loses to a good project from a proven org every time.

STRUCTURE (4 paragraphs):

PARAGRAPH 1 — TRACK RECORD:
Cite 2–3 specific past programs with measurable outcomes (not activities — outcomes). 
Include dollar amounts of past grants received and from whom. Example structure: 
"In 2022–2023, [Org] managed a $450,000 CalRecycle grant to [do X], resulting in 
[specific outcome with numbers]. This project was completed on time and within budget."

PARAGRAPH 2 — RELEVANT EXPERTISE:
Name specific key staff (by title, not name for privacy) and their relevant 
credentials. For the project director: years of experience, specific expertise. 
For program staff: certifications, language skills, lived experience. Show the 
team can execute.

PARAGRAPH 3 — FINANCIAL MANAGEMENT:
Demonstrate fiscal responsibility. Mention annual budget size, financial controls, 
audit history (clean audits), and any relevant fiscal sponsorship or fiduciary 
experience. Funders check this — don't skip it.

PARAGRAPH 4 — COMMUNITY ROOTEDNESS:
How long has the org worked in this geography? What community trust have they built?
Name board composition (especially community members). Reference any community 
recognition or awards. This is especially important for equity-focused CA funders.""",
    },
    {
        "key": "evaluation_plan",
        "title": "Evaluation & Learning Plan",
        "word_target": "350–400 words",
        "instructions": """Evaluation is often the most underwritten section by NGOs, yet it's heavily 
scored because funders want to know: will we know if this worked?

STRUCTURE:

SMART GOALS TABLE — Start with this markdown table:
| Goal | Metric | Baseline | Target | Timeline |
|------|--------|----------|--------|----------|

Derive rows from the user's stated KPIs. Be SMART: Specific, Measurable,
Achievable, Relevant, Time-bound. Then continue with:

OPENING STATEMENT:
State the evaluation approach in one sentence: who will conduct evaluation (internal 
staff, external evaluator, or both), what framework will be used (logic model, 
theory of change, etc.).

KPI TABLE — Output as a REAL markdown table with these exact 5 columns:
| KPI | Baseline | Target | Data Source | Frequency |
|-----|----------|--------|-------------|-----------|

List 4–6 specific, measurable KPIs drawn from the user's stated goals.
Each row must be concrete and tied to a project activity.
After the table, write 1–2 sentences interpreting the most important KPI.

DATA COLLECTION METHODS:
Describe 2–3 specific data collection tools: participant surveys (include response 
rate strategy), administrative records, pre/post assessments, focus groups. 
Be specific about who collects data and when.

LEARNING AND ADAPTATION:
One paragraph on how data will be used to improve the program during implementation 
(adaptive management), not just reported after. Funders appreciate this — it shows 
sophisticated program management.

REPORTING:
State what reports will be submitted to the funder, on what schedule, and who 
is responsible for preparing them.""",
    },
    {
        "key": "budget_narrative",
        "title": "Budget Narrative",
        "word_target": "400–500 words",
        "instructions": """The budget narrative is where many proposals die. Reviewers check: Do the 
numbers match the activities? Are costs reasonable and justified? Is this realistic?

BUDGET SUMMARY TABLE — Lead with this markdown table before the prose narrative:
| Category | Amount (USD) | % of Total | Justification (brief) |
|----------|-------------|------------|----------------------|

Fill rows for: Personnel, Fringe/Benefits, Consultants, Supplies & Equipment,
Travel, Other Direct Costs, Indirect/Overhead.
Derive amounts from the user's stated budget figures or estimate reasonably.
After the table, write the detailed prose narrative for each category:

1. PERSONNEL (typically 50–70% of budget):
For each position: title, FTE percentage, annual salary, total cost, and specific 
role in the project. Example: "Project Director (1.0 FTE, $85,000/year): responsible 
for day-to-day program management, partner coordination, grant reporting, and 
staff supervision."

2. FRINGE/BENEFITS:
State the benefit rate (typically 25–30% for nonprofits) and what it covers 
(health insurance, FICA, retirement). Example: "Benefits calculated at 28% of 
personnel costs ($23,800), covering health insurance, dental, vision, FICA, 
and 403(b) employer match."

3. CONSULTANTS/SUBCONTRACTORS:
If any, explain the need (specialized expertise not available in-house), hourly 
rate or flat fee, and scope of work. Justify why this is not a staff position.

4. SUPPLIES AND EQUIPMENT:
Itemize significant purchases. Explain why each is necessary for project activities.
Do not include general office supplies — these belong in indirect costs.

5. TRAVEL:
If included, justify mileage, per diem rates. Reference IRS or state rates.

6. OTHER DIRECT COSTS:
Participant stipends, training costs, printing, etc. — each justified.

7. INDIRECT/OVERHEAD:
State the rate (typically 10–15% for NGOs; some funders cap this). Explain what 
it covers (rent, utilities, shared administrative staff).

CLOSING STATEMENT:
State total project budget, total requested from this funder, and other confirmed 
or pending funding sources. Show leverage — funders want to see their dollars 
multiplied. Example: "This $250,000 request represents 45% of the total $556,000 
project budget. Remaining funds include $180,000 confirmed from [Funder] and 
$126,000 in in-kind contributions from [Partner]." """,
    },
    {
        "key": "sustainability",
        "title": "Sustainability Plan",
        "word_target": "250–300 words",
        "instructions": """This is the section most NGOs write last and worst. Reviewers know "we will 
seek additional grants" is not a sustainability plan. Write something credible.

STRUCTURE (3 paragraphs):

PARAGRAPH 1 — BEYOND THE GRANT PERIOD:
Explicitly state what will continue, at what scale, and how. Is this a pilot that 
will expand? A capacity-building project that builds systems lasting beyond the 
grant? Be concrete about what "sustained" looks like in 3–5 years.

PARAGRAPH 2 — DIVERSIFIED FUNDING PIPELINE (be specific):
Name 2–3 real, specific future funding sources with dollar estimates:
- Other grants already applied for or planning to apply (name the program)
- Earned income strategies (fee-for-service, social enterprise, government contracts)
- Individual donor campaign goals with specific targets
- Government contracts or SB/AB allocations the project could qualify for
- Corporate partnerships already in conversation

PARAGRAPH 3 — COMMUNITY AND SYSTEMS OWNERSHIP:
Explain how this project builds community capacity or changes systems so that 
the work continues without ongoing grant funding. Examples: training community 
members as advocates, changing institutional policy, building an endowment, 
transferring program to a government agency, establishing a coalition with 
ongoing membership dues.

WHAT NOT TO WRITE: "We will seek additional grant funding." This is the most 
common and weakest sustainability statement. If it must be included, it should 
be one of three strategies, not the only one.""",
    },
    {
        "key": "equity_statement",
        "title": "Equity, Diversity & Environmental Justice",
        "word_target": "200–300 words",
        "instructions": """California state funders in 2024–2026 require or heavily weight this section. 
It is often a standalone scored criterion. Even if not explicitly required, include it.

STRUCTURE (2–3 paragraphs):

PARAGRAPH 1 — EQUITY IN PROJECT DESIGN:
How does this project explicitly address historic inequity, systemic racism, or 
environmental injustice? Name the specific disparities your project addresses and 
cite data. Connect to CalEnviroScreen scores, HOLC redlining history, or other 
recognized equity frameworks if relevant to the issue area.

PARAGRAPH 2 — EQUITY IN ORGANIZATIONAL PRACTICE:
Describe the org's internal equity commitments: staff demographics, BIPOC 
leadership, multilingual capacity, community-accountable governance. Don't 
overstate — funders can verify and will penalize performative claims.

PARAGRAPH 3 — ENVIRONMENTAL JUSTICE (if relevant):
For environmental, housing, water, or transportation grants: explicitly connect 
to EJ communities as defined by CalEPA. Reference proximity to pollution sources, 
health burdens, and lack of prior investment. Name the specific census tracts or 
communities if possible.""",
    },
]

# ── Section prompt ────────────────────────────────────────────────────────────

SECTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", MASTER_SYSTEM),
    ("user", """Write the "{section_title}" section of a grant proposal.

━━━ SECTION REQUIREMENTS ━━━
Target length: {word_target}
Writing instructions:
{instructions}

━━━ ORGANIZATION PROFILE ━━━
{proposal}

━━━ TARGET GRANT / FUNDER ━━━
{grant}

━━━ USER'S SPECIFIC DATA INPUTS ━━━
{user_values}

━━━ CRITICAL RULES FOR THIS RESPONSE ━━━
1. Use the funder's exact program language where possible — mirror their vocabulary
2. Every claim needs a number, a name, or a date — no vague statements
3. Connect every activity to a specific measurable outcome
4. Demonstrate equity lens appropriate for CA state funding
5. Do NOT start with a generic opener like "This proposal seeks to..." 
   — open with the most compelling, specific sentence possible
6. USE MARKDOWN TABLES where instructed — format them exactly as standard markdown
   with header row, separator row (|---|---|), and data rows
7. Return ONLY the section content — no JSON, no meta-commentary outside the section
   Headers and tables ARE allowed where the section instructions require them

Write the section now:""")
])


# ── Draft functions ───────────────────────────────────────────────────────────

def _extract_user_values(proposal: dict) -> str:
    """Pull concrete numbers and facts from proposal for table population."""
    lines = []
    if proposal.get("total_budget"):
        lines.append(f"Total budget: {proposal['total_budget']}")
    if proposal.get("target_beneficiaries"):
        lines.append(f"Target beneficiaries: {', '.join(proposal['target_beneficiaries'])}")
    if proposal.get("key_activities"):
        lines.append(f"Key activities: {', '.join(proposal['key_activities'])}")
    if proposal.get("kpis"):
        lines.append(f"KPIs: {', '.join(proposal['kpis'])}")
    if proposal.get("budget_breakdown"):
        lines.append(f"Budget breakdown: {', '.join(proposal['budget_breakdown'])}")
    if proposal.get("geographic_focus"):
        lines.append(f"Geography: {', '.join(proposal['geographic_focus'])}")
    if proposal.get("timeline"):
        lines.append(f"Timeline: {proposal['timeline']}")
    if proposal.get("number_served"):
        lines.append(f"People served: {proposal['number_served']}")
    return "\n".join(lines) if lines else "Use reasonable estimates based on proposal context."



def _build_grant_context(grant: dict) -> dict:
    """Build a lean but complete grant context for the prompt."""
    return {
        "title":           grant.get("title", ""),
        "agency":          grant.get("agency", ""),
        "description":     (grant.get("description", "")[:1500]
                            if grant.get("description") else ""),
        "focus_areas":     grant.get("focus_areas", ""),
        "eligibility":     grant.get("eligibility", []),
        "award_floor":     grant.get("award_floor", 0),
        "award_ceiling":   grant.get("award_ceiling", 0),
        "funding_method":  grant.get("funding_method", ""),
        "close_date":      grant.get("close_date", ""),
        "match_required":  grant.get("cost_sharing_required", False),
        "application_tip": grant.get("application_tip", ""),
    }


def draft_proposal(proposal: dict, grant: dict) -> dict:
    """
    Draft a complete proposal. Returns dict with all sections.
    Non-streaming — waits for each section before moving to next.
    """
    chain = SECTION_PROMPT | llm
    grant_ctx = _build_grant_context(grant)
    sections = {}

    for section in SECTIONS:
        # Extract numeric/table values from proposal for table population
        user_values = _extract_user_values(proposal)
        response = chain.invoke({
            "section_title": section["title"],
            "word_target":   section["word_target"],
            "instructions":  section["instructions"],
            "proposal":      json.dumps(proposal, indent=2),
            "grant":         json.dumps(grant_ctx, indent=2),
            "user_values":   user_values,
        })
        sections[section["key"]] = {
            "title":   section["title"],
            "content": response.content.strip(),
        }

    return {
        "grant_id":      grant.get("grant_id", ""),
        "grant_title":   grant.get("title", ""),
        "agency":        grant.get("agency", ""),
        "org_name":      proposal.get("organization_name", ""),
        "sections":      sections,
        "section_order": [s["key"] for s in SECTIONS],
        "total_sections": len(SECTIONS),
    }


def draft_proposal_stream(proposal: dict, grant: dict):
    """
    Generator — yields one JSON line per completed section.
    Frontend reads via ReadableStream or EventSource.
    """
    chain = SECTION_PROMPT | llm
    grant_ctx = _build_grant_context(grant)

    for i, section in enumerate(SECTIONS):
        # Extract numeric/table values from proposal for table population
        user_values = _extract_user_values(proposal)
        response = chain.invoke({
            "section_title": section["title"],
            "word_target":   section["word_target"],
            "instructions":  section["instructions"],
            "proposal":      json.dumps(proposal, indent=2),
            "grant":         json.dumps(grant_ctx, indent=2),
            "user_values":   user_values,
        })

        yield json.dumps({
            "key":      section["key"],
            "title":    section["title"],
            "content":  response.content.strip(),
            "index":    i + 1,
            "total":    len(SECTIONS),
            "done":     False,
        }) + "\n"

    yield json.dumps({
        "done":          True,
        "total_sections": len(SECTIONS),
    }) + "\n"