"""
scripts/evaluate_all.py

Run all offline evaluation harnesses and produce a combined report.

Usage:
    cd impactlink-backend
    python scripts/evaluate_all.py                  # budget + retrieval only (fast)
    python scripts/evaluate_all.py --with-pipeline  # includes LLM drafting (slow)
    python scripts/evaluate_all.py --with-pipeline --quick
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

from eval_common import print_header, save_report
from evaluate_logic import run_evaluation as run_budget_eval
from evaluate_retrieval import run_offline_eval
from evaluate_pipeline import run_scenario, _aggregate_results

from eval_common import load_scenarios, print_header, print_key_pool_status, save_report, setup_eval_llm_runtime


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all ImpactLink eval harnesses")
    parser.add_argument("--with-pipeline", action="store_true", help="Include LLM pipeline eval")
    parser.add_argument("--quick", action="store_true", help="Quick pipeline mode (3 sections)")
    parser.add_argument("--scenario", type=str, help="Limit pipeline eval to one scenario id")
    args = parser.parse_args()

    print_header("ImpactLink Full Evaluation Suite")
    combined = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "suites": {},
    }
    exit_code = 0

    print("\n[1/2] Budget logic")
    budget_report = run_budget_eval()
    combined["suites"]["budget"] = budget_report
    print(f"  -> {budget_report['aggregate']['passed']}/{budget_report['aggregate']['total']} passed")
    if budget_report["aggregate"]["failed"]:
        exit_code = 1

    print("\n[2/2] Retrieval (offline)")
    retrieval_report = run_offline_eval(k=5)
    combined["suites"]["retrieval"] = retrieval_report
    agg = retrieval_report["aggregate"]
    print(f"  -> mean P@5={agg['mean_precision@5']:.2f}, mean R@5={agg['mean_recall@5']:.2f}")

    if args.with_pipeline:
        print("\n[3/3] Pipeline (LLM)")
        if setup_eval_llm_runtime() == 0:
            print("  Skipping pipeline: GROQ_API_KEY not set.")
            exit_code = 1
        else:
            print("  Rate-limit messages will print as [EVAL] when rotation/retry occurs.")
            scenarios = load_scenarios()
            if args.scenario:
                scenarios = [s for s in scenarios if s["id"] == args.scenario]
                if not scenarios:
                    print(f"  Unknown scenario: {args.scenario}")
                    return 1

            pipeline_results = [
                run_scenario(s, quick=args.quick) for s in scenarios
            ]
            pipeline_report = {
                "eval_type": "pipeline",
                "mode": "quick" if args.quick else "full",
                "aggregate": _aggregate_results(pipeline_results),
                "results": pipeline_results,
            }
            combined["suites"]["pipeline"] = pipeline_report

            ok = pipeline_report["aggregate"].get("runs", 0)
            failed = sum(1 for r in pipeline_results if r["status"] != "ok")
            print(f"  -> {ok} ok, {failed} failed")
            if failed:
                exit_code = 1
            print_key_pool_status()

    out_path = save_report(
        f"combined_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        combined,
    )
    print_header("Done")
    print(f"Combined report: {out_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
