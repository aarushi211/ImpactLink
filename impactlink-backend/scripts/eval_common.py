"""
scripts/eval_common.py

Shared helpers for ImpactLink offline evaluation harnesses.
"""

from __future__ import annotations

import json
import logging
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agents.slot_extractor import SLOT_DEFINITIONS, initial_slots, slots_to_profile

DATA_DIR = Path(__file__).resolve().parent.parent / "Data"
RESULTS_DIR = DATA_DIR / "eval_results"

_EVAL_LLM_LOGGER = "utils.llm"
_EVAL_LLM_HOOKED = False


class _EvalGroqLogHandler(logging.Handler):
    """Surface Groq pool rotation / retry messages in eval console output."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            if "[Sync]" in msg and "retrying in" in msg:
                if "rate-limited" in msg:
                    print(
                        f"[EVAL] Rate limited (429) - rotating key and retrying. {msg}",
                        flush=True,
                    )
                else:
                    print(f"[EVAL] Transient LLM error - retrying. {msg}", flush=True)
            elif "All keys cooling down" in msg:
                print(
                    f"[EVAL] All Groq keys are rate-limited - waiting for cooldown. {msg}",
                    flush=True,
                )
            elif "[Pool]" in msg and ("sync" in msg or "async" in msg):
                print(f"[EVAL] {msg}", flush=True)
            elif "quarantined" in msg:
                print(f"[EVAL] {msg}", flush=True)
        except Exception:
            self.handleError(record)


def setup_eval_llm_runtime() -> int:
    """
    Enable visible Groq key-pool rotation for LLM-backed eval scripts.

    Uses the shared KEY_POOL from utils.llm (same as production RotatingGroq).
    Prints when keys are rotated, rate-limited, or cooling down.

    Returns the number of API keys loaded from GROQ_API_KEY.
    """
    global _EVAL_LLM_HOOKED

    load_dotenv()

    from utils.llm import KEY_POOL, _KEYS

    logger = logging.getLogger(_EVAL_LLM_LOGGER)
    if not any(isinstance(h, _EvalGroqLogHandler) for h in logger.handlers):
        handler = _EvalGroqLogHandler()
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not _EVAL_LLM_HOOKED:
        original_report = KEY_POOL.report_rate_limit

        def report_rate_limit_with_notice(key: str) -> None:
            print(
                f"[EVAL] Rate limited (429) on key ...{key[-4:]}. "
                "Quarantining 60s and rotating to next key.",
                flush=True,
            )
            original_report(key)

        KEY_POOL.report_rate_limit = report_rate_limit_with_notice  # type: ignore[method-assign]
        _EVAL_LLM_HOOKED = True

    n = len(_KEYS)
    if n == 0:
        print("[EVAL] WARNING: GROQ_API_KEY is not set. LLM evals will fail.", flush=True)
    elif n == 1:
        print(
            "[EVAL] Groq: 1 API key loaded. "
            "Add comma-separated keys in GROQ_API_KEY for rotation.",
            flush=True,
        )
    else:
        print(
            f"[EVAL] Groq: {n} API keys loaded - rotation and 429 retry enabled.",
            flush=True,
        )
    return n


def print_key_pool_status() -> None:
    """Print end-of-run summary for Groq key pool health."""
    try:
        from utils.llm import KEY_POOL

        status = KEY_POOL.status()
    except Exception:
        return

    cooling = [s for s in status if s["cooling_down"]]
    failures = sum(s["failures"] for s in status)
    if not cooling and failures == 0:
        return

    print("[EVAL] Key pool summary:", flush=True)
    for row in status:
        if row["cooling_down"] or row["failures"]:
            print(
                f"  ...{row['key_suffix']}: failures={row['failures']}, "
                f"cooldown={row['cooldown_remaining_s']}s",
                flush=True,
            )


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_scenarios() -> list[dict]:
    data = load_json(DATA_DIR / "eval_scenarios.json")
    return data.get("scenarios", [])


def load_scenario(scenario_id: str) -> dict:
    for scenario in load_scenarios():
        if scenario["id"] == scenario_id:
            return scenario
    raise KeyError(f"Unknown scenario id: {scenario_id!r}")


def load_grants_catalog() -> list[dict]:
    data = load_json(DATA_DIR / "eval_grants_catalog.json")
    return data.get("grants", [])


def build_slots_from_scenario(scenario_slots: dict) -> dict:
    """Convert scenario slot values into the scratch-flow slot dict."""
    slots = initial_slots()
    for key, value in scenario_slots.items():
        if key not in slots:
            continue
        slots[key]["value"] = value
        slots[key]["filled"] = bool(value and str(value).strip())
    return slots


def build_profile_from_scenario(scenario: dict) -> dict:
    slots = build_slots_from_scenario(scenario["slots"])
    return slots_to_profile(slots)


def expected_slot_keys() -> list[str]:
    return [s["key"] for s in SLOT_DEFINITIONS]


def validate_scenario(scenario: dict) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    errors: list[str] = []
    for field in ("id", "name", "slots", "grant"):
        if field not in scenario:
            errors.append(f"Missing required field: {field}")

    slots = scenario.get("slots", {})
    for key in expected_slot_keys():
        if key not in slots or not str(slots[key]).strip():
            errors.append(f"Slot not filled: {key}")

    grant = scenario.get("grant", {})
    for key in ("title", "agency", "description"):
        if not grant.get(key):
            errors.append(f"Grant missing: {key}")

    return errors


def summarize_sections(sections: dict) -> dict:
    if not sections:
        return {
            "count": 0,
            "mean_score": 0,
            "min_score": 0,
            "max_score": 0,
            "pass_at_75": 0.0,
            "flagged_count": 0,
            "total_retries": 0,
            "per_section": {},
        }

    scores = [sec.get("score", 0) for sec in sections.values()]
    per_section = {
        key: {
            "score": sec.get("score", 0),
            "retries": sec.get("retries", 0),
            "flagged": bool(sec.get("flagged")),
            "content_chars": len(sec.get("content") or ""),
        }
        for key, sec in sections.items()
    }

    return {
        "count": len(scores),
        "mean_score": round(statistics.mean(scores), 2),
        "min_score": min(scores),
        "max_score": max(scores),
        "pass_at_75": round(sum(1 for s in scores if s >= 75) / len(scores), 3),
        "flagged_count": sum(1 for sec in sections.values() if sec.get("flagged")),
        "total_retries": sum(sec.get("retries", 0) for sec in sections.values()),
        "per_section": per_section,
    }


def summarize_agent_trace(trace: list[dict]) -> dict:
    if not trace:
        return {"event_count": 0, "by_agent": {}, "tool_mentions": 0, "coherence_mentions": 0}

    by_agent = Counter(entry.get("agent", "unknown") for entry in trace)
    decisions = " ".join(entry.get("decision", "") for entry in trace).lower()

    return {
        "event_count": len(trace),
        "by_agent": dict(by_agent),
        "tool_mentions": sum(
            1 for entry in trace
            if "tool" in entry.get("decision", "").lower()
            or entry.get("agent", "").endswith("Tool")
        ),
        "coherence_mentions": sum(
            1 for entry in trace if entry.get("agent") == "CoherenceAgent"
        ),
        "planning_mentions": sum(
            1 for entry in trace if entry.get("agent") == "PlanningAgent"
        ),
    }


def precision_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top = retrieved_ids[:k]
    if not top:
        return 0.0
    hits = sum(1 for gid in top if gid in relevant_ids)
    return round(hits / k, 3)


def recall_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    top = set(retrieved_ids[:k])
    hits = sum(1 for gid in relevant_ids if gid in top)
    return round(hits / len(relevant_ids), 3)


def ensure_results_dir() -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESULTS_DIR


def save_report(filename: str, report: dict) -> Path:
    out_dir = ensure_results_dir()
    path = out_dir / filename
    with path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return path


def print_header(title: str) -> None:
    line = "=" * 60
    print(f"\n{line}\n{title}\n{line}")
