"""
agents/gap_analysis_agent.py
"""

import os
import json
import random
import logging
from utils.llm import RotatingGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

_RAW_KEYS = os.getenv("GROQ_API_KEY", "")
GROQ_KEYS = [k.strip() for k in _RAW_KEYS.split(",") if k.strip()]


def _get_llm() -> RotatingGroq:
    from config import GROQ_API_KEY
    key = random.choice(GROQ_KEYS) if GROQ_KEYS else GROQ_API_KEY
    return RotatingGroq(model="llama-3.3-70b-versatile", temperature=0, groq_api_key=key)


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


def analyze_gaps(
    existing_sections: dict[str, str],
    grant: dict,
    funder_vocab: list[str],
) -> dict:
    sections_str = "\n\n".join(
        f"=== {key.upper()} ===\n{text}"
        for key, text in existing_sections.items()
        if text.strip()
    )
    if not sections_str:
        log.warning("gap_analysis: no existing sections provided")
        return _empty_analysis()

    vocab_str = "\n".join(f"- {v}" for v in funder_vocab) or "None extracted."

    llm      = _get_llm()
    chain    = GAP_PROMPT | llm
    response = chain.invoke({
        "grant_title":       grant.get("title", ""),
        "grant_agency":      grant.get("agency", ""),
        "grant_description": grant.get("description", "")[:2000],
        "funder_vocab":      vocab_str,
        "existing_sections": sections_str,
    })

    raw = response.content.strip()
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
    updated = dict(analysis)
    updated["user_confirmed_gaps"]   = confirmed_gaps
    updated["user_additions"]        = user_additions
    updated["sections_to_rewrite"]   = sections_to_rewrite
    return updated


def _empty_analysis() -> dict:
    return {
        "missing_content":     [],
        "weak_evidence":       [],
        "wrong_vocabulary":    [],
        "misalignment":        [],
        "sections_to_rewrite": [],
    }


def _validate_analysis(result: dict) -> None:
    required = {"missing_content", "weak_evidence", "wrong_vocabulary", "misalignment", "sections_to_rewrite"}
    missing  = required - set(result.keys())
    if missing:
        raise ValueError(f"Gap analysis missing keys: {missing}")