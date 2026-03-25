"""
agents/rewriter_agent.py
"""

import os
import random
import logging
from utils.llm import RotatingGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from agents.vocab_extractor import vocab_to_prompt_str

load_dotenv()
log = logging.getLogger(__name__)

_RAW_KEYS = os.getenv("GROQ_API_KEY", "")
GROQ_KEYS = [k.strip() for k in _RAW_KEYS.split(",") if k.strip()]


def _get_llm(temperature: float = 0.3) -> RotatingGroq:
    from config import GROQ_API_KEY
    key = random.choice(GROQ_KEYS) if GROQ_KEYS else GROQ_API_KEY
    return RotatingGroq(model="llama-3.3-70b-versatile", temperature=temperature, groq_api_key=key)


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


def rewrite_section(
    section_key:      str,
    section_title:    str,
    original_content: str,
    gaps_for_section: list[dict],
    funder_vocab:     list[str],
    grant:            dict,
    profile:          dict,
) -> str:
    gaps_str = (
        "\n".join(f"- [{g.get('severity','').upper()}] {g.get('description','')}" for g in gaps_for_section)
        if gaps_for_section
        else "No specific gaps identified — polish vocabulary and evidence."
    )
    llm      = _get_llm(temperature=0.3)
    chain    = REWRITE_PROMPT | llm
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
    llm      = _get_llm(temperature=0.3)
    chain    = RETRY_PROMPT | llm
    response = chain.invoke({
        "section_title":   section_title,
        "current_content": current_content,
        "feedback":        scorer_feedback,
        "funder_vocab":    vocab_to_prompt_str(funder_vocab),
    })
    return response.content.strip()


def _fmt_profile(profile: dict) -> str:
    lines = []
    for key in ("org_name", "mission", "location", "cause_area", "key_activities", "geographic_focus"):
        val = profile.get(key)
        if val:
            lines.append(f"{key}: {val}")
    return "\n".join(lines) or "No profile provided."


def gaps_for_section(analysis: dict, section_key: str) -> list[dict]:
    all_gaps = (
        analysis.get("missing_content", []) +
        analysis.get("weak_evidence", []) +
        analysis.get("wrong_vocabulary", []) +
        analysis.get("misalignment", [])
    )
    return [g for g in all_gaps if g.get("section") == section_key]