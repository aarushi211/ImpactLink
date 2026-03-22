"""
agents/gap_analysis_agent.py

Flow A only: compares the EXISTING PROPOSAL SECTIONS against grant requirements.

This is NOT the same as the scratch flow's slot extractor.
The input is actual written section content — not an org profile.
The output is a structured gap list the user reviews before any rewriting begins.

Phase 4 upgrade path:
    replace the LLM detection with a Kuzu graph traversal query.
    LLM role shifts to explaining gaps in prose — not detecting them.
    The function signature stays the same, callers don't change.
"""

import json
import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

# ── Gap analysis prompt ───────────────────────────────────────────────────────

GAP_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a senior grant reviewer with 20 years of experience.
You are comparing an NGO's EXISTING WRITTEN PROPOSAL against a grant's requirements.

Your task: identify specific, actionable gaps between what the proposal currently
says and what this grant requires.

A gap is one of:
1. MISSING CONTENT  — the grant requires X but the proposal doesn't mention it
2. WEAK EVIDENCE    — the proposal mentions X but without data, specifics, or outcomes
3. WRONG VOCABULARY — the proposal uses different terms than the funder uses
4. MISALIGNMENT     — a section's emphasis doesn't match what this funder prioritizes

DO NOT flag things that are not required by this grant.
DO NOT be vague — each gap must reference specific grant language and specific
proposal content (or absence of it).

Return ONLY a JSON object with this exact structure:
{{
  "missing_content": [
    {{"section": "executive_summary", "description": "No mention of riparian corridor restoration which is a stated priority", "severity": "high"}}
  ],
  "weak_evidence": [
    {{"section": "target_beneficiaries", "description": "Claims 500 beneficiaries but no source cited", "severity": "medium"}}
  ],
  "wrong_vocabulary": [
    {{"section": "proposed_solution", "description": "Uses 'streamside habitat' instead of funder's term 'riparian corridor'", "severity": "low"}}
  ],
  "misalignment": [
    {{"section": "evaluation_plan", "description": "Focuses on outputs not outcomes — funder's rubric explicitly scores on measurable outcomes", "severity": "high"}}
  ],
  "sections_to_rewrite": ["executive_summary", "evaluation_plan"]
}}

severity: "high" = likely to cause rejection | "medium" = will lower score | "low" = minor polish"""),
    ("user", """GRANT TITLE: {grant_title}
GRANT AGENCY: {grant_agency}
GRANT DESCRIPTION:
{grant_description}

FUNDER VOCABULARY (phrases the funder uses that reviewers look for):
{funder_vocab}

EXISTING PROPOSAL SECTIONS:
{existing_sections}"""),
])


# ── Public API ────────────────────────────────────────────────────────────────

def analyze_gaps(
    existing_sections: dict[str, str],
    grant: dict,
    funder_vocab: list[str],
) -> dict:
    """
    Compare existing written proposal sections against grant requirements.

    Args:
        existing_sections: {section_key: section_text_content}
                           Pass the raw text of each section, not SectionResult dicts.
        grant:             the full grant dict
        funder_vocab:      extracted vocab list from vocab_extractor

    Returns:
        Structured gap dict with keys:
            missing_content, weak_evidence, wrong_vocabulary,
            misalignment, sections_to_rewrite
        Falls back to a minimal safe dict on parse failure.
    """
    # Format existing sections for the prompt
    sections_str = "\n\n".join(
        f"=== {key.upper()} ===\n{text}"
        for key, text in existing_sections.items()
        if text.strip()
    )
    if not sections_str:
        log.warning("gap_analysis: no existing sections provided")
        return _empty_analysis()

    vocab_str = "\n".join(f"- {v}" for v in funder_vocab) or "None extracted."

    chain = GAP_PROMPT | llm
    response = chain.invoke({
        "grant_title":       grant.get("title", ""),
        "grant_agency":      grant.get("agency", ""),
        "grant_description": grant.get("description", "")[:2000],  # cap to avoid token overflow
        "funder_vocab":      vocab_str,
        "existing_sections": sections_str,
    })

    raw = response.content.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]

    try:
        result = json.loads(raw.strip())
        _validate_analysis(result)
        return result
    except (json.JSONDecodeError, ValueError) as e:
        log.warning("gap_analysis: JSON parse failed — %s\nRaw: %s", e, raw)
        return _empty_analysis()


def apply_user_adjustments(
    analysis: dict,
    confirmed_gaps: list[str],
    user_additions: str,
    sections_to_rewrite: list[str],
) -> dict:
    """
    Merge user's gate input back into the analysis dict.

    Args:
        analysis:            the original gap analysis dict
        confirmed_gaps:      list of gap descriptions the user kept (unchecked = removed)
        user_additions:      free-text adjustments the user typed
        sections_to_rewrite: user-confirmed list of sections to rewrite

    Returns:
        Updated analysis dict ready to pass to the rewriter.
    """
    updated = dict(analysis)
    updated["user_confirmed_gaps"] = confirmed_gaps
    updated["user_additions"] = user_additions
    updated["sections_to_rewrite"] = sections_to_rewrite
    return updated


# ── Helpers ───────────────────────────────────────────────────────────────────

def _empty_analysis() -> dict:
    return {
        "missing_content":    [],
        "weak_evidence":      [],
        "wrong_vocabulary":   [],
        "misalignment":       [],
        "sections_to_rewrite": [],
    }


def _validate_analysis(result: dict) -> None:
    """Raise ValueError if required keys are missing."""
    required = {"missing_content", "weak_evidence",
                "wrong_vocabulary", "misalignment", "sections_to_rewrite"}
    missing = required - set(result.keys())
    if missing:
        raise ValueError(f"Gap analysis missing keys: {missing}")
