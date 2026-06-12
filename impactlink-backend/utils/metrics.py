"""
utils/metrics.py

Centralized latency & generation-time collector for ImpactLink.

Usage:
    from utils.metrics import timed, metrics_collector

    # Decorator style — auto-records timing + logs to console
    @timed("agent", "score_section")
    def score_section(...):
        ...

    # Manual style — for finer-grained control
    with metrics_collector.timer("llm_call", "groq_generate", session_id="abc"):
        result = llm.invoke(...)

    # Query results
    metrics_collector.get_summary()                  # aggregated stats
    metrics_collector.get_session_report("abc-123")  # per-session breakdown
"""

from __future__ import annotations

import functools
import logging
import statistics
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class TimingEvent:
    category:    str            # "llm_call" | "agent" | "node" | "service" | "api"
    name:        str            # e.g. "score_section", "draft_sections", "/api/upload"
    duration_s:  float          # wall-clock seconds
    session_id:  str = ""       # for grouping by session
    metadata:    dict = field(default_factory=dict)  # model, tokens, section_key, etc.
    timestamp:   str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


# ── Collector singleton ───────────────────────────────────────────────────────

class MetricsCollector:
    """
    Thread-safe in-memory collector for timing events.

    All public methods are safe to call from any thread.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: List[TimingEvent] = []

    # ── Recording ─────────────────────────────────────────────────────────

    def record(
        self,
        category:   str,
        name:       str,
        duration_s: float,
        session_id: str = "",
        metadata:   Optional[dict] = None,
    ) -> TimingEvent:
        """Append a timing event and log it to console."""
        event = TimingEvent(
            category=category,
            name=name,
            duration_s=round(duration_s, 4),
            session_id=session_id,
            metadata=metadata or {},
        )
        with self._lock:
            self._events.append(event)

        # Console log — always printed
        meta_str = ""
        if metadata:
            meta_parts = [f"{k}={v}" for k, v in metadata.items()
                          if k not in ("raw_response",)]
            meta_str = f"  ({', '.join(meta_parts)})" if meta_parts else ""

        log.info(
            "⏱  [%s] %s = %.3fs%s%s",
            category.upper(),
            name,
            duration_s,
            f"  session={session_id[:8]}…" if session_id else "",
            meta_str,
        )
        return event

    # ── Context manager ───────────────────────────────────────────────────

    @contextmanager
    def timer(
        self,
        category:   str,
        name:       str,
        session_id: str = "",
        metadata:   Optional[dict] = None,
    ):
        """
        Context-manager style timing.

        Usage:
            with metrics_collector.timer("node", "draft_sections", session_id=sid):
                ...
        """
        start = time.perf_counter()
        _meta = dict(metadata) if metadata else {}
        try:
            yield _meta  # caller can add metadata during execution
        finally:
            duration = time.perf_counter() - start
            self.record(category, name, duration, session_id, _meta)

    # ── Queries ───────────────────────────────────────────────────────────

    def get_all_events(self) -> List[dict]:
        """Return all events as dicts."""
        with self._lock:
            return [e.to_dict() for e in self._events]

    def get_session_report(self, session_id: str) -> dict:
        """Return all events for a session, grouped by category."""
        with self._lock:
            session_events = [e for e in self._events if e.session_id == session_id]

        grouped: Dict[str, list] = {}
        for e in session_events:
            grouped.setdefault(e.category, []).append(e.to_dict())

        total_llm = sum(e.duration_s for e in session_events if e.category == "llm_call")
        total_agent = sum(e.duration_s for e in session_events if e.category == "agent")
        total_node = sum(e.duration_s for e in session_events if e.category == "node")

        return {
            "session_id": session_id,
            "event_count": len(session_events),
            "totals": {
                "llm_call_s": round(total_llm, 4),
                "agent_s": round(total_agent, 4),
                "node_s": round(total_node, 4),
            },
            "events_by_category": grouped,
        }

    def get_summary(self) -> dict:
        """Return aggregated stats (mean, p50, p95, max) per event name."""
        with self._lock:
            events_copy = list(self._events)

        # Group by (category, name)
        buckets: Dict[str, List[float]] = {}
        for e in events_copy:
            key = f"{e.category}/{e.name}"
            buckets.setdefault(key, []).append(e.duration_s)

        summary = {}
        for key, durations in sorted(buckets.items()):
            n = len(durations)
            sorted_d = sorted(durations)
            p95_idx = min(int(n * 0.95), n - 1)
            summary[key] = {
                "count": n,
                "mean_s": round(statistics.mean(durations), 4),
                "median_s": round(statistics.median(durations), 4),
                "p95_s": round(sorted_d[p95_idx], 4),
                "max_s": round(max(durations), 4),
                "min_s": round(min(durations), 4),
                "total_s": round(sum(durations), 4),
            }

        return {
            "total_events": len(events_copy),
            "summary_by_step": summary,
        }

    def reset(self) -> None:
        """Clear all collected events."""
        with self._lock:
            self._events.clear()
        log.info("⏱  Metrics collector reset.")

    # ── CSV Export ────────────────────────────────────────────────────

    def export_events_csv(self) -> str:
        """Export all raw timing events as a CSV string."""
        import csv
        import io

        with self._lock:
            events_copy = list(self._events)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "timestamp", "category", "name", "duration_s",
            "session_id", "metadata",
        ])
        for e in events_copy:
            meta_str = "; ".join(f"{k}={v}" for k, v in e.metadata.items()) if e.metadata else ""
            writer.writerow([
                e.timestamp, e.category, e.name,
                e.duration_s, e.session_id, meta_str,
            ])
        return output.getvalue()

    def export_summary_csv(self) -> str:
        """Export aggregated stats (count, mean, median, p95, max) as a CSV string."""
        import csv
        import io

        summary = self.get_summary()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "step", "count", "mean_s", "median_s",
            "p95_s", "max_s", "min_s", "total_s",
        ])
        for step_name, stats in summary.get("summary_by_step", {}).items():
            writer.writerow([
                step_name,
                stats["count"],
                stats["mean_s"],
                stats["median_s"],
                stats["p95_s"],
                stats["max_s"],
                stats["min_s"],
                stats["total_s"],
            ])
        return output.getvalue()


# ── Module-level singleton ────────────────────────────────────────────────────

metrics_collector = MetricsCollector()


# ── Decorator ─────────────────────────────────────────────────────────────────

def timed(category: str, name: str = None):
    """
    Decorator that auto-records timing for any function.

    Usage:
        @timed("agent", "score_section")
        def score_section(section_key, ...):
            ...

    The decorator will:
      1. Start a perf_counter before the function
      2. Call the function
      3. Record a TimingEvent with the duration
      4. Log the timing to console

    If the decorated function receives a `session_id` kwarg or has it
    as the first positional arg, it will be included in the event.
    """
    def decorator(func):
        event_name = name or func.__name__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Try to extract session_id from kwargs or state dict
            sid = _extract_session_id(args, kwargs)

            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.perf_counter() - start
                metrics_collector.record(
                    category=category,
                    name=event_name,
                    duration_s=duration,
                    session_id=sid,
                )
        return wrapper
    return decorator


def _extract_session_id(args: tuple, kwargs: dict) -> str:
    """Best-effort extraction of session_id from function arguments."""
    # Check kwargs first
    if "session_id" in kwargs:
        return str(kwargs["session_id"])

    # Check if first arg is a state dict with session_id
    if args and isinstance(args[0], dict) and "session_id" in args[0]:
        return str(args[0]["session_id"])

    return ""
