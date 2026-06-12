"""
agents/planning_agent.py

PlanningAgent analyzes the grant + NGO profile before section drafting and
produces a structured DraftingPlan that flows into each SectionSubgraph.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from agents.prompts import SECTIONS
from utils.llm import RotatingGroq
from utils.metrics import timed

load_dotenv()
log = logging.getLogger(__name__)

_RAW_KEYS = os.getenv("GROQ_API_KEY", "")
GROQ_KEYS = [k.strip() for k in _RAW_KEYS.split(",") if k.strip()]

# Phased drafting waves — later waves receive summaries from earlier waves.
DRAFTING_WAVES: list[list[str]] = [
    ["problem_statement", "proposed_solution", "target_beneficiaries"],
    ["goals_and_objectives", "evaluation_plan", "organizational_capacity", "budget_narrative"],
    ["executive_summary", "sustainability", "equity_statement"],
]

PRIOR_SECTION_SNIPPET_CHARS = 350
PRIOR_SECTIONS_MAX_CHARS = 1200


class SectionPriority(BaseModel):
    key: str
    priority: int = Field(ge=1, le=10)
    critical_because: str
    evidence_needed: list[str] = Field(default_factory=list)
    funder_phrases_to_use: list[str] = Field(default_factory=list)


class CrossSectionDependency(BaseModel):
    if_section: str
    affects: str
    because: str


class DraftingPlan(BaseModel):
    section_priorities: list[SectionPriority]
    cross_section_dependencies: list[CrossSectionDependency] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    scoring_rubric_inference: dict[str, str] = Field(default_factory=dict)

    def get_section_priority(self, section_key: str) -> Optional[SectionPriority]:
        for item in self.section_priorities:
            if item.key == section_key:
                return item
        return None

    def to_section_context(self, section_key: str) -> str:
        """Format plan guidance for injection into a section draft prompt."""
        priority = self.get_section_priority(section_key)
        lines: list[str] = []

        if priority:
            lines.append(f"Priority rank: {priority.priority}/10")
            lines.append(f"Critical because: {priority.critical_because}")
            if priority.evidence_needed:
                lines.append(
                    "Evidence needed: " + "; ".join(priority.evidence_needed)
                )
            if priority.funder_phrases_to_use:
                lines.append(
                    "Funder phrases to weave in: "
                    + ", ".join(priority.funder_phrases_to_use)
                )

        deps = [
            d for d in self.cross_section_dependencies
            if d.affects == section_key or d.if_section == section_key
        ]
        if deps:
            lines.append("Cross-section dependencies:")
            for d in deps:
                lines.append(f"  - {d.if_section} → {d.affects}: {d.because}")

        if self.red_flags:
            lines.append("Proposal red flags to address or avoid:")
            for flag in self.red_flags:
                lines.append(f"  - {flag}")

        if self.scoring_rubric_inference:
            rubric = ", ".join(
                f"{k}: {v}" for k, v in self.scoring_rubric_inference.items()
            )
            lines.append(f"Inferred funder scoring emphasis: {rubric}")

        return "\n".join(lines)


PLAN_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a senior grant strategist preparing a drafting plan before
any proposal sections are written.

Read the grant requirements and NGO profile. Produce a structured plan that tells
section writers what matters most for THIS specific funder.

Section keys you must cover (one entry per key in section_priorities):
{section_keys}

Return ONLY a JSON object with this exact structure:
{{
  "section_priorities": [
    {{
      "key": "problem_statement",
      "priority": 1,
      "critical_because": "why this section matters for this funder",
      "evidence_needed": ["local statistic type", "demographic data"],
      "funder_phrases_to_use": ["exact phrase from RFP"]
    }}
  ],
  "cross_section_dependencies": [
    {{
      "if_section": "problem_statement",
      "affects": "executive_summary",
      "because": "summary must reference statistics established in need section"
    }}
  ],
  "red_flags": [
    "specific mismatch or risk, e.g. budget exceeds award ceiling"
  ],
  "scoring_rubric_inference": {{
    "alignment": "what the funder weights heavily",
    "vocabulary": "specific language reviewers look for",
    "specificity": "data/evidence expectations",
    "persuasion": "tone and framing expectations"
  }}
}}

Rules:
- priority 1 = most critical for this funder; 10 = least
- Include all 10 section keys in section_priorities
- red_flags: 0–5 concrete risks; empty list if none
- Be specific to this grant — no generic advice"""),
    ("user", """GRANT TITLE: {grant_title}
GRANT AGENCY: {grant_agency}
GRANT DESCRIPTION:
{grant_description}

FUNDER VOCABULARY:
{funder_vocab}

NGO PROFILE:
{profile}"""),
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


