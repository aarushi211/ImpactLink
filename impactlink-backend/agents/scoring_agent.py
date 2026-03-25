"""
agents/scoring_agent.py
"""

import os
import re
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

SCORE_THRESHOLD = 75
MAX_RETRIES     = 2


def _get_scorer_llm() -> RotatingGroq:
    from config import GROQ_API_KEY
    key = random.choice(GROQ_KEYS) if GROQ_KEYS else GROQ_API_KEY
    return RotatingGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        groq_api_key=key,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


SCORING_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a strict grant reviewer scoring a proposal section.

Score on a scale of 0–100 based on:
- Alignment with grant priorities and stated focus areas (30 pts)
- Use of the funder's specific vocabulary and language (20 pts)
- Specificity: numbers, names, dates — no vague statements (25 pts)
- Clarity and persuasiveness for a non-expert reviewer (25 pts)

Be strict. A score above 80 requires explicit evidence of all four criteria.
A score above 90 requires the section to be genuinely outstanding.

Return ONLY a JSON object with exactly these two keys:
{{
  "score": <integer 0-100>,
  "feedback": "<max 2 sentences identifying the specific weaknesses>"
}}

No markdown fences. No preamble."""),
    ("user", """GRANT TITLE: {grant_title}
GRANT AGENCY: {grant_agency}
GRANT PRIORITIES: {grant_focus}
FUNDER VOCABULARY: {funder_vocab}

SECTION TITLE: {section_title}

SECTION CONTENT:
{content}"""),
])


def score_section(
    section_key:   str,
    section_title: str,
    content:       str,
    grant:         dict,
    funder_vocab:  list[str],
) -> dict:
    vocab_str = ", ".join(funder_vocab[:10]) if funder_vocab else "None."

    # Fresh instance per score call — low temperature, json_object mode
    llm      = _get_scorer_llm()
    chain    = SCORING_PROMPT | llm
    response = chain.invoke({
        "grant_title":   grant.get("title", ""),
        "grant_agency":  grant.get("agency", ""),
        "grant_focus":   grant.get("focus_areas", grant.get("description", "")[:300]),
        "funder_vocab":  vocab_str,
        "section_title": section_title,
        "content":       content,
    })

    raw = response.content.strip()

    json_match = re.search(r'(\{.*\})', raw, re.DOTALL)
    if json_match:
        raw = json_match.group(1)
    raw = re.sub(r',\s*}', '}', raw)

    try:
        result = json.loads(raw)
        score  = int(result.get("score", 50))
        return {
            "score":    max(0, min(100, score)),
            "feedback": result.get("feedback", "No feedback provided."),
        }
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        log.warning("scoring_agent: parse failed - %s\nRaw: %s", e, raw)
        score_match    = re.search(r'"score":\s*(\d+)', raw)
        fallback_score = int(score_match.group(1)) if score_match else 50
        return {
            "score":    fallback_score,
            "feedback": "Analysis complete. (Structure was repaired by system).",
        }


def needs_retry(score: int, retry_count: int) -> bool:
    return score < SCORE_THRESHOLD and retry_count < MAX_RETRIES


def is_flagged(score: int, retry_count: int) -> bool:
    return score < SCORE_THRESHOLD and retry_count >= MAX_RETRIES