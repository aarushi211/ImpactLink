"""
scripts/evaluate_logic.py

Deterministic evaluation for the budget engine.
Uses budget cases from eval_scenarios.json plus stress-test edge cases.

Usage:
    python scripts/evaluate_logic.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from services.budget.generator import generate_budget

from eval_common import load_scenarios, print_header, save_report


STRESS_CASES = [
    {
        "name": "Extreme Over-Budget Request (Stress Test)",
        "max_award": 50000,
        "proposal": {
            "project_title": "Massive Reforestation",
            "key_activities": ["Hire 50 Project Managers", "Buy 10 Trucks"],
            "geographic_focus": ["San Francisco, CA"],
            "budget_breakdown": ["Personnel", "Travel"],
        },
        "expect_error": True,
    },
    {
        "name": "Low Wage Region Compliance",
        "max_award": 25000,
        "proposal": {
            "project_title": "Rural Education",
            "key_activities": ["Tutoring"],
            "geographic_focus": ["Rural Alabama"],
            "budget_breakdown": ["Personnel"],
        },
        "expect_error": False,
    },
]


def _proposal_from_scenario(scenario: dict) -> dict:
    slots = scenario["slots"]
    profile = {
        "project_title": scenario["name"],
        "key_activities": [slots.get("activities", "")],
        "geographic_focus": [slots.get("geography", "")],
        "budget_breakdown": ["Personnel", "Equipment", "Supplies", "Outreach"],
        "total_budget": slots.get("budget_total", ""),
        "target_beneficiaries": [slots.get("beneficiaries", "")],
    }
    return profile


def _run_budget_case(name: str, proposal: dict, max_award: int, expect_error: bool = False) -> dict:
    import io
    from contextlib import redirect_stdout, redirect_stderr

    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            budget = generate_budget(proposal, max_award)

        if "error" in budget:
            if expect_error:
                return {"name": name, "status": "PASS", "detail": budget.get("details", "caught violation")}
            return {"name": name, "status": "FAIL", "detail": budget.get("details", "unexpected error")}

        total = budget.get("total_requested", 0)
        items_sum = sum(item.get("amount", 0) for item in budget.get("items", []))
        math_pass = total == max_award == items_sum

        if math_pass:
            return {
                "name": name,
                "status": "PASS",
                "detail": f"total=${total:,}, items_sum=${items_sum:,}",
                "total_requested": total,
            }
        return {
            "name": name,
            "status": "FAIL",
            "detail": f"math mismatch total={total} sum={items_sum} expected={max_award}",
        }
    except Exception as exc:
        if expect_error:
            return {"name": name, "status": "PASS", "detail": f"caught exception: {exc}"}
        return {"name": name, "status": "CRASH", "detail": str(exc)}


def run_evaluation() -> dict:
    cases = []

    for scenario in load_scenarios():
        budget_cfg = scenario.get("budget") or {}
        max_award = budget_cfg.get("max_award")
        if not max_award:
            continue
        cases.append({
            "name": f"Scenario: {scenario['id']}",
            "max_award": max_award,
            "proposal": _proposal_from_scenario(scenario),
            "expect_error": False,
        })

    cases.extend(STRESS_CASES)

    results = [_run_budget_case(**case) for case in cases]
    passed = sum(1 for r in results if r["status"] == "PASS")
    return {
        "eval_type": "budget_logic",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "aggregate": {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "pass_rate": round(passed / max(len(results), 1), 3),
        },
        "results": results,
    }


def main() -> int:
    print_header("ImpactLink Budget Logic Evaluation")
    report = run_evaluation()

    for row in report["results"]:
        icon = "PASS" if row["status"] == "PASS" else row["status"]
        print(f"  [{icon}] {row['name']}: {row['detail']}")

    agg = report["aggregate"]
    print(f"\nPass rate: {agg['passed']}/{agg['total']} ({agg['pass_rate']:.0%})")

    out_path = save_report(
        f"budget_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        report,
    )
    print(f"Report saved: {out_path}")
    return 0 if agg["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
