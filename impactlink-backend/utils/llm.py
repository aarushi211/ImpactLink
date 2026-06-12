"""
rotating_groq.py
~~~~~~~~~~~~~~~~
A production-grade drop-in replacement for ChatGroq that adds:

  • Cross-request key cooldown   — keys that 429'd are quarantined for a
                                   configurable window before re-entering the pool.
  • Thread-safe client caching   — one Groq / AsyncGroq client instance per key,
                                   created once under a lock and reused forever.
  • Smart key scheduling         — picks the least-recently-used key with the
                                   fewest failures (weighted score), so load is
                                   spread evenly and troubled keys are deprioritised.
  • Full-jitter exponential back-off for 429 / 5xx errors.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from dotenv import load_dotenv
from utils.metrics import metrics_collector
from groq import AsyncGroq, Groq
from langchain_groq import ChatGroq

load_dotenv()
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
BASE_DELAY: float      = 1.0    # seconds — wait before first retry
MAX_DELAY: float       = 60.0   # seconds — ceiling for any single wait
BACKOFF_FACTOR: float  = 2.0    # exponential multiplier
JITTER_FRACTION: float = 0.25   # ±25 % random jitter to de-sync callers
MAX_RETRIES: int       = 5      # attempts before propagating the exception
KEY_COOLDOWN: float    = 60.0   # seconds a key is quarantined after a 429
# Weight applied to failure_count when scoring keys (higher → bad keys
# are penalised more aggressively relative to recency).
FAILURE_WEIGHT: float  = 10.0


# ---------------------------------------------------------------------------
# Per-key state
# ---------------------------------------------------------------------------
@dataclass
class _KeyState:
    key: str
    # Cached SDK clients — created lazily, then reused.
    sync_client:  Optional[object] = field(default=None, repr=False)
    async_client: Optional[object] = field(default=None, repr=False)
    # Scheduling metadata
    last_used_at:   float = 0.0   # monotonic seconds of last successful pick
    failure_count:  int   = 0     # cumulative 429 / 5xx hits
    cooldown_until: float = 0.0   # monotonic seconds; key is blocked until then

    def is_cooling_down(self) -> bool:
        return time.monotonic() < self.cooldown_until

    def mark_rate_limited(self, cooldown: float = KEY_COOLDOWN) -> None:
        self.cooldown_until = time.monotonic() + cooldown
        self.failure_count += 1
        log.warning(
            "Key ...%s quarantined for %.0fs (total failures=%d)",
            self.key[-4:], cooldown, self.failure_count,
        )

    def mark_success(self) -> None:
        # Gradually forgive: halve failure count on every clean response.
        self.failure_count = max(0, self.failure_count // 2)
        self.last_used_at  = time.monotonic()

    def score(self) -> float:
        """
        Lower score = more preferred.

        score = -idle_seconds + failure_count * FAILURE_WEIGHT

        A key that has been idle longest gets a more-negative score (preferred).
        A key with many failures is pushed up (deprioritised).
        """
        idle = time.monotonic() - self.last_used_at
        return -idle + self.failure_count * FAILURE_WEIGHT


# ---------------------------------------------------------------------------
# Thread-safe key pool  (module-level singleton)
# ---------------------------------------------------------------------------
class _KeyPool:
    """
    Owns the full lifecycle of every API key:

      - Lazy client construction  (one Groq + one AsyncGroq per key, ever)
      - Cooldown enforcement      (quarantine after 429)
      - Weighted scheduling       (lowest LRU + failure score wins)
      - Thread safety             (single RLock guards all mutable state)
    """

    def __init__(self, keys: list[str]) -> None:
        self._lock   = threading.RLock()
        self._states: Dict[str, _KeyState] = {k: _KeyState(key=k) for k in keys}

    # ------------------------------------------------------------------
    # Internal helpers  (call only while holding self._lock)
    # ------------------------------------------------------------------
    def _available(self) -> list[_KeyState]:
        return [s for s in self._states.values() if not s.is_cooling_down()]

    def _best(self) -> Optional[_KeyState]:
        """
        Return the available key with the lowest score.
        Ties (within 5 % relative tolerance) are broken randomly so no single
        key monopolises when several share the same score.
        """
        candidates = self._available()
        if not candidates:
            return None
        min_score = min(s.score() for s in candidates)
        top = [s for s in candidates
               if math.isclose(s.score(), min_score, rel_tol=0.05)]
        return random.choice(top)

    def _ensure_sync_client(self, state: _KeyState) -> object:
        if state.sync_client is None:
            state.sync_client = Groq(api_key=state.key).chat.completions
            log.debug("Created sync client for key ...%s", state.key[-4:])
        return state.sync_client

    def _ensure_async_client(self, state: _KeyState) -> object:
        if state.async_client is None:
            state.async_client = AsyncGroq(api_key=state.key).chat.completions
            log.debug("Created async client for key ...%s", state.key[-4:])
        return state.async_client

    def _cooldown_remaining(self) -> float:
        """Seconds until the soonest quarantined key exits cooldown."""
        now   = time.monotonic()
        waits = [max(0.0, s.cooldown_until - now) for s in self._states.values()]
        return min(waits) if waits else 1.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def acquire_sync(self) -> tuple[str, object]:
        """
        Return (api_key, sync_client) for the best available key.
        Blocks with brief sleeps if every key is currently cooling down.
        """
        while True:
            with self._lock:
                state = self._best()
                if state:
                    state.last_used_at = time.monotonic()
                    client = self._ensure_sync_client(state)
                    log.info(
                        "[Pool] sync  → key ...%s  score=%.1f",
                        state.key[-4:], state.score(),
                    )
                    return state.key, client

            wait = self._cooldown_remaining()
            log.warning("[Pool] All keys cooling down — waiting %.1fs …", wait)
            time.sleep(min(wait, 1.0))

    async def acquire_async(self) -> tuple[str, object]:
        """Async equivalent of acquire_sync."""
        while True:
            with self._lock:
                state = self._best()
                if state:
                    state.last_used_at = time.monotonic()
                    client = self._ensure_async_client(state)
                    log.info(
                        "[Pool] async → key ...%s  score=%.1f",
                        state.key[-4:], state.score(),
                    )
                    return state.key, client

            wait = self._cooldown_remaining()
            log.warning("[Pool] All keys cooling down — waiting %.1fs …", wait)
            await asyncio.sleep(min(wait, 1.0))

    def report_rate_limit(self, key: str) -> None:
        with self._lock:
            if key in self._states:
                self._states[key].mark_rate_limited()

    def report_success(self, key: str) -> None:
        with self._lock:
            if key in self._states:
                self._states[key].mark_success()

    def report_transient_failure(self, key: str) -> None:
        """Non-429 retryable error: increment failure count without cooldown."""
        with self._lock:
            if key in self._states:
                self._states[key].failure_count += 1

    def status(self) -> list[dict]:
        """Diagnostic snapshot — safe to call from any thread at any time."""
        with self._lock:
            now = time.monotonic()
            return [
                {
                    "key_suffix":          s.key[-4:],
                    "failures":            s.failure_count,
                    "score":               round(s.score(), 2),
                    "cooling_down":        s.is_cooling_down(),
                    "cooldown_remaining_s": round(max(0.0, s.cooldown_until - now), 1),
                }
                for s in self._states.values()
            ]


# ---------------------------------------------------------------------------
# Module-level singleton — shared across all RotatingGroq instances / threads
# ---------------------------------------------------------------------------
_RAW_KEYS = os.getenv("GROQ_API_KEY", "")
_KEYS: list[str] = [k.strip() for k in _RAW_KEYS.split(",") if k.strip()]
KEY_POOL = _KeyPool(_KEYS)


# ---------------------------------------------------------------------------
# Back-off helper
# ---------------------------------------------------------------------------
def _compute_delay(attempt: int) -> float:
    """Full-jitter exponential backoff capped at MAX_DELAY."""
    exp    = min(BASE_DELAY * (BACKOFF_FACTOR ** attempt), MAX_DELAY)
    jitter = exp * JITTER_FRACTION * (2 * random.random() - 1)
    return max(0.0, exp + jitter)


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------
def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "429"         in msg
        or "rate limit"  in msg
        or "rate_limit"  in msg
        or "too many"    in msg
        or type(exc).__name__ == "RateLimitError"
    )


def _is_retryable(exc: Exception) -> bool:
    if _is_rate_limit(exc):
        return True
    msg = str(exc).lower()
    return any(code in msg for code in ("500", "502", "503", "504")) or any(
        word in msg for word in ("connection", "timeout")
    )


# ---------------------------------------------------------------------------
# RotatingGroq
# ---------------------------------------------------------------------------
class RotatingGroq(ChatGroq):
    """
    Drop-in replacement for ChatGroq with production-grade key management.

    All key selection, client caching, cooldown enforcement, and failure
    accounting is delegated to the module-level KEY_POOL singleton so state
    is consistent across every instance and every thread.
    """

    # ------------------------------------------------------------------
    # Sync path
    # ------------------------------------------------------------------
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        call_start = time.perf_counter()
        total_attempts = 0

        for attempt in range(MAX_RETRIES):
            total_attempts = attempt + 1
            key, client = KEY_POOL.acquire_sync()

            # Swap key + client atomically under a lock so concurrent threads
            # sharing the same RotatingGroq instance can't interleave writes.
            with threading.Lock():
                object.__setattr__(self, "groq_api_key", key)
                object.__setattr__(self, "client", client)

            try:
                gen_start = time.perf_counter()
                result = super()._generate(
                    messages, stop=stop, run_manager=run_manager, **kwargs
                )
                gen_duration = time.perf_counter() - gen_start
                KEY_POOL.report_success(key)

                # Record successful LLM call timing
                meta = {
                    "model": getattr(self, "model_name", getattr(self, "model", "unknown")),
                    "key_suffix": key[-4:],
                    "attempt": total_attempts,
                    "generation_s": round(gen_duration, 4),
                }
                # Try to extract token usage from result
                if hasattr(result, "generations") and result.generations:
                    gen_info = result.generations[0] if result.generations[0] else None
                    if gen_info and hasattr(gen_info, "generation_info"):
                        usage = (gen_info.generation_info or {}).get("usage", {})
                        if usage:
                            meta["prompt_tokens"] = usage.get("prompt_tokens", 0)
                            meta["completion_tokens"] = usage.get("completion_tokens", 0)
                            meta["total_tokens"] = usage.get("total_tokens", 0)

                total_duration = time.perf_counter() - call_start
                metrics_collector.record(
                    category="llm_call",
                    name=f"groq_generate",
                    duration_s=total_duration,
                    metadata=meta,
                )
                return result

            except Exception as exc:
                is_last = attempt == MAX_RETRIES - 1

                if _is_rate_limit(exc):
                    KEY_POOL.report_rate_limit(key)
                elif _is_retryable(exc):
                    KEY_POOL.report_transient_failure(key)

                if not _is_retryable(exc) or is_last:
                    log.error(
                        "[Sync] Giving up after %d attempt(s) — key ...%s: %s",
                        attempt + 1, key[-4:], exc,
                    )
                    raise

                delay = _compute_delay(attempt)
                log.warning(
                    "[Sync] attempt=%d key=...%s %s — retrying in %.2fs",
                    attempt + 1, key[-4:],
                    "rate-limited" if _is_rate_limit(exc) else repr(exc),
                    delay,
                )
                time.sleep(delay)

    # ------------------------------------------------------------------
    # Async path
    # ------------------------------------------------------------------
    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        call_start = time.perf_counter()
        total_attempts = 0

        for attempt in range(MAX_RETRIES):
            total_attempts = attempt + 1
            key, client = await KEY_POOL.acquire_async()

            with threading.Lock():
                object.__setattr__(self, "groq_api_key", key)
                object.__setattr__(self, "async_client", client)

            try:
                gen_start = time.perf_counter()
                result = await super()._agenerate(
                    messages, stop=stop, run_manager=run_manager, **kwargs
                )
                gen_duration = time.perf_counter() - gen_start
                KEY_POOL.report_success(key)

                # Record successful LLM call timing
                meta = {
                    "model": getattr(self, "model_name", getattr(self, "model", "unknown")),
                    "key_suffix": key[-4:],
                    "attempt": total_attempts,
                    "generation_s": round(gen_duration, 4),
                }
                if hasattr(result, "generations") and result.generations:
                    gen_info = result.generations[0] if result.generations[0] else None
                    if gen_info and hasattr(gen_info, "generation_info"):
                        usage = (gen_info.generation_info or {}).get("usage", {})
                        if usage:
                            meta["prompt_tokens"] = usage.get("prompt_tokens", 0)
                            meta["completion_tokens"] = usage.get("completion_tokens", 0)
                            meta["total_tokens"] = usage.get("total_tokens", 0)

                total_duration = time.perf_counter() - call_start
                metrics_collector.record(
                    category="llm_call",
                    name=f"groq_generate_async",
                    duration_s=total_duration,
                    metadata=meta,
                )
                return result

            except Exception as exc:
                is_last = attempt == MAX_RETRIES - 1

                if _is_rate_limit(exc):
                    KEY_POOL.report_rate_limit(key)
                elif _is_retryable(exc):
                    KEY_POOL.report_transient_failure(key)

                if not _is_retryable(exc) or is_last:
                    log.error(
                        "[Async] Giving up after %d attempt(s) — key ...%s: %s",
                        attempt + 1, key[-4:], exc,
                    )
                    raise

                delay = _compute_delay(attempt)
                log.warning(
                    "[Async] attempt=%d key=...%s %s — retrying in %.2fs",
                    attempt + 1, key[-4:],
                    "rate-limited" if _is_rate_limit(exc) else repr(exc),
                    delay,
                )
                await asyncio.sleep(delay)