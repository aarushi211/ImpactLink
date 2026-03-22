"""
agents/rewriter_agent.py

Rewrites a single proposal section incorporating:
- Funder vocabulary
- Specific gap(s) identified for this section
- The original content as context (not a blank slate)

Kept separate from draft_agent.py intentionally:
- draft_agent writes from scratch (Flow B)
- rewriter_agent improves existing content (Flow A)
Different prompts, different context, different output expectations.
"""

import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from agents.vocab_extractor import vocab_to_prompt_str

load_dotenv()
log = logging.getLogger(__name__)

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)

# ── Rewrite prompt ────────────────────────────────────────────────────────────

REWRITE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a senior grant writer improving an existing proposal section.

Your task is NOT to rewrite from scratch. Your task is to:
1. Keep what is already strong
2. Fix the specific gaps identified
3. Weave in the funder's vocabulary naturally
4. Sharpen evidence and specificity where weak

Rules:
- Do not invent facts, statistics, or names not present in the original or org profile
- Mirror the funder's exact phrases where relevant — do not paraphrase them
- Every claim needs a number, name, or date
- Return ONLY the improved section content — no JSON, no meta-commentary"""),
    ("user", """SECTION: {section_title}

ORIGINAL CONTENT:
{original_content}

GAPS TO FIX IN THIS SECTION:
{gaps_for_section}

FUNDER VOCABULARY TO USE:
{funder_vocab}

ORG PROFILE (for factual grounding):
{org_profile}

GRANT CONTEXT:
Title: {grant_title}
Agency: {grant_agency}

Rewrite the section now, fixing the gaps while preserving what works:"""),
])

RETRY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a senior grant writer doing a targeted revision.
The section below scored too low. Fix ONLY what the feedback identifies.
Do not restructure or rewrite sections that are already strong.
Return ONLY the revised section content."""),
    ("user", """SECTION: {section_title}

CURRENT CONTENT:
{current_content}

SCORER FEEDBACK:
{feedback}

FUNDER VOCABULARY TO USE:
{funder_vocab}

Revise the section now:"""),
])


# ── Public API ────────────────────────────────────────────────────────────────

def rewrite_section(
    section_key:      str,
    section_title:    str,
    original_content: str,
    gaps_for_section: list[dict],
    funder_vocab:     list[str],
    grant:            dict,
    profile:          dict,
) -> str:
    """
    Rewrite one section incorporating gaps and funder vocab.

    Args:
        section_key:      e.g. "executive_summary"
        section_title:    human-readable title
        original_content: the existing text of this section
        gaps_for_section: list of gap dicts relevant to this section
                          (filtered from the full gap analysis)
        funder_vocab:     extracted vocab list
        grant:            grant dict
        profile:          NGO profile dict

    Returns:
        Rewritten section text (plain string).
    """
    # Format gaps for prompt
    if gaps_for_section:
        gaps_str = "\n".join(
            f"- [{g.get('severity','').upper()}] {g.get('description','')}"
            for g in gaps_for_section
        )
    else:
        gaps_str = "No specific gaps identified — polish vocabulary and evidence."

    chain = REWRITE_PROMPT | llm
    response = chain.invoke({
        "section_title":    section_title,
        "original_content": original_content,
        "gaps_for_section": gaps_str,
        "funder_vocab":     vocab_to_prompt_str(funder_vocab),
        "org_profile":      _fmt_profile(profile),
        "grant_title":      grant.get("title", ""),
        "grant_agency":     grant.get("agency", ""),
    })
    return response.content.strip()


def retry_rewrite(
    section_title:   str,
    current_content: str,
    scorer_feedback: str,
    funder_vocab:    list[str],
) -> str:
    """
    Targeted revision based on scorer feedback.
    Called when initial rewrite scored below threshold.

    Args:
        section_title:   human-readable section name
        current_content: the rewritten content that scored too low
        scorer_feedback: the scorer's 1–2 sentence feedback
        funder_vocab:    extracted vocab list

    Returns:
        Revised section text.
    """
    chain = RETRY_PROMPT | llm
    response = chain.invoke({
        "section_title":   section_title,
        "current_content": current_content,
        "feedback":        scorer_feedback,
        "funder_vocab":    vocab_to_prompt_str(funder_vocab),
    })
    return response.content.strip()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_profile(profile: dict) -> str:
    lines = []
    for key in ("org_name", "mission", "location", "cause_area",
                "key_activities", "geographic_focus"):
        val = profile.get(key)
        if val:
            lines.append(f"{key}: {val}")
    return "\n".join(lines) or "No profile provided."


def gaps_for_section(analysis: dict, section_key: str) -> list[dict]:
    """
    Filter the full gap analysis down to gaps relevant to one section.
    Combines all gap types (missing, weak, vocab, misalignment).

    Args:
        analysis:    the full gap analysis dict from gap_analysis_agent
        section_key: the section to filter for

    Returns:
        List of gap dicts relevant to this section.
    """
    all_gaps = (
        analysis.get("missing_content", []) +
        analysis.get("weak_evidence", []) +
        analysis.get("wrong_vocabulary", []) +
        analysis.get("misalignment", [])
    )
    return [g for g in all_gaps if g.get("section") == section_key]