def _default_plan(funder_vocab: list[str]) -> DraftingPlan:
    vocab_sample = funder_vocab[:5] if funder_vocab else []
    return DraftingPlan(
        section_priorities=[
            SectionPriority(
                key=s["key"],
                priority=min(i + 1, 10),
                critical_because=f"Required section: {s['title']}",
                evidence_needed=[],
                funder_phrases_to_use=vocab_sample,
            )
            for i, s in enumerate(SECTIONS)
        ],
        cross_section_dependencies=[
            CrossSectionDependency(
                if_section="problem_statement",
                affects="executive_summary",
                because="Summary must reference need statistics from problem statement",
            ),
            CrossSectionDependency(
                if_section="proposed_solution",
                affects="budget_narrative",
                because="Budget line items must match described activities",
            ),
            CrossSectionDependency(
                if_section="goals_and_objectives",
                affects="evaluation_plan",
                because="KPIs must map to stated objectives",
            ),
        ],
        red_flags=[],
        scoring_rubric_inference={
            "alignment": "Match funder stated priorities",
            "vocabulary": "Mirror RFP language",
            "specificity": "Local data, numbers, names",
            "persuasion": "Clear outcomes for non-expert reviewers",
        },
    )


def _parse_plan_json(raw: str) -> DraftingPlan:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 1)[-1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]

    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        text = match.group(1)
    text = re.sub(r",\s*}", "}", text)

    data = json.loads(text.strip())
    return DraftingPlan.model_validate(data)


def append_agent_trace(
    trace: list[dict],
    agent: str,
    decision: str,
    metadata: Optional[dict] = None,
) -> list[dict]:
    entry = {"agent": agent, "decision": decision}
    if metadata:
        entry["metadata"] = metadata
    return [*trace, entry]


def summarize_prior_sections(
    sections: dict,
    *,
    max_chars: int = PRIOR_SECTIONS_MAX_CHARS,
    snippet_chars: int = PRIOR_SECTION_SNIPPET_CHARS,
) -> str:
    """Build rolling context from completed section drafts."""
    if not sections:
        return ""

    lines: list[str] = []
    total = 0
    for key, result in sections.items():
        title = result.get("title", key.replace("_", " ").title())
        content = result.get("content", "")
        snippet = content[:snippet_chars]
        if len(content) > snippet_chars:
            snippet += "..."
        block = f"### {title}\n{snippet}"
        if total + len(block) > max_chars:
            break
        lines.append(block)
        total += len(block)

    return "\n\n".join(lines)


class PlanningAgent:
    """Produces a structured drafting plan before section generation."""

    @staticmethod
    @timed("agent", "create_drafting_plan")
    def create_plan(
        grant: dict,
        profile: dict,
        funder_vocab: list[str],
    ) -> DraftingPlan:
        section_keys = ", ".join(s["key"] for s in SECTIONS)
        vocab_str = "\n".join(f"- {v}" for v in funder_vocab) or "None extracted."

        llm = _get_llm()
        chain = PLAN_PROMPT | llm
        response = chain.invoke({
            "section_keys": section_keys,
            "grant_title": grant.get("title", ""),
            "grant_agency": grant.get("agency", ""),
            "grant_description": (grant.get("description", "") or "")[:2500],
            "funder_vocab": vocab_str,
            "profile": json.dumps(profile, indent=2)[:2000],
        })

        try:
            return _parse_plan_json(response.content)
        except (json.JSONDecodeError, ValueError) as e:
            log.warning("PlanningAgent: parse failed — %s", e)
            return _default_plan(funder_vocab)
