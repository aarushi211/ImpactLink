"""
agents/draft_agent_v2.py

Enhanced proposal drafting agent with:
1. Funder vocab extraction
2. Gap analysis
3. Parallel section drafting
4. Score-based retries (max 2)
5. Word-level diff highlighting
"""

import json
import asyncio
import difflib
from typing import List, Dict, Any
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)
critic_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.1)

# ── Master system prompt (inherited from v1 but refined) ──────────────────────

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
"""

# Import SECTIONS from v1 for consistency, or redefine if needed.
# For v2, we keep the same section structure but enhance the prompts.
from agents.draft_agent import SECTIONS, _extract_user_values, _build_grant_context

# ── Enhanced Prompts ─────────────────────────────────────────────────────────

VOCAB_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are an expert grant writer. Extract the top 10-15 key 'funder vocab' phrases from the following grant description. These are terms, buzzwords, or specific program language that the funder uses to describe their priorities. Return them as a comma-separated list."),
    ("user", "GRANT DESCRIPTION:\n{description}")
])

GAP_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are a master grant reviewer. Compare the organization's information with the grant requirements. Identify the top 3-5 critical 'gaps' — info that is missing or weak but required for a winning proposal. Return a JSON list of strings."),
    ("user", "ORG PROFILE:\n{proposal}\n\nGRANT DESCRIPTION:\n{description}")
])

ENHANCED_SECTION_PROMPT = ChatPromptTemplate.from_messages([
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

━━━ FUNDER VOCABULARY (USE THESE EXACT PHRASES) ━━━
{funder_vocab}

━━━ GAPS ADDRESSED ━━━
{addressed_gaps}

━━━ USER'S SPECIFIC DATA INPUTS ━━━
{user_values}

━━━ CRITICAL RULES ━━━
1. MIRROR the funder vocabulary naturally.
2. Ensure the gaps identified previously are proactively addressed or mitigated.
3. Every claim needs a number, a name, or a date.
4. Return ONLY the section content.
""")
])

SCORING_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a strict grant reviewer. Score the following proposal section on a scale of 1-10. 
Criteria: 
- Alignment with grant priorities
- Use of funder vocabulary
- Specificity and data usage
- Clarity and persuasiveness

