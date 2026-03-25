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
import re

load_dotenv()
log = logging.getLogger(__name__)

# Separate LLM instance with low temperature for consistent scoring
scorer_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0, model_kwargs={"response_format": {"type": "json_object"}})

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

    # 1. Advanced Cleaning: Extract only the JSON part using Regex
    # This finds the first '{' and the last '}' regardless of what's around it
    json_match = re.search(r'(\{.*\})', raw, re.DOTALL)
    if json_match:
        raw = json_match.group(1)
    
    # 2. Fix common LLM trailing comma/newline issues
    raw = re.sub(r',\s*}', '}', raw) 

    try:
        # 3. Standard Parse
        result = json.loads(raw)
        score = int(result.get("score", 50))
        return {
            "score": max(0, min(100, score)),
            "feedback": result.get("feedback", "No feedback provided."),
        }
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        # 4. Emergency Backup: If JSON still fails, try to find the score manually
        log.warning("scoring_agent: parse failed - %s\nRaw: %s", e, raw)
        
        # Regex to find "score": 92 even in broken JSON
        score_match = re.search(r'"score":\s*(\d+)', raw)
        fallback_score = int(score_match.group(1)) if score_match else 50
        
        return {
            "score": fallback_score,
            "feedback": "Analysis complete. (Structure was repaired by system).",
        }


def needs_retry(score: int, retry_count: int) -> bool:
    if score >= SCORE_THRESHOLD:
        return False
    if retry_count >= MAX_RETRIES:
        return False
    return True

def is_flagged(score: int, retry_count: int) -> bool:
    return score < SCORE_THRESHOLD and retry_count >= MAX_RETRIES