"""
agents/tools/budget_consistency.py

Deterministic check: narrative dollar amounts and personnel claims vs budget engine.
"""

from __future__ import annotations

import re
import logging
from typing import Any

from utils.metrics import timed

log = logging.getLogger(__name__)

_PERSONNEL_RE = re.compile(
    r"(\d+)\s+(?:full[- ]time\s+)?(?:field\s+)?(?:workers?|staff(?:\s+members?)?|FTEs?|personnel|employees?)",
    re.IGNORECASE,
)
_TOTAL_RE = re.compile(
    r"(?:total\s+(?:project\s+)?(?:budget|cost|request)|request(?:ing)?)\s*(?:of\s*)?\$?([\d,]+(?:\.\d+)?)\s*([kKmM])?",
    re.IGNORECASE,
)
_DOLLAR_RE = re.compile(r"\$([\d,]+(?:\.\d+)?)\s*([kKmM])?")


def _parse_amount(num_str: str, suffix: str | None = None) -> int:
    num = float(num_str.replace(",", ""))
    if suffix:
        s = suffix.lower()
        if s == "k":
            num *= 1_000
        elif s == "m":
            num *= 1_000_000
    return int(num)


def _extract_claimed_totals(text: str) -> list[int]:
    totals: list[int] = []
    for match in _TOTAL_RE.finditer(text):
        try:
            totals.append(_parse_amount(match.group(1), match.group(2)))
        except ValueError:
            continue
    return totals


def _extract_personnel_counts(text: str) -> list[int]:
    return [int(m.group(1)) for m in _PERSONNEL_RE.finditer(text)]


def _load_budget(profile: dict, grant: dict) -> dict | None:
    from agents.budget_injector import _parse_budget_string
    from services.budget.generator import generate_budget

    budget_val = profile.get("total_budget", "")
    grant_ceiling = grant.get("award_ceiling", 0) if isinstance(grant, dict) else 0
    grant_doc = grant.get("description", "") if isinstance(grant, dict) else ""
    max_budget = _parse_budget_string(budget_val) or grant_ceiling or 100_000

    try:
        budget_data = generate_budget(profile, max_budget, grant_doc)
    except Exception as e:
        log.warning("check_budget_consistency: budget engine failed — %s", e)
        return None
    if "error" in budget_data:
        log.warning("check_budget_consistency: budget engine error — %s", budget_data["error"])
        return None
    return budget_data


@timed("tool", "check_budget_consistency")
def check_budget_consistency(
    section_content: str,
    profile: dict,
    grant: dict,
) -> dict[str, Any]:
    """
    Verify narrative claims against the deterministic budget engine output.

    Returns:
        {
            "consistent": bool,
            "issues": [{"claim", "expected", "severity"}],
            "budget_total": int,
        }
    """
    budget_data = _load_budget(profile, grant)
    if not budget_data:
        return {"consistent": True, "issues": [], "budget_total": 0}

    items = budget_data.get("items", [])
    budget_total = int(budget_data.get("total_requested", 0) or 0)
    issues: list[dict[str, str]] = []

    ceiling = int(grant.get("award_ceiling", 0) or 0)
    if ceiling and budget_total > ceiling:
        issues.append({
            "claim": f"Budget engine total ${budget_total:,}",
            "expected": f"Grant award ceiling ${ceiling:,}",
            "severity": "high",
        })

    for claimed in _extract_claimed_totals(section_content):
        if budget_total and abs(claimed - budget_total) / max(budget_total, 1) > 0.12:
            issues.append({
                "claim": f"Narrative states total ${claimed:,}",
                "expected": f"Pre-calculated budget total ${budget_total:,}",
                "severity": "high",
            })

    personnel_items = [
        i for i in items
        if any(k in (i.get("category") or "").lower() for k in ("personnel", "staff", "salary", "wage"))
    ]
    if personnel_items and _extract_personnel_counts(section_content):
        budget_roles = sum(
            1 for i in personnel_items
            if int(i.get("quantity", 1) or 1) > 0
        )
        for count in _extract_personnel_counts(section_content):
            if budget_roles and count > budget_roles + 1:
                issues.append({
                    "claim": f"Narrative mentions {count} staff/workers",
                    "expected": f"Budget has ~{budget_roles} personnel line item(s)",
                    "severity": "medium",
                })

    large_amounts = []
    for match in _DOLLAR_RE.finditer(section_content):
        try:
            amt = _parse_amount(match.group(1), match.group(2))
            if amt >= 10_000:
                large_amounts.append(amt)
        except ValueError:
            continue

    item_amounts = {int(i.get("amount", 0) or 0) for i in items}
    for amt in large_amounts:
        if budget_total and amt > budget_total * 1.1:
            issues.append({
                "claim": f"Narrative mentions ${amt:,}",
                "expected": f"No single line exceeds total budget ${budget_total:,}",
                "severity": "medium",
            })
        elif item_amounts and amt not in item_amounts and not any(
            abs(amt - ia) / max(ia, 1) < 0.08 for ia in item_amounts if ia
        ):
            if amt != budget_total:
                issues.append({
                    "claim": f"Narrative mentions ${amt:,}",
                    "expected": "Amount not found in budget line items",
                    "severity": "low",
                })

    return {
        "consistent": len(issues) == 0,
        "issues": issues,
        "budget_total": budget_total,
    }


def format_consistency_issues(result: dict) -> str:
    """Format tool output for injection into rewrite feedback."""
    if result.get("consistent"):
        return ""
    lines = ["Budget consistency tool found these mismatches:"]
    for issue in result.get("issues", []):
        lines.append(
            f"- [{issue.get('severity', 'medium')}] {issue['claim']} "
            f"(expected: {issue['expected']})"
        )
    return "\n".join(lines)
