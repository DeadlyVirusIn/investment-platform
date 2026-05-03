"""Engine B governance policy.

Read-only evaluation. State machine ACTIVE / DEGRADED / DISABLED is
ADVISORY — does NOT change live trading behavior. Engine B continues
to fire until operator flips a future env flag.

Inputs:
  closed Engine B trade returns (net_ret_pct), oldest-first.

Outputs:
  EngineBVerdict — state, rolling stats, recommendation reason, and
  three simulation deltas (remove / gate-tsmom / replace-tsmom).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Sequence


# Thresholds — defaults, override-able from settings
SHARPE_DEGRADED = -0.30           # below → DEGRADED
SHARPE_DISABLED = -0.60           # below → DISABLED recommendation
HIT_DEGRADED    = 0.45            # below → DEGRADED
ROLLING_WINDOW  = 60              # trades

PERIODS_PER_YEAR = 252


def _sharpe(returns: Sequence[float]) -> float:
    arr = [float(r) for r in returns
           if r is not None and math.isfinite(float(r))]
    if len(arr) < 2:
        return float("nan")
    mu = sum(arr) / len(arr)
    try:
        sd = statistics.stdev(arr)
    except statistics.StatisticsError:
        return float("nan")
    if sd == 0 or not math.isfinite(sd):
        return float("nan")
    return mu / sd * math.sqrt(PERIODS_PER_YEAR)


def _max_drawdown_pct(returns: Sequence[float]) -> float:
    """Equity-style max drawdown (%), assuming returns are decimal."""
    eq = 1.0
    peak = 1.0
    worst = 0.0
    for r in returns:
        if r is None or not math.isfinite(float(r)):
            continue
        eq *= (1.0 + float(r))
        peak = max(peak, eq)
        dd = (eq - peak) / peak
        worst = min(worst, dd)
    return worst * 100.0


@dataclass
class EngineBVerdict:
    state: str                    # ACTIVE | DEGRADED | DISABLED
    rolling_sharpe: float
    full_sharpe: float
    rolling_hit: float
    full_hit: float
    drawdown_pct: float
    n: int
    rolling_n: int
    reason: str
    recommendation: str
    simulations: dict[str, float] = field(default_factory=dict)
    advisory: bool = True         # never actually changes execution

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "rolling_sharpe": round(self.rolling_sharpe, 4)
                                if math.isfinite(self.rolling_sharpe) else None,
            "full_sharpe": round(self.full_sharpe, 4)
                              if math.isfinite(self.full_sharpe) else None,
            "rolling_hit": round(self.rolling_hit, 4),
            "full_hit": round(self.full_hit, 4),
            "drawdown_pct": round(self.drawdown_pct, 4),
            "n": int(self.n),
            "rolling_n": int(self.rolling_n),
            "reason": self.reason,
            "recommendation": self.recommendation,
            "simulations": dict(self.simulations),
            "advisory": True,
            "execution_changed": False,
        }


def evaluate_engine_b(
    returns: Sequence[float],
    *,
    rolling_window: int = ROLLING_WINDOW,
    sharpe_degraded: float = SHARPE_DEGRADED,
    sharpe_disabled: float = SHARPE_DISABLED,
    hit_degraded: float = HIT_DEGRADED,
) -> EngineBVerdict:
    """Compute Engine B verdict from a chronological list of net returns.

    `returns` is decimal (e.g. 0.0023 for +23bps), oldest first.
    No live state mutation.
    """
    arr = [float(r) for r in returns
           if r is not None and math.isfinite(float(r))]
    n = len(arr)
    if n == 0:
        return EngineBVerdict(
            state="ACTIVE",
            rolling_sharpe=float("nan"),
            full_sharpe=float("nan"),
            rolling_hit=0.0,
            full_hit=0.0,
            drawdown_pct=0.0,
            n=0, rolling_n=0,
            reason="no closed Engine B trades yet",
            recommendation="MONITOR",
        )

    rolling = arr[-rolling_window:]
    full_sharpe   = _sharpe(arr)
    rolling_sharpe = _sharpe(rolling)
    rolling_hit   = sum(1 for r in rolling if r > 0) / max(1, len(rolling))
    full_hit      = sum(1 for r in arr if r > 0) / n
    dd            = _max_drawdown_pct(arr)

    # State decision: take the WORSE of full + rolling Sharpe so we
    # never label "ACTIVE" while the trailing window is collapsing.
    s = min(
        full_sharpe if math.isfinite(full_sharpe) else float("inf"),
        rolling_sharpe if math.isfinite(rolling_sharpe) else float("inf"),
    )
    if s <= sharpe_disabled or rolling_hit < hit_degraded - 0.10:
        state = "DISABLED"
        reason = (f"Sharpe {s:.2f} ≤ {sharpe_disabled:.2f} or "
                  f"rolling hit {rolling_hit:.0%} far below floor")
        recommendation = "RECOMMEND_DISABLE"
    elif s <= sharpe_degraded or rolling_hit < hit_degraded:
        state = "DEGRADED"
        reason = (f"Sharpe {s:.2f} ≤ {sharpe_degraded:.2f} or "
                  f"rolling hit {rolling_hit:.0%} < {hit_degraded:.0%}")
        recommendation = "RECOMMEND_GATE_OR_RESEARCH"
    else:
        state = "ACTIVE"
        reason = "Within performance band"
        recommendation = "MONITOR"

    sims = simulate_engine_b(arr)

    return EngineBVerdict(
        state=state,
        rolling_sharpe=rolling_sharpe,
        full_sharpe=full_sharpe,
        rolling_hit=rolling_hit,
        full_hit=full_hit,
        drawdown_pct=dd,
        n=n,
        rolling_n=len(rolling),
        reason=reason,
        recommendation=recommendation,
        simulations=sims,
    )


def simulate_engine_b(returns: Sequence[float]) -> dict[str, float]:
    """Return Sharpe under three counterfactuals.

    All operate on the SAME entry dates as the real trades — they answer:
    "if Engine B had done X instead, what Sharpe would we have seen?"

      remove        : zero-out every trade — Sharpe undefined / 0 base
      gate_tsmom    : assume gate filters 50% of trades randomly to keep
                       only the better half (proxy: drop bottom 50%)
      replace_tsmom : flip Engine B trade direction when our audit
                       showed TSMOM signal disagreed (here we proxy by
                       flipping bottom 30% sign, since negative-edge
                       proxies misalignment)
    """
    arr = [float(r) for r in returns
           if r is not None and math.isfinite(float(r))]
    if not arr:
        return {"remove": 0.0, "gate_tsmom": float("nan"),
                "replace_tsmom": float("nan")}

    # Remove: no trades → Sharpe defined as 0 (no edge, no DD)
    sim_remove = 0.0

    # Gate proxy: keep only top-50% by realized return (best case bound)
    sorted_top = sorted(arr, reverse=True)[: max(1, len(arr) // 2)]
    sim_gate = _sharpe(sorted_top)

    # Replace proxy: flip sign of bottom-30% (replacement strategy
    # would have refused those trades; flipping is upper-bound estimate)
    cutoff = len(arr) - max(1, int(len(arr) * 0.30))
    flipped = sorted(arr)
    flipped = [-r for r in flipped[:cutoff]] + flipped[cutoff:]
    sim_replace = _sharpe(flipped)

    return {
        "remove":        round(sim_remove, 4),
        "gate_tsmom":    round(sim_gate, 4) if math.isfinite(sim_gate) else None,
        "replace_tsmom": round(sim_replace, 4)
                            if math.isfinite(sim_replace) else None,
    }
