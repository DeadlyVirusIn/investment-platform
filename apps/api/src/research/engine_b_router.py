"""Engine B → B2 controlled rollout router.

Pure function. NEVER mutates state. NEVER calls into execution.
Determines which directional signal would be routed under the
current ENGINE_B_MODE. Production wiring continues to use Engine B
unchanged for ANY mode that is not strictly FULL_B2 / PARTIAL_B2_*
AND only after operator-controlled flag is flipped.

Modes:
  LEGACY          — execute Engine B (production unchanged)
  SHADOW_COMPARE  — execute Engine B; LOG B and B2 for comparison
  PARTIAL_B2_25   — route 25% of decision days to B2
  PARTIAL_B2_50   — route 50%
  PARTIAL_B2_75   — route 75%
  FULL_B2         — route 100% of decision days to B2

The probabilistic split is **deterministic per (date, mode)** so the
backtest of any historical day yields the same answer as the live
runner for that day. No PRNG state leakage.

This module DOES NOT modify any production execution path. The router
output is consumed by:
  • the shadow runner (logging only)
  • the transition API (display only)
  • a future runner toggle (not wired yet)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date


VALID_MODES = (
    "LEGACY", "SHADOW_COMPARE",
    "PARTIAL_B2_25", "PARTIAL_B2_50", "PARTIAL_B2_75",
    "FULL_B2",
)

# Modes that, if any code ever reads `RoutedDecision.execution_changed`
# as `True`, indicate routing has actively replaced Engine B with B2.
EXECUTION_CHANGE_MODES = (
    "PARTIAL_B2_25", "PARTIAL_B2_50", "PARTIAL_B2_75", "FULL_B2",
)


@dataclass(frozen=True)
class RoutedDecision:
    mode: str
    routed_signal: str           # LONG | FLAT
    engine_b_signal: str         # LONG | FLAT
    b2_signal: str               # LONG | FLAT
    routed_engine: str           # B | B2
    divergence: bool             # True if B != B2
    note: str
    execution_changed: bool      # True iff routed_engine == 'B2'

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "routed_signal": self.routed_signal,
            "engine_b_signal": self.engine_b_signal,
            "b2_signal": self.b2_signal,
            "routed_engine": self.routed_engine,
            "divergence": bool(self.divergence),
            "note": self.note,
            "execution_changed": bool(self.execution_changed),
        }


def _validate(mode: str) -> str:
    if mode not in VALID_MODES:
        raise ValueError(
            f"unknown ENGINE_B_MODE={mode!r}; "
            f"allowed: {', '.join(VALID_MODES)}")
    return mode


def _deterministic_pick(d: date, partial_pct: int) -> bool:
    """Stable per-day decision. Hash(date) → uniform [0,1)."""
    h = hashlib.sha256(str(d.isoformat()).encode("utf-8")).digest()
    # First 8 bytes → uint64 → normalize to [0,1)
    val = int.from_bytes(h[:8], "big") / (2 ** 64)
    return val < (partial_pct / 100.0)


def route(
    *,
    mode: str,
    as_of: date,
    engine_b_signal: str,
    b2_signal: str,
) -> RoutedDecision:
    """Compute routed decision for `as_of`.

    `engine_b_signal` and `b2_signal` are computed independently by the
    caller (deterministic Engine B logic + Engine B2 TSMOM-no-stress).
    """
    m = _validate(mode)
    eb = "LONG" if str(engine_b_signal).upper() == "LONG" else "FLAT"
    b2 = "LONG" if str(b2_signal).upper() == "LONG" else "FLAT"
    div = eb != b2

    if m == "LEGACY":
        return RoutedDecision(
            mode=m, routed_signal=eb,
            engine_b_signal=eb, b2_signal=b2,
            routed_engine="B", divergence=div,
            note="LEGACY: execution unchanged; Engine B routes",
            execution_changed=False,
        )

    if m == "SHADOW_COMPARE":
        return RoutedDecision(
            mode=m, routed_signal=eb,
            engine_b_signal=eb, b2_signal=b2,
            routed_engine="B", divergence=div,
            note="SHADOW_COMPARE: execution unchanged; both signals "
                  "logged for B-vs-B2 analysis",
            execution_changed=False,
        )

    if m == "FULL_B2":
        return RoutedDecision(
            mode=m, routed_signal=b2,
            engine_b_signal=eb, b2_signal=b2,
            routed_engine="B2", divergence=div,
            note="FULL_B2: routed signal is B2",
            execution_changed=True,
        )

    if m.startswith("PARTIAL_B2_"):
        try:
            pct = int(m.split("_")[-1])
        except ValueError as e:
            raise ValueError(f"unparseable partial mode: {m!r}") from e
        pick_b2 = _deterministic_pick(as_of, pct)
        if pick_b2:
            return RoutedDecision(
                mode=m, routed_signal=b2,
                engine_b_signal=eb, b2_signal=b2,
                routed_engine="B2", divergence=div,
                note=(f"PARTIAL_B2_{pct}: deterministic pick → B2 "
                       f"({pct}% target)"),
                execution_changed=True,
            )
        return RoutedDecision(
            mode=m, routed_signal=eb,
            engine_b_signal=eb, b2_signal=b2,
            routed_engine="B", divergence=div,
            note=(f"PARTIAL_B2_{pct}: deterministic pick → B "
                   f"({100-pct}% target)"),
            execution_changed=False,
        )

    # Unreachable due to _validate, but defensive.
    raise ValueError(f"unhandled mode {m!r}")
