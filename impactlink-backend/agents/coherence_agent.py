"""
agents/coherence_agent.py

Cross-section coherence check after parallel drafting.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from utils.llm import RotatingGroq
from utils.metrics import timed

load_dotenv()
log = logging.getLogger(__name__)

_RAW_KEYS = os.getenv("GROQ_API_KEY", "")
GROQ_KEYS = [k.strip() for k in _RAW_KEYS.split(",") if k.strip()]

MAX_COHERENCE_FIXES = 2


class CoherenceIssue(BaseModel):
    section: str
    issue: str
    fix: str
    severity: Literal["high", "medium", "low"] = "medium"


class CoherenceReport(BaseModel):
    coherent: bool
    issues: list[CoherenceIssue] = Field(default_factory=list)


COHERENCE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a grant proposal editor checking cross-section consistency.

Compare ALL sections together. Find contradictions or misalignments such as:
- Beneficiary counts that differ across sections
- Budget dollar amounts that don't match the budget narrative
- KPIs in evaluation_plan that don't map to goals_and_objectives
- Activities in proposed_solution missing from budget_narrative
- Executive summary statistics that contradict problem_statement

Return ONLY JSON:
{{
  "coherent": <true if no significant issues, else false>,
  "issues": [
    {{
      "section": "<section_key to fix>",
      "issue": "<what contradicts what>",
      "fix": "<specific edit instruction>",
      "severity": "<high|medium|low>"
    }}
  ]
}}

Return at most 5 issues. Empty issues array if coherent."""),
    ("user", """GRANT: {grant_title} ({grant_agency})

PROPOSAL SECTIONS:
{sections_text}"""),
])


def _get_llm() -> RotatingGroq:
    from config import GROQ_API_KEY

    key = random.choice(GROQ_KEYS) if GROQ_KEYS else GROQ_API_KEY
    return RotatingGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        groq_api_key=key,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def _sections_digest(sections: dict) -> str:
    blocks = []
    for key, result in sections.items():
        title = result.get("title", key)
        content = result.get("content", "")
        snippet = content[:500] + ("..." if len(content) > 500 else "")
        blocks.append(f"=== {key} ({title}) ===\n{snippet}")
    return "\n\n".join(blocks)


def _parse_report(raw: str) -> CoherenceReport:
    text = raw.strip()
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        text = match.group(1)
    text = re.sub(r",\s*}", "}", text)
    data = json.loads(text.strip())
    return CoherenceReport.model_validate(data)


class CoherenceAgent:
    """Validates cross-section alignment after drafting."""

    @staticmethod
    @timed("agent", "check_coherence")
    def check(sections: dict, grant: dict) -> CoherenceReport:
        if not sections:
            return CoherenceReport(coherent=True, issues=[])

        llm = _get_llm()
        chain = COHERENCE_PROMPT | llm
        response = chain.invoke({
            "grant_title": grant.get("title", ""),
            "grant_agency": grant.get("agency", ""),
            "sections_text": _sections_digest(sections),
        })

        try:
            return _parse_report(response.content)
        except (json.JSONDecodeError, ValueError) as e:
            log.warning("CoherenceAgent: parse failed — %s", e)
            return CoherenceReport(coherent=True, issues=[])

    @staticmethod
    def top_fixes(report: CoherenceReport, limit: int = MAX_COHERENCE_FIXES) -> list[CoherenceIssue]:
        severity_rank = {"high": 0, "medium": 1, "low": 2}
        sorted_issues = sorted(
            report.issues,
            key=lambda i: severity_rank.get(i.severity, 2),
        )
        return sorted_issues[:limit]
