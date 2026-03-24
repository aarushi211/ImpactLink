"""
agents/budget_injector.py

Generates a pre-calculated, mathematically correct budget table
to inject into the budget_narrative section prompt.

Extracted from prompts.py._inject_budget_calculator() — one job, one file.

Returns a formatted markdown table string, or None if calculation fails.
The caller (draft node in flows) decides what to do with it.
"""

import re
import logging

log = logging.getLogger(__name__)


def get_budget_context(proposal: dict, grant: dict) -> str | None:
    """
    Generate a pre-calculated budget table for the budget_narrative section.

    Args:
        proposal: the NGO profile / slot-derived profile dict
        grant:    the grant dict

    Returns:
        A markdown table string to inject into the section prompt,
        or None if the budget service fails or is unavailable.
        Caller should treat None as "let the LLM estimate instead."
    """
    try:
        from services.budget.generator import generate_budget

        budget_val    = proposal.get("total_budget", "")
        grant_ceiling = grant.get("award_ceiling", 0) if isinstance(grant, dict) else 0
        grant_doc     = grant.get("description", "") if isinstance(grant, dict) else ""
        max_budget    = _parse_budget_string(budget_val) or grant_ceiling or 100_000

        budget_data = generate_budget(proposal, max_budget, grant_doc)

        if "error" in budget_data:
            log.warning("budget_injector: budget service returned error — %s",
                        budget_data["error"])
            return None

        items = budget_data.get("items", [])
        if not items:
            log.warning("budget_injector: no items returned from budget service")
            return None

        lines = [
            "| Category | Amount (USD) | Notes |",
            "|---|---|---|",
        ]
        for item in items:
            category = item.get("category", "")
            amount   = item.get("amount", 0)
            notes    = item.get("notes") or item.get("description") or ""
            lines.append(f"| {category} | ${amount:,} | {notes} |")

        total = budget_data.get("total_requested", 0)
        lines.append(f"| **TOTAL** | **${total:,}** | |")

        return "\n".join(lines)

    except ImportError:
        log.warning("budget_injector: services.budget.generator not available")
        return None
    except Exception as e:
        log.error("budget_injector: unexpected error — %s", e, exc_info=True)
        return None


def _parse_budget_string(val: str) -> int:
    """
    Parse a human-entered budget string into an integer dollar amount.

    Handles: "$150,000", "150k", "1.5m", "1.5 million", "150000"
    Returns 0 if parsing fails.
    """
    if not val:
        return 0

    clean = re.sub(r'[$,]', '', str(val).lower().strip())
    match = re.search(r'([\d.]+)\s*(k|m|million|thousand)?', clean)
    if not match:
        return 0

    num    = float(match.group(1))
    suffix = match.group(2)

    if suffix in ('k', 'thousand'):
        num *= 1_000
    elif suffix in ('m', 'million'):
        num *= 1_000_000

    return int(num)