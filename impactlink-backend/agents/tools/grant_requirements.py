"""
agents/tools/grant_requirements.py

Lookup grant-specific requirements relevant to each proposal section.
"""

from __future__ import annotations

from typing import Any

from utils.metrics import timed

SECTION_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "executive_summary": {
        "required_elements": [
            "local problem hook with statistic",
            "organization credibility",
            "exact dollar ask and 3 measurable outcomes",
        ],
        "word_target_hint": "250–300 words",
    },
    "problem_statement": {
        "required_elements": [
            "human story opening",
            "local (not national) data",
            "root causes and service gap",
        ],
        "word_target_hint": "400–500 words",
    },
    "goals_and_objectives": {
        "required_elements": [
            "SMART objectives",
            "alignment with funder priorities",
            "timeline for each objective",
        ],
        "word_target_hint": "300–400 words",
    },
    "proposed_solution": {
        "required_elements": [
            "3–5 specific activities with who leads each",
            "theory of change / activity → outcome chain",
            "partnerships if applicable",
        ],
        "word_target_hint": "450–550 words",
    },
    "target_beneficiaries": {
        "required_elements": [
            "headcount with demographics",
            "equity / priority populations",
            "community engagement approach",
        ],
        "word_target_hint": "300–400 words",
    },
    "organizational_capacity": {
        "required_elements": [
            "track record",
            "relevant expertise",
            "financial management capacity",
        ],
        "word_target_hint": "350–450 words",
    },
    "evaluation_plan": {
        "required_elements": [
            "KPIs tied to objectives",
            "data collection methods",
            "reporting cadence to funder",
        ],
        "word_target_hint": "350–450 words",
    },
    "budget_narrative": {
        "required_elements": [
            "narrative matches pre-calculated budget table",
            "justification per major line item",
            "match/leverage if required",
        ],
        "word_target_hint": "300–400 words",
    },
    "sustainability": {
        "required_elements": [
            "funding after grant period",
            "diversified revenue sources",
            "community ownership",
        ],
        "word_target_hint": "250–350 words",
    },
    "equity_statement": {
        "required_elements": [
            "equity in project design",
            "organizational equity practice",
            "environmental justice if relevant",
        ],
        "word_target_hint": "250–350 words",
    },
}


@timed("tool", "get_grant_requirement")
def get_grant_requirement(section_key: str, grant: dict) -> dict[str, Any]:
    """Return eligibility, limits, and required elements for a section."""
    section_meta = SECTION_REQUIREMENTS.get(section_key, {})
    description = grant.get("description", "") or ""

    return {
        "section_key": section_key,
        "grant_title": grant.get("title", ""),
        "grant_agency": grant.get("agency", ""),
        "focus_areas": grant.get("focus_areas") or description[:600],
        "eligibility": grant.get("eligibility", []),
        "award_ceiling": grant.get("award_ceiling", 0),
        "award_floor": grant.get("award_floor", 0),
        "match_required": grant.get("cost_sharing_required", False),
        "required_elements": section_meta.get("required_elements", []),
        "word_target_hint": section_meta.get("word_target_hint", ""),
        "application_tip": grant.get("application_tip", ""),
        "close_date": grant.get("close_date", ""),
    }


def format_grant_requirements(req: dict) -> str:
    """Format tool output for prompt injection."""
    lines = [
        f"Grant: {req.get('grant_title')} ({req.get('grant_agency')})",
    ]
    if req.get("focus_areas"):
        lines.append(f"Funder priorities: {req['focus_areas'][:400]}")
    if req.get("award_ceiling"):
        lines.append(f"Award ceiling: ${int(req['award_ceiling']):,}")
    if req.get("match_required"):
        lines.append("Cost sharing / match is required.")
    if req.get("required_elements"):
        lines.append("Required elements for this section:")
        for el in req["required_elements"]:
            lines.append(f"  - {el}")
    if req.get("word_target_hint"):
        lines.append(f"Target length: {req['word_target_hint']}")
    if req.get("application_tip"):
        lines.append(f"Application tip: {req['application_tip']}")
    return "\n".join(lines)
