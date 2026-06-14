"""
scripts/evaluate_retrieval.py

Offline retrieval evaluation using the hand-curated grant catalog.
Does not require Supabase/pgvector — uses keyword overlap ranking.

Optional --live mode uses topic_search_grants() when DATABASE_URL is configured.

Usage:
    python scripts/evaluate_retrieval.py
    python scripts/evaluate_retrieval.py --live
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from eval_common import (
    load_grants_catalog,
    load_scenarios,
    precision_at_k,
    print_header,
    print_key_pool_status,
    recall_at_k,
    save_report,
    setup_eval_llm_runtime,
)


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    stop = {
        "the", "and", "for", "with", "that", "this", "from", "are", "will",
        "into", "their", "have", "has", "was", "were", "been", "also", "via",
    }
    return {w for w in words if len(w) > 2 and w not in stop}


def rank_grants_keyword(query: str, grants: list[dict], top_k: int = 5) -> list[str]:
    """Simple offline ranker: token overlap + title/focus boost."""
    q_tokens = _tokenize(query)
    scored = []

    for grant in grants:
        text = " ".join([
            grant.get("title", ""),
            grant.get("agency", ""),
            grant.get("description", ""),
            grant.get("focus_areas", ""),
        ])
        g_tokens = _tokenize(text)
        overlap = len(q_tokens & g_tokens)

        title_tokens = _tokenize(grant.get("title", ""))
        focus_tokens = _tokenize(grant.get("focus_areas", ""))
        title_boost = len(q_tokens & title_tokens) * 2
        focus_boost = len(q_tokens & focus_tokens)

        score = overlap + title_boost + focus_boost
        scored.append((score, grant["id"]))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [gid for _, gid in scored[:top_k]]


def run_offline_eval(k: int = 5) -> dict:
    catalog = load_grants_catalog()
    catalog_ids = {g["id"] for g in catalog}
    scenario_results = []

    for scenario in load_scenarios():
        retrieval = scenario.get("retrieval") or {}
        query = retrieval.get("query", "")
        relevant = retrieval.get("relevant_grant_ids", [])

        missing = [gid for gid in relevant if gid not in catalog_ids]
        retrieved = rank_grants_keyword(query, catalog, top_k=k)

        scenario_results.append({
            "scenario_id": scenario["id"],
            "query": query,
            "relevant_grant_ids": relevant,
            "retrieved_ids": retrieved,
            f"precision@{k}": precision_at_k(retrieved, relevant, k),
            f"recall@{k}": recall_at_k(retrieved, relevant, k),
            "missing_from_catalog": missing,
            "status": "ok" if not missing else "warn",
        })

    valid = [r for r in scenario_results if r["status"] == "ok"]
    return {
        "mode": "offline_keyword",
        "k": k,
        "catalog_size": len(catalog),
        "aggregate": {
            "scenarios": len(scenario_results),
            f"mean_precision@{k}": round(
                sum(r[f"precision@{k}"] for r in valid) / max(len(valid), 1), 3
            ),
            f"mean_recall@{k}": round(
                sum(r[f"recall@{k}"] for r in valid) / max(len(valid), 1), 3
            ),
        },
        "results": scenario_results,
    }


def run_live_eval(k: int = 5) -> dict:
    from services.vector_store import topic_search_grants

    scenario_results = []
    for scenario in load_scenarios():
        retrieval = scenario.get("retrieval") or {}
        query = retrieval.get("query", "")
        relevant = [str(g) for g in retrieval.get("relevant_grant_ids", [])]

        try:
            hits = topic_search_grants(query, top_k=k)
            retrieved = [str(h.get("grant_id", "")) for h in hits]
        except Exception as exc:
            scenario_results.append({
                "scenario_id": scenario["id"],
                "status": "error",
                "error": str(exc),
            })
            continue

        scenario_results.append({
            "scenario_id": scenario["id"],
            "query": query,
            "relevant_grant_ids": relevant,
            "retrieved_ids": retrieved,
            f"precision@{k}": precision_at_k(retrieved, relevant, k),
            f"recall@{k}": recall_at_k(retrieved, relevant, k),
            "status": "ok",
        })

    ok = [r for r in scenario_results if r.get("status") == "ok"]
    return {
        "mode": "live_vector_db",
        "k": k,
        "aggregate": {
            "scenarios": len(scenario_results),
            f"mean_precision@{k}": round(
                sum(r[f"precision@{k}"] for r in ok) / max(len(ok), 1), 3
            ),
            f"mean_recall@{k}": round(
                sum(r[f"recall@{k}"] for r in ok) / max(len(ok), 1), 3
            ),
        },
        "results": scenario_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate grant retrieval")
    parser.add_argument("--live", action="store_true", help="Use live pgvector search (needs DATABASE_URL)")
    parser.add_argument("--k", type=int, default=5, help="Top-K for precision/recall")
    parser.add_argument("--output", type=str, help="Output filename under Data/eval_results/")
    args = parser.parse_args()

    print_header("ImpactLink Retrieval Evaluation")

    if args.live:
        print("Mode: live vector DB\n")
        if setup_eval_llm_runtime() == 0:
            print("Aborting: GROQ_API_KEY required for live retrieval reranking.")
            return 1
        print("Rate-limit messages will print as [EVAL] when rotation/retry occurs.\n")
        report = run_live_eval(k=args.k)
    else:
        print("Mode: offline keyword ranker (no DB required)\n")
        report = run_offline_eval(k=args.k)

    report["eval_type"] = "retrieval"
    report["timestamp"] = datetime.now(timezone.utc).isoformat()

    for row in report["results"]:
        if row.get("status") == "ok":
            print(
                f"  {row['scenario_id']}: "
                f"P@{args.k}={row[f'precision@{args.k}']:.2f} "
                f"R@{args.k}={row[f'recall@{args.k}']:.2f} "
                f"-> {row['retrieved_ids']}"
            )
        else:
            print(f"  {row['scenario_id']}: {row.get('status')} {row.get('error', row.get('missing_from_catalog'))}")

    agg = report["aggregate"]
    print(
        f"\nMean P@{args.k}: {agg[f'mean_precision@{args.k}']:.2f} | "
        f"Mean R@{args.k}: {agg[f'mean_recall@{args.k}']:.2f}"
    )

    out_name = args.output or f"retrieval_{report['mode']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path = save_report(out_name, report)
    print(f"Report saved: {out_path}")
    if args.live:
        print_key_pool_status()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
