"""Phase F7 — in-process metrics + cost accounting for the
agent-insights layer.

These counters are deliberately process-local: every API process
maintains its own snapshot, and a restart resets them. That's
acceptable F7 scope — the goal is operator visibility, not
billing truth. A future phase can wire a real meter (Prometheus,
StatsD, etc.) once the existing operator dashboards stabilize.

NEVER blocks a request. Every public function swallows its own
errors so a bug here cannot leak into the response path.
"""

from __future__ import annotations

import datetime as _dt
import threading
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------
# Pricing constants
# ---------------------------------------------------------------------

# Conservative per-Mtok rates for the default Haiku tier. Mirrors
# the figures already used by `research/providers/anthropic_provider.py`
# so the cost accounting on dashboards is internally consistent.
INPUT_COST_PER_MTOK_USD: float = 1.00
OUTPUT_COST_PER_MTOK_USD: float = 5.00

# Fallback char-to-token ratio when the SDK response did not carry
# usage info. Matches Anthropic's published rule of thumb.
CHARS_PER_TOKEN: int = 4


# ---------------------------------------------------------------------
# Counter container (mutable, lock-protected)
# ---------------------------------------------------------------------

@dataclass
class _Counters:
    requests_total: int = 0
    disabled_total: int = 0
    cache_hit_total: int = 0
    cache_miss_total: int = 0
    llm_calls_total: int = 0
    safety_rejected_total: int = 0
    transport_error_total: int = 0
    # F8: number of times the LLM call was blocked at the cost-guard
    # gate. Independent of `disabled_total` (which counts feature-
    # flag disablement) and `safety_rejected_total` (which counts
    # post-call rejections).
    cost_guard_blocked_total: int = 0
    estimated_cost_usd_total: float = 0.0
    last_call_at: str | None = None
    last_error_reason: str | None = None


_lock = threading.Lock()
_state: _Counters = _Counters()


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def reset() -> None:
    """Test-only: reset all counters to zero. Production code
    SHOULD NOT call this."""
    global _state
    with _lock:
        _state = _Counters()


def snapshot() -> dict[str, Any]:
    """Return a JSON-serializable snapshot. Cost is rounded to
    6 decimal places so micro-cost rounding errors do not leak
    into the status payload."""
    with _lock:
        return {
            "requests_total": _state.requests_total,
            "disabled_total": _state.disabled_total,
            "cache_hit_total": _state.cache_hit_total,
            "cache_miss_total": _state.cache_miss_total,
            "llm_calls_total": _state.llm_calls_total,
            "safety_rejected_total": _state.safety_rejected_total,
            "transport_error_total": _state.transport_error_total,
            "cost_guard_blocked_total":
                _state.cost_guard_blocked_total,
            "estimated_cost_usd_total": round(
                _state.estimated_cost_usd_total, 6,
            ),
            "last_call_at": _state.last_call_at,
            "last_error_reason": _state.last_error_reason,
        }


def is_cost_guard_reached(guard_usd: float) -> bool:
    """True iff the configured guard is positive AND the running
    estimated cost has met or exceeded it. A guard <= 0 means
    "unlimited" — always returns False so the endpoint never
    short-circuits on a misconfigured ceiling."""
    try:
        guard = float(guard_usd or 0.0)
    except (TypeError, ValueError):
        return False
    if guard <= 0.0:
        return False
    with _lock:
        return _state.estimated_cost_usd_total >= guard


def record_request() -> None:
    try:
        with _lock:
            _state.requests_total += 1
    except Exception:  # noqa: BLE001 — never block the endpoint
        pass


def record_disabled() -> None:
    try:
        with _lock:
            _state.disabled_total += 1
    except Exception:  # noqa: BLE001
        pass


def record_cache_hit() -> None:
    try:
        with _lock:
            _state.cache_hit_total += 1
    except Exception:  # noqa: BLE001
        pass


def record_cache_miss() -> None:
    try:
        with _lock:
            _state.cache_miss_total += 1
    except Exception:  # noqa: BLE001
        pass


def _estimate_cost_usd(
    *,
    prompt: str,
    body: str,
    usage: Any | None,
) -> float:
    """Return non-negative cost estimate. NEVER raises — falls back
    to char/4 token approximation when the SDK omitted usage."""
    try:
        if usage is not None:
            tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
            tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
        else:
            tokens_in = max(len(prompt or "") // CHARS_PER_TOKEN, 0)
            tokens_out = max(len(body or "") // CHARS_PER_TOKEN, 0)
        tokens_in = max(tokens_in, 0)
        tokens_out = max(tokens_out, 0)
        cost = (
            (tokens_in / 1_000_000.0) * INPUT_COST_PER_MTOK_USD
            + (tokens_out / 1_000_000.0) * OUTPUT_COST_PER_MTOK_USD
        )
        return max(0.0, float(cost))
    except Exception:  # noqa: BLE001 — accounting must never raise
        return 0.0


def record_llm_call(
    *,
    prompt: str,
    body: str,
    usage: Any | None = None,
) -> None:
    """Increment the LLM-call counter and add an estimated cost.
    Only invoked AFTER the SDK returned a non-empty body — empty
    bodies and timeouts go through `record_transport_error`."""
    cost = _estimate_cost_usd(prompt=prompt, body=body, usage=usage)
    try:
        with _lock:
            _state.llm_calls_total += 1
            _state.estimated_cost_usd_total += cost
            _state.last_call_at = _dt.datetime.now(
                _dt.timezone.utc,
            ).isoformat()
    except Exception:  # noqa: BLE001
        pass


def record_safety_rejection(reason: str) -> None:
    """Validation gate (forbidden phrase, hallucinated number,
    code fence) refused the response."""
    try:
        with _lock:
            _state.safety_rejected_total += 1
            _state.last_error_reason = f"safety:{(reason or '').strip()[:240]}"
    except Exception:  # noqa: BLE001
        pass


def record_transport_error(reason: str) -> None:
    """SDK / network / empty-body failure. Distinct from a safety
    rejection so dashboards can tell the two apart."""
    try:
        with _lock:
            _state.transport_error_total += 1
            _state.last_error_reason = f"transport:{(reason or '').strip()[:240]}"
    except Exception:  # noqa: BLE001
        pass


def record_cost_guard_blocked(*, guard_usd: float) -> None:
    """The cost-guard gate refused an LLM call. Sets last_error_reason
    to a `guard:` prefix so dashboards can distinguish guard blocks
    from safety rejections / transport failures."""
    try:
        with _lock:
            _state.cost_guard_blocked_total += 1
            _state.last_error_reason = (
                f"guard:cost_blocked:guard={guard_usd:.6f}"
            )
    except Exception:  # noqa: BLE001
        pass