Return ONLY a JSON object with 'score' (int) and 'feedback' (string, max 2 sentences)."""),
    ("user", "SECTION TITLE: {section_title}\n\nCONTENT:\n{content}\n\nGRANT CONTEXT:\n{grant_ctx}")
])

# ── Step 1 & 2: Analysis ─────────────────────────────────────────────────────

async def extract_funder_vocab(description: str) -> str:
    chain = VOCAB_PROMPT | llm
    response = await chain.ainvoke({"description": description})
    return response.content.strip()

async def analyze_gaps(proposal: dict, description: str) -> List[str]:
    chain = GAP_PROMPT | llm
    response = await chain.ainvoke({
        "proposal": json.dumps(proposal),
        "description": description
    })
    try:
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        return json.loads(content)
    except:
        return ["General alignment with grant priorities"]

# ── Step 5 & 6: Scoring & Diffs ──────────────────────────────────────────────

async def score_section(section_title: str, content: str, grant_ctx: dict) -> Dict[str, Any]:
    chain = SCORING_PROMPT | critic_llm
    response = await chain.ainvoke({
        "section_title": section_title,
        "content": content,
        "grant_ctx": json.dumps(grant_ctx)
    })
    try:
        res_content = response.content.strip()
        if "```json" in res_content:
            res_content = res_content.split("```json")[1].split("```")[0]
        elif "```" in res_content:
            res_content = res_content.split("```")[1].split("```")[0]
        return json.loads(res_content)
    except:
        return {"score": 5, "feedback": "Could not parse score."}

def get_word_diff(old_text: str, new_text: str) -> str:
    """Returns a visual representation of word-level changes."""
    old_words = old_text.split()
    new_words = new_text.split()
    
    matcher = difflib.SequenceMatcher(None, old_words, new_words)
    result = []
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            result.append(" ".join(old_words[i1:i2]))
        elif tag == 'replace':
            result.append(f"[-{' '.join(old_words[i1:i2])}-] {{+{' '.join(new_words[j1:j2])}+}}")
        elif tag == 'delete':
            result.append(f"[-{' '.join(old_words[i1:i2])}-]")
        elif tag == 'insert':
            result.append(f"{{+{' '.join(new_words[j1:j2])}+}}")
            
    return " ".join(result)

# ── Drafting Core ─────────────────────────────────────────────────────────────

async def draft_section_with_retry(
    section: dict, 
    proposal: dict, 
    grant_ctx: dict, 
    funder_vocab: str, 
    addressed_gaps: str,
    user_values: str
) -> Dict[str, Any]:
    
    chain = ENHANCED_SECTION_PROMPT | llm
    
    # Initial draft
    response = await chain.ainvoke({
        "section_title": section["title"],
        "word_target":   section["word_target"],
        "instructions":  section["instructions"],
        "proposal":      json.dumps(proposal, indent=2),
        "grant":         json.dumps(grant_ctx, indent=2),
        "funder_vocab":   funder_vocab,
        "addressed_gaps": addressed_gaps,
        "user_values":   user_values,
    })
    
    content = response.content.strip()
    history = [content]
    diffs = []
    
    # Retry logic
    retry_count = 0
    max_retries = 2
    target_score = 8
    
    while retry_count < max_retries:
        assessment = await score_section(section["title"], content, grant_ctx)
        if assessment.get("score", 0) >= target_score:
            break
        
        retry_count += 1
        # Rewrite with feedback
        rewrite_prompt = ChatPromptTemplate.from_messages([
            ("system", MASTER_SYSTEM),
            ("user", f"""Rewrite the following section to improve it based on feedback.
            
            SECTION: {section['title']}
            FEEDBACK: {assessment.get('feedback')}
            CURRENT CONTENT:
            {content}
            
            Keep the same target length and requirements.
            """)
        ])
        rewrite_chain = rewrite_prompt | llm
        rewrite_response = await rewrite_chain.ainvoke({
            "section_title": section["title"],
            "feedback": assessment.get("feedback"),
            "content": content
        })

        
        new_content = rewrite_response.content.strip()
        diffs.append(get_word_diff(content, new_content))
        content = new_content
        history.append(content)
        
    return {
        "key": section["key"],
        "title": section["title"],
        "content": content,
        "score": (await score_section(section["title"], content, grant_ctx)).get("score", 0),
        "retries": retry_count,
        "diffs": diffs
    }

async def draft_proposal_v2(proposal: dict, grant: dict, max_concurrency: int = 1) -> dict:
    grant_ctx = _build_grant_context(grant)
    user_values = _extract_user_values(proposal)
    
    # Analysis steps
    vocab = await extract_funder_vocab(grant_ctx["description"])
    gaps = await analyze_gaps(proposal, grant_ctx["description"])
    gaps_str = "\n".join([f"- {g}" for g in gaps])
    
    # Sequential drafting to avoid rate limits
    results = []
    for section in SECTIONS:
        res = await draft_section_with_retry(
            section, proposal, grant_ctx, vocab, gaps_str, user_values
        )
        results.append(res)
        await asyncio.sleep(2) # Small delay between sections


    
    sections_dict = {res["key"]: res for res in results}
    
    return {
        "grant_id":      grant.get("grant_id", ""),
        "grant_title":   grant.get("title", ""),
        "agency":        grant.get("agency", ""),
        "org_name":      proposal.get("organization_name", ""),
        "funder_vocab":  vocab,
        "identified_gaps": gaps,
        "sections":      sections_dict,
        "section_order": [s["key"] for s in SECTIONS],
    }
