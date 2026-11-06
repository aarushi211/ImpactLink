"""Deterministic evaluation of the current cost-input budget engine (no API keys)."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval_common import print_header, save_report
from services.budget.costing import calculate_budget


def run_offline_evaluation():
    inputs = {"staff": [{"id": "s", "role": "Coordinator", "headcount": 2, "annual_salary": 60000, "fte_per_person": "0.5", "months": 6, "fringe_rate_pct": 20}],
              "indirect": {"method": "funder", "rate_pct": 10, "reference": "Synthetic evaluation terms"}}
    budget = calculate_budget(inputs, 30000)
    cases = [
        ("Salary effort and project duration", budget["items"][0]["amount"] == 30000),
        ("Fringe on project salary", budget["items"][1]["amount"] == 6000),
        ("Indirect on MTDC", budget["items"][2]["amount"] == 3600),
        ("Over-budget costs preserved", budget["total_requested"] == 39600 and budget["funding_gap"] == 9600),
        ("Scope reduction recalculates costs", budget["scope_options"][0]["total_requested"] == 19800),
        ("No automatic headcount reduction", budget["cost_inputs"]["staff"][0]["headcount"] == 2),
    ]
    subawards = {"direct_costs": [{"id": str(index), "description": "Partner delivery", "kind": "subaward", "quantity": 1, "unit_cost": 30000, "subaward_id": "A"} for index in (1, 2)],
                 "indirect": {"method": "de_minimis", "rate_pct": 15, "de_minimis_eligible": True}}
    calculated = calculate_budget(subawards, 100000)
    cases.append(("One MTDC threshold per subaward", calculated["compliance_summary"]["indirect"]["base_amount"] == 50000 and calculated["total_requested"] == 67500))
    blocked = {"direct_costs": [{"id": "a", "description": "Flights", "kind": "travel", "quantity": 1, "unit_cost": 1000}], "unallowable_kinds": ["travel"]}
    try:
        calculate_budget(blocked, 100000)
        cases.append(("Unallowable costs blocked", False))
    except ValueError:
        cases.append(("Unallowable costs blocked", True))
    results = [{"name": name, "status": "PASS" if passed else "FAIL", "detail": "Synthetic cost-input fixture"} for name, passed in cases]
    passed = sum(bool(ok) for _, ok in cases)
    return {"eval_type": "budget_cost_inputs", "timestamp": datetime.now(timezone.utc).isoformat(), "aggregate": {"total": len(cases), "passed": passed, "failed": len(cases) - passed, "pass_rate": passed / len(cases)}, "results": results}


run_evaluation = run_offline_evaluation


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Accepted for CI compatibility; all budget math is deterministic")
    parser.parse_args()
    print_header("ImpactLink Budget Cost Evaluation")
    report = run_offline_evaluation()
    for row in report["results"]:
        print(f"[{row['status']}] {row['name']}")
    print(f"Passed {report['aggregate']['passed']}/{report['aggregate']['total']}")
    save_report(f"budget_costs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", report)
    sys.exit(1 if report["aggregate"]["failed"] else 0)
