"""
scripts/evaluate_logic.py

Deterministic evaluation for the budget engine.

Usage:
    python scripts/evaluate_logic.py              # full pipeline (needs GROQ_API_KEY)
    python scripts/evaluate_logic.py --offline    # compliance math only (CI-safe)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

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
    return {
        "project_title": scenario["name"],
        "key_activities": [slots.get("activities", "")],
        "geographic_focus": [slots.get("geography", "")],
        "budget_breakdown": ["Personnel", "Equipment", "Supplies", "Outreach"],
        "total_budget": slots.get("budget_total", ""),
        "target_beneficiaries": [slots.get("beneficiaries", "")],
    }


def _run_budget_case(name: str, proposal: dict, max_award: int, expect_error: bool = False) -> dict:
    import io
    from contextlib import redirect_stdout, redirect_stderr

    from services.budget.generator import generate_budget

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


def run_offline_evaluation() -> dict:
    """Pure-Python budget checks — no LLM or API keys required."""
    from services.budget.compliance import enforce_grant_rules
    from services.budget.constants import INDIRECT_CATEGORIES_DEFAULT
    from services.budget.models import BudgetLineItem, CategoryType, ComplianceViolation, GrantRules
    from services.budget.personnel import ComplianceViolation as PersonnelComplianceViolation
    from services.budget.personnel import PersonnelRole, compute_personnel_budget

    results: list[dict] = []

    # 1) Personnel wage floor math
    roles = [PersonnelRole(role_title="Field Coordinator", fte_count=2.0)]
    items, _ = compute_personnel_budget(roles, min_wage_hourly=20.0, labor_cap=100_000)
    personnel_total = sum(i.amount for i in items)
    ok = personnel_total == 83_200  # 2 FTE × 2080 hrs × $20/hr
    results.append({
        "name": "Personnel wage floor math",
        "status": "PASS" if ok else "FAIL",
        "detail": f"total=${personnel_total:,}, expected=$83,200",
    })

    # 2) Labor cap blocks impossible headcount
    many_roles = [
        PersonnelRole(role_title=f"Staff {i}", fte_count=1.0)
        for i in range(20)
    ]
    try:
        compute_personnel_budget(many_roles, min_wage_hourly=32.0, labor_cap=37_500)
        results.append({
            "name": "Labor cap enforcement",
            "status": "FAIL",
            "detail": "expected ComplianceViolation",
        })
    except PersonnelComplianceViolation as exc:
        results.append({
            "name": "Labor cap enforcement",
            "status": "PASS",
            "detail": str(exc)[:120],
        })

    # 3) Indirect cost cap trimming
    max_budget = 100_000
    rules = GrantRules(indirect_cost_cap_pct=15.0)
    line_items = [
        BudgetLineItem(category=CategoryType.FIELD_STAFF, description="Lead", amount=55_000, fte_count=1.0),
        BudgetLineItem(category=CategoryType.PROGRAM_ACTIVITIES, description="Workshops", amount=25_000),
        BudgetLineItem(category=CategoryType.INDIRECT_OVERHEAD, description="Admin", amount=20_000),
    ]
    fixed, report = enforce_grant_rules(
        line_items,
        max_budget,
        rules,
        INDIRECT_CATEGORIES_DEFAULT,
        set(),
        labor_cap=80_000,
        min_wage_hourly=20.0,
    )
    indirect_total = sum(i.amount for i in fixed if i.category in INDIRECT_CATEGORIES_DEFAULT)
    cap_ok = indirect_total <= int(max_budget * 0.15)
    results.append({
        "name": "Indirect cost cap trim",
        "status": "PASS" if cap_ok and report.get("violations_fixed") else "FAIL",
        "detail": f"indirect=${indirect_total:,}, cap=$15,000, trimmed={bool(report.get('violations_fixed'))}",
    })

    # 4) Unallowable category hard block
    blocked_items = [
        BudgetLineItem(category=CategoryType.TRAVEL, description="Flights", amount=10_000),
    ]
    rules_block = GrantRules(unallowable_costs=[CategoryType.TRAVEL.value])
    try:
        enforce_grant_rules(
            blocked_items,
            50_000,
            rules_block,
            INDIRECT_CATEGORIES_DEFAULT,
            {CategoryType.TRAVEL},
            labor_cap=40_000,
            min_wage_hourly=20.0,
        )
        results.append({
            "name": "Unallowable cost block",
            "status": "FAIL",
            "detail": "expected ComplianceViolation",
        })
    except ComplianceViolation:
        results.append({
            "name": "Unallowable cost block",
            "status": "PASS",
            "detail": "Travel blocked as expected",
        })

    passed = sum(1 for r in results if r["status"] == "PASS")
    return {
        "eval_type": "budget_logic_offline",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "aggregate": {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "pass_rate": round(passed / max(len(results), 1), 3),
        },
        "results": results,
    }


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
    parser = argparse.ArgumentParser(description="ImpactLink budget logic evaluation")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run deterministic compliance tests only (no GROQ_API_KEY)",
    )
    args = parser.parse_args()

    title = "Budget Logic Evaluation (offline)" if args.offline else "Budget Logic Evaluation"
    print_header(f"ImpactLink {title}")
    report = run_offline_evaluation() if args.offline else run_evaluation()

    for row in report["results"]:
        icon = "PASS" if row["status"] == "PASS" else row["status"]
        print(f"  [{icon}] {row['name']}: {row['detail']}")

    agg = report["aggregate"]
    print(f"\nPass rate: {agg['passed']}/{agg['total']} ({agg['pass_rate']:.0%})")

    prefix = "budget_offline" if args.offline else "budget"
    out_path = save_report(
        f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        report,
    )
    print(f"Report saved: {out_path}")
    return 0 if agg["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
