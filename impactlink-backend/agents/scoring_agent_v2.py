"""
agents/scoring_agent.py

Scores a single proposal section and manages the retry cap.

Scale: 0–100 (not 1–10, to match the existing scoring_agent.py convention).
Threshold: 75 (not 85 — self-scoring bias inflates by 8–12 points;
           75 auto-proceed ≈ 83–87 in unbiased evaluation).
Max retries: 2 per section. After 2 failures, section is flagged for
             human review rather than retrying indefinitely.
"""

import json
import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

# Separate LLM instance with low temperature for consistent scoring
scorer_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

SCORE_THRESHOLD = 75   # auto-proceed above this
MAX_RETRIES     = 2    # hard cap — never retry more than twice

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


# ── Public API ────────────────────────────────────────────────────────────────

def score_section(
    section_key:   str,
    section_title: str,
    content:       str,
    grant:         dict,
    funder_vocab:  list[str],
) -> dict:
    """
    Score one section. Returns {"score": int, "feedback": str}.

    Args:
        section_key:   e.g. "executive_summary" (used for logging)
        section_title: human-readable title
        content:       the section text to score
        grant:         grant dict
        funder_vocab:  extracted vocab list (used to judge vocabulary alignment)

    Returns:
        {"score": int, "feedback": str}
        On parse failure returns {"score": 50, "feedback": "..."} — never crashes.
    """
    vocab_str = ", ".join(funder_vocab[:10]) if funder_vocab else "None."

    chain = SCORING_PROMPT | scorer_llm
    response = chain.invoke({
        "grant_title":  grant.get("title", ""),
        "grant_agency": grant.get("agency", ""),
        "grant_focus":  grant.get("focus_areas", grant.get("description", "")[:300]),
        "funder_vocab": vocab_str,
        "section_title": section_title,
        "content":      content,
    })

    raw = response.content.strip()
    # Strip markdown fences defensively
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]

    try:
        result = json.loads(raw.strip())
        score = int(result.get("score", 50))
        # Clamp to valid range
        score = max(0, min(100, score))
        return {
            "score":    score,
            "feedback": result.get("feedback", "No feedback provided."),
        }
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        log.warning(
            "scoring_agent: parse failed for section '%s' — %s\nRaw: %s",
            section_key, e, raw,
        )
        return {
            "score":    50,
            "feedback": f"Score parsing failed. Raw output: {raw[:200]}",
        }


def needs_retry(score: int, retry_count: int) -> bool:
    """
    Returns True if this section should be rewritten.
    False if score is good enough OR retry cap is reached.
    """
    if score >= SCORE_THRESHOLD:
        return False
    if retry_count >= MAX_RETRIES:
        return False   # cap reached — flag for human review instead
    return True


def is_flagged(score: int, retry_count: int) -> bool:
    """
    Returns True if the section should be flagged for human attention.
    A section is flagged when it failed all retries and still scores low.
    """
    return score < SCORE_THRESHOLD and retry_count >= MAX_RETRIES
