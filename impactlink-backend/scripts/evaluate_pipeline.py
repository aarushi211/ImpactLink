"""
scripts/evaluate_pipeline.py

Run the scratch-flow drafting pipeline on fixed eval scenarios.

Bypasses slot-filling Q&A by injecting hand-crafted slot values, then runs:
  PlanningAgent → SectionSubgraph (draft/score/retry) → CoherenceAgent

Usage:
    cd impactlink-backend
    python scripts/evaluate_pipeline.py --all
    python scripts/evaluate_pipeline.py --scenario la_urban_forestry
    python scripts/evaluate_pipeline.py --all --quick   # 3 sections only (faster)
    python scripts/evaluate_pipeline.py --all --output report.json
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from agents.prompts import SECTIONS
from agents.vocab_extractor import extract_funder_vocab
from flows.section_subgraph import run_section_subgraph
from flows.scratch_flow import node_coherence_check, node_draft_sections, node_plan_draft
from utils.metrics import metrics_collector

from eval_common import (
    build_slots_from_scenario,
    load_scenario,
    load_scenarios,
    print_header,
    print_key_pool_status,
    save_report,
    setup_eval_llm_runtime,
    summarize_agent_trace,
    summarize_sections,
    validate_scenario,
)

QUICK_SECTION_KEYS = [
    "executive_summary",
    "goals_and_objectives",
    "budget_narrative",
]


def _build_eval_state(scenario: dict) -> dict:
    session_id = f"eval-{scenario['id']}-{uuid.uuid4().hex[:8]}"
    slots = build_slots_from_scenario(scenario["slots"])
    grant = scenario["grant"]

    return {
        "session_id": session_id,
        "user_id": "eval-runner",
        "flow": "scratch",
        "profile": {},
        "grant": grant,
        "funder_vocab": extract_funder_vocab(grant),
        "drafting_plan": None,
        "agent_trace": [],
        "slots": slots,
        "analysis": None,
        "original_sections": {},
        "sections": {},
        "diffs": {},
        "gate": "slot_confirm",
        "retry_counts": {},
        "flagged_sections": [],
    }


def _draft_quick_sections(state: dict, section_keys: list[str]) -> dict:
    """Draft a subset of sections without running the full wave orchestrator."""
    profile = state.get("profile") or {}
    grant = state["grant"]
    vocab = state["funder_vocab"]
    drafting_plan = state.get("drafting_plan")
    sid = state["session_id"]

    sections_by_key = {s["key"]: s for s in SECTIONS}
    new_sections = {}
    new_retry_counts = dict(state.get("retry_counts") or {})
    new_flagged = list(state.get("flagged_sections") or [])
    trace = list(state.get("agent_trace") or [])

    trace.append({
        "agent": "evaluate_pipeline",
        "decision": f"quick mode — drafting {', '.join(section_keys)}",
        "metadata": {},
    })

    for key in section_keys:
        section = sections_by_key.get(key)
        if not section:
            continue
        _, result = run_section_subgraph(
            section,
            session_id=sid,
            profile=profile,
            grant=grant,
            funder_vocab=vocab,
            drafting_plan=drafting_plan,
            prior_sections_context="",
        )
        new_sections[key] = result
        new_retry_counts[key] = result.get("retries", 0)
        if result.get("flagged") and key not in new_flagged:
            new_flagged.append(key)

    return {
        "sections": new_sections,
        "retry_counts": new_retry_counts,
        "flagged_sections": new_flagged,
        "agent_trace": trace,
    }


def run_scenario(scenario: dict, *, quick: bool = False) -> dict:
    errors = validate_scenario(scenario)
    if errors:
        return {
            "scenario_id": scenario.get("id", "unknown"),
            "status": "invalid",
            "errors": errors,
        }

    metrics_collector.reset()
    started = time.perf_counter()
    state = _build_eval_state(scenario)

    try:
        state.update(node_plan_draft(state))

        if quick:
            state.update(_draft_quick_sections(state, QUICK_SECTION_KEYS))
        else:
            state.update(node_draft_sections(state))

        state.update(node_coherence_check(state))

        elapsed = round(time.perf_counter() - started, 2)
        sections = state.get("sections") or {}
        trace = state.get("agent_trace") or []

        return {
            "scenario_id": scenario["id"],
            "scenario_name": scenario["name"],
            "status": "ok",
            "mode": "quick" if quick else "full",
            "elapsed_s": elapsed,
            "gate": state.get("gate"),
            "sections_expected": 10 if not quick else len(QUICK_SECTION_KEYS),
            "sections_summary": summarize_sections(sections),
            "agent_trace_summary": summarize_agent_trace(trace),
            "drafting_plan_priorities": len(
                (state.get("drafting_plan") or {}).get("section_priorities") or []
            ),
            "metrics_summary": metrics_collector.get_summary(),
            "session_id": state["session_id"],
        }
    except Exception as exc:
        return {
            "scenario_id": scenario["id"],
            "scenario_name": scenario.get("name"),
            "status": "error",
            "error": str(exc),
            "elapsed_s": round(time.perf_counter() - started, 2),
        }


def _aggregate_results(results: list[dict]) -> dict:
    ok = [r for r in results if r.get("status") == "ok"]
    if not ok:
        return {"runs": 0}

    mean_scores = [r["sections_summary"]["mean_score"] for r in ok]
    pass_rates = [r["sections_summary"]["pass_at_75"] for r in ok]
    latencies = [r["elapsed_s"] for r in ok]

    return {
        "runs": len(ok),
        "mean_section_score_avg": round(sum(mean_scores) / len(mean_scores), 2),
        "pass_at_75_avg": round(sum(pass_rates) / len(pass_rates), 3),
        "elapsed_s_avg": round(sum(latencies) / len(latencies), 2),
        "elapsed_s_max": max(latencies),
        "total_flagged": sum(r["sections_summary"]["flagged_count"] for r in ok),
        "total_retries": sum(r["sections_summary"]["total_retries"] for r in ok),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate ImpactLink drafting pipeline")
    parser.add_argument("--all", action="store_true", help="Run every scenario in eval_scenarios.json")
    parser.add_argument("--scenario", type=str, help="Run a single scenario by id")
    parser.add_argument("--quick", action="store_true", help="Draft only 3 representative sections")
    parser.add_argument("--output", type=str, help="Save JSON report to Data/eval_results/")
    args = parser.parse_args()

    if args.scenario:
        scenarios = [load_scenario(args.scenario)]
    elif args.all:
        scenarios = load_scenarios()
    else:
        parser.error("Specify --all or --scenario <id>")

    print_header("ImpactLink Pipeline Evaluation")
    key_count = setup_eval_llm_runtime()
    print(f"Scenarios: {len(scenarios)} | Mode: {'quick' if args.quick else 'full'}")
    if key_count == 0:
        print("Aborting: set GROQ_API_KEY in .env before running pipeline eval.\n")
        return 1
    print("Rate-limit messages will print as [EVAL] when rotation/retry occurs.\n")

    results = []
    for scenario in scenarios:
        print(f"--- {scenario['id']}: {scenario['name']} ---")
        result = run_scenario(scenario, quick=args.quick)
        results.append(result)

        if result["status"] == "ok":
            s = result["sections_summary"]
            print(
                f"  OK  {result['elapsed_s']}s | "
                f"sections={s['count']} | mean_score={s['mean_score']} | "
                f"pass@75={s['pass_at_75']:.0%} | retries={s['total_retries']} | "
                f"flagged={s['flagged_count']}"
            )
        elif result["status"] == "invalid":
            print(f"  INVALID: {', '.join(result['errors'])}")
        else:
            print(f"  ERROR: {result.get('error')}")
        print()

    report = {
        "eval_type": "pipeline",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "quick" if args.quick else "full",
        "aggregate": _aggregate_results(results),
        "results": results,
    }

    print_header("Pipeline Summary")
    agg = report["aggregate"]
    if agg.get("runs"):
        print(f"Runs:              {agg['runs']}")
        print(f"Avg mean score:    {agg['mean_section_score_avg']}")
        print(f"Avg pass@75:       {agg['pass_at_75_avg']:.1%}")
        print(f"Avg latency:       {agg['elapsed_s_avg']}s")
        print(f"Max latency:       {agg['elapsed_s_max']}s")
        print(f"Total retries:     {agg['total_retries']}")
        print(f"Total flagged:     {agg['total_flagged']}")
    else:
        print("No successful runs.")

    out_name = args.output or f"pipeline_{report['mode']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path = save_report(out_name, report)
    print(f"\nReport saved: {out_path}")
    print_key_pool_status()

    failed = sum(1 for r in results if r["status"] != "ok")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
