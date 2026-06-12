"""
agents/scoring_agent.py

LLM-as-a-Judge scorer that returns structured routing decisions, not just a score.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
from typing import Literal, Optional

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

from utils.llm import RotatingGroq
from utils.metrics import timed

load_dotenv()
log = logging.getLogger(__name__)

_RAW_KEYS = os.getenv("GROQ_API_KEY", "")
GROQ_KEYS = [k.strip() for k in _RAW_KEYS.split(",") if k.strip()]

SCORE_THRESHOLD = 75
MAX_RETRIES = 2

Routing = Literal["approve", "targeted_rewrite", "needs_tool_call", "escalate"]


class TargetedFeedback(BaseModel):
    issue: str
    fix: str
    severity: Literal["high", "medium", "low"] = "medium"
    paragraph: Optional[int] = None


class ScoringDecision(BaseModel):
    score: int = Field(ge=0, le=100)
    routing: Routing
    feedback: str
    targeted_feedback: list[TargetedFeedback] = Field(default_factory=list)
    tool_to_call: Optional[str] = None
    cross_section_impact: list[str] = Field(default_factory=list)

    @field_validator("score", mode="before")
    @classmethod
    def _clamp_score(cls, v):
        return max(0, min(100, int(v)))


SCORING_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a strict grant reviewer scoring a proposal section.

Score on a scale of 0–100 based on:
- Alignment with grant priorities and stated focus areas (30 pts)
- Use of the funder's specific vocabulary and language (20 pts)
- Specificity: numbers, names, dates — no vague statements (25 pts)
- Clarity and persuasiveness for a non-expert reviewer (25 pts)

Be strict. A score above 80 requires explicit evidence of all four criteria.

Return ONLY a JSON object with this exact structure:
{{
  "score": <integer 0-100>,
  "routing": "<approve|targeted_rewrite|needs_tool_call|escalate>",
  "feedback": "<max 2 sentences summarizing weaknesses>",
  "targeted_feedback": [
    {{
      "issue": "<specific weakness>",
      "fix": "<specific fix instruction>",
      "severity": "<high|medium|low>",
      "paragraph": <optional integer paragraph number or null>
    }}
  ],
  "tool_to_call": "<check_budget_consistency|get_grant_requirement|null>",
  "cross_section_impact": [
    "<if this section changes X, section Y must update because Z>"
  ]
}}

Routing rules:
- score >= 75 → routing MUST be "approve"
- score < 75 and fixable with text edits → "targeted_rewrite"
- score < 75 and budget numbers/personnel don't match table → "needs_tool_call" with tool_to_call "check_budget_consistency"
- score < 50 after multiple issues that need human judgment → "escalate"

No markdown fences. No preamble."""),
    ("user", """SECTION KEY: {section_key}
GRANT TITLE: {grant_title}
GRANT AGENCY: {grant_agency}
GRANT PRIORITIES: {grant_focus}
FUNDER VOCABULARY: {funder_vocab}

SECTION TITLE: {section_title}

SECTION CONTENT:
{content}"""),
])


def _get_scorer_llm() -> RotatingGroq:
    from config import GROQ_API_KEY

    key = random.choice(GROQ_KEYS) if GROQ_KEYS else GROQ_API_KEY
    return RotatingGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        groq_api_key=key,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        text = match.group(1)
    text = re.sub(r",\s*}", "}", text)
    return json.loads(text.strip())


def _fallback_decision(score: int, feedback: str, section_key: str) -> ScoringDecision:
    if score >= SCORE_THRESHOLD:
        routing: Routing = "approve"
    elif section_key == "budget_narrative":
        routing = "needs_tool_call"
    else:
        routing = "targeted_rewrite"

    return ScoringDecision(
        score=score,
        routing=routing,
        feedback=feedback,
        targeted_feedback=[],
        tool_to_call="check_budget_consistency" if routing == "needs_tool_call" else None,
        cross_section_impact=[],
    )


def route_after_scoring(
    decision: ScoringDecision | dict,
    retry_count: int,
    *,
    max_retries: int = MAX_RETRIES,
) -> Routing:
    """Resolve the graph edge after scoring."""
    if isinstance(decision, dict):
        decision = ScoringDecision.model_validate(decision)

    if decision.score >= SCORE_THRESHOLD:
        return "approve"
    if retry_count >= max_retries:
        return "escalate"
    if decision.routing == "approve":
        return "targeted_rewrite"
    return decision.routing


def format_targeted_feedback(decision: ScoringDecision | dict) -> str:
    """Format structured feedback for the rewrite agent."""
    if isinstance(decision, dict):
        decision = ScoringDecision.model_validate(decision)

    lines = [decision.feedback]
    for item in decision.targeted_feedback:
        para = f" (paragraph {item.paragraph})" if item.paragraph else ""
        lines.append(f"- [{item.severity.upper()}]{para} {item.issue} → Fix: {item.fix}")
    if decision.cross_section_impact:
        lines.append("Cross-section impacts:")
        for impact in decision.cross_section_impact:
            lines.append(f"  - {impact}")
    return "\n".join(lines)


@timed("agent", "score_section_decision")
def score_section_decision(
    section_key: str,
    section_title: str,
    content: str,
    grant: dict,
    funder_vocab: list[str],
) -> dict:
    """Score a section and return a structured ScoringDecision dict."""
    vocab_str = ", ".join(funder_vocab[:10]) if funder_vocab else "None."

    llm = _get_scorer_llm()
    chain = SCORING_PROMPT | llm
    response = chain.invoke({
        "section_key": section_key,
        "grant_title": grant.get("title", ""),
        "grant_agency": grant.get("agency", ""),
        "grant_focus": grant.get("focus_areas", grant.get("description", "")[:300]),
        "funder_vocab": vocab_str,
        "section_title": section_title,
        "content": content,
    })

    try:
        data = _parse_json(response.content)
        decision = ScoringDecision.model_validate(data)

        if decision.score >= SCORE_THRESHOLD:
            decision = decision.model_copy(update={"routing": "approve"})
        elif decision.routing == "approve":
            decision = decision.model_copy(update={"routing": "targeted_rewrite"})

        return decision.model_dump()
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        log.warning("scoring_agent: decision parse failed — %s", e)
        score_match = re.search(r'"score":\s*(\d+)', response.content)
        fallback_score = int(score_match.group(1)) if score_match else 50
        return _fallback_decision(
            fallback_score,
            "Scoring structure was repaired by system.",
            section_key,
        ).model_dump()


@timed("agent", "score_section")
def score_section(
    section_key: str,
    section_title: str,
    content: str,
    grant: dict,
    funder_vocab: list[str],
) -> dict:
    """Backward-compatible wrapper returning score + feedback only."""
    decision = score_section_decision(
        section_key, section_title, content, grant, funder_vocab
    )
    return {
        "score": decision["score"],
        "feedback": decision["feedback"],
    }


def needs_retry(score: int, retry_count: int) -> bool:
    return score < SCORE_THRESHOLD and retry_count < MAX_RETRIES


def is_flagged(score: int, retry_count: int) -> bool:
    return score < SCORE_THRESHOLD and retry_count >= MAX_RETRIES
