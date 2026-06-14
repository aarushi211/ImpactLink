"""
scripts/evaluate_generation.py

Smoke test for the ScoringAgent on a weak vs strong section pair.
Useful for quick judge sanity checks without running the full pipeline.

Usage:
    python scripts/evaluate_generation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from agents.scoring_agent import score_section
from eval_common import load_scenario, print_header, print_key_pool_status, setup_eval_llm_runtime


def evaluate_generation() -> int:
    print_header("ScoringAgent Smoke Test")
    if setup_eval_llm_runtime() == 0:
        print("Aborting: set GROQ_API_KEY in .env")
        return 1
    print("Rate-limit messages will print as [EVAL] when rotation/retry occurs.\n")

    scenario = load_scenario("la_urban_forestry")
    grant = scenario["grant"]
    vocab = ["canopy", "heat island", "environmental justice", "disadvantaged communities"]

    cases = [
        {
            "label": "Weak draft (should score low)",
            "section_key": "executive_summary",
            "section_title": "Executive Summary",
            "content": (
                "We will plant trees in East LA. It is very hot there. "
                "We hope this helps the community."
            ),
        },
        {
            "label": "Stronger draft (should score higher)",
            "section_key": "executive_summary",
            "section_title": "Executive Summary",
            "content": (
                "Green Future Los Angeles requests $85,000 from CAL FIRE's Urban and Community "
                "Forestry Program to plant 500 native trees across Boyle Heights and East LA "
                "(ZIP 90033, 90063), increasing canopy cover in census tracts with 12% tree cover "
                "and surface temperatures above 105°F. Over 18 months, 2,400 residents will benefit "
                "through planting crews, 40 certified resident stewards, and quarterly canopy "
                "assessments with UCLA Extension. Success will be measured by 70% one-year tree "
                "survival and a 15% reduction in peak afternoon temperature at 10 monitoring sites."
            ),
        },
    ]

    results = []
    for case in cases:
        print(f"--- {case['label']} ---")
        print(f"Content preview: {case['content'][:120]}...\n")

        result = score_section(
            section_key=case["section_key"],
            section_title=case["section_title"],
            content=case["content"],
            grant=grant,
            funder_vocab=vocab,
        )
        score = result["score"]
        print(f"Score: {score}/100")
        print(f"Feedback: {result['feedback']}\n")
        results.append(score)

    if len(results) == 2 and results[1] > results[0]:
        print("PASS: stronger draft scored higher than weak draft.")
        print_key_pool_status()
        return 0

    print("WARN: expected stronger draft to outscore weak draft.")
    print_key_pool_status()
    return 1


if __name__ == "__main__":
    raise SystemExit(evaluate_generation())
