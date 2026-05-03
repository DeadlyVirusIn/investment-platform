"""Engine B2 — shadow-only directional replacement candidate.

Goal: replace the negative-Sharpe directional Engine B with a
regime-aware, multi-horizon TSMOM strategy that NEVER conflicts with
Engine A's stress mean-reversion mandate.

Design contract:
  • Pure function. No DB writes, no execution, no risk param touch.
  • Output is a SignalDecision dataclass (action ∈ {LONG, FLAT}, reasons).
  • Long-flat only — no short side. Mirrors current Engine B universe.
  • All thresholds are explicit + override-able. No magic constants
    embedded in branching logic.

Inputs (priced PIT):
  prices : Sequence[float]  — chronological closes ending at decision bar
  regime : str | None       — "DIRECTIONAL" | "NEUTRAL_POS" | "NEUTRAL_NEG"
                              | "STRESS" | "CHOP" | other
  engine_a_active : bool    — True if Engine A is firing on same date

Outputs:
  SignalDecision:
    action:           "LONG" or "FLAT"
    trend_score:      weighted multi-horizon z-momentum
    components:       {ret_20d, ret_60d, ret_120d,
                        z20, z60, z120,
                        ma50, ma200, ma_slope_50d,
                        rvol_20d, vol_of_vol_20d, atr_ratio,
                        ma_confirm, regime_allow, chop_block}
    reasons:          list[str]   — explanation for action
    rejected_by:      list[str]   — gates that fired against LONG
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Sequence


# Defaults — tuned conservatively, not fit to any one sample.
DEFAULTS = dict(
    # Trend score gates
    trend_score_min=0.40,        # require positive momentum z-blend
    trend_score_extreme=1.20,    # strong enough to override chop
    # MA confirmation
    ma_fast=50,
    ma_slow=200,
    ma_slope_lookback=20,        # bars used to estimate slope
    # Regime
    allowed_regimes=("DIRECTIONAL", "NEUTRAL_POS"),
    stress_block_unless_engine_a_off=True,
    # Volatility / chop filter
    rvol_window=20,
    vol_of_vol_window=20,
    atr_window=14,
    rvol_high=0.30,              # annualized rvol cutoff
    vol_of_vol_high=0.50,        # rel stdev of rolling vol
    atr_expansion_threshold=1.30,  # ATR_now / ATR_60d_median
    # Score weights
    weight_z20=0.25,
    weight_z60=0.50,
    weight_z120=0.25,
    # Z-score lookback for normalization
    z_lookback=120,
    # Periods/yr
    periods_per_year=252,
)


@dataclass
class SignalDecision:
    action: str                          # "LONG" or "FLAT"
    trend_score: float
    components: dict
    reasons: list[str] = field(default_factory=list)
    rejected_by: list[str] = field(default_factory=list)
    advisory: bool = True

    def to_dict(self) -> dict:
        def _f(v):
            if isinstance(v, float):
                return None if not math.isfinite(v) else round(v, 6)
            return v
        return {
            "action": self.action,
            "trend_score": _f(self.trend_score),
            "components": {k: _f(v) for k, v in self.components.items()},
            "reasons": list(self.reasons),
            "rejected_by": list(self.rejected_by),
            "advisory": True,
            "execution_changed": False,
        }


# ---------------------------------------------------------------------------
# Helpers (pure, no I/O)
# ---------------------------------------------------------------------------

def _rets(prices: Sequence[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(prices)):
        a, b = float(prices[i - 1]), float(prices[i])
        if a == 0 or not (math.isfinite(a) and math.isfinite(b)):
            continue
        out.append(b / a - 1.0)
    return out


def _stdev(xs: Sequence[float]) -> float:
    arr = [float(x) for x in xs if math.isfinite(float(x))]
    if len(arr) < 2:
        return float("nan")
    try:
        return statistics.stdev(arr)
    except statistics.StatisticsError:
        return float("nan")


def _ret_h(prices: Sequence[float], h: int) -> float:
    if len(prices) <= h:
        return float("nan")
    a = float(prices[-(h + 1)])
    b = float(prices[-1])
    if a == 0 or not (math.isfinite(a) and math.isfinite(b)):
        return float("nan")
    return b / a - 1.0


def _zscore_of_h_returns(prices: Sequence[float], h: int,
                              lookback: int) -> float:
    """Rolling z-score of `h`-day returns over a `lookback`-window
    (window of overlapping h-day returns)."""
    if len(prices) < h + lookback + 1:
        return float("nan")
    series = []
    closes = list(prices)
    for i in range(h, len(closes)):
        a = closes[i - h]; b = closes[i]
        if a == 0 or not (math.isfinite(a) and math.isfinite(b)):
            continue
        series.append(b / a - 1.0)
    if len(series) < lookback:
        return float("nan")
    window = series[-lookback:]
    sd = _stdev(window)
    if not math.isfinite(sd) or sd == 0:
        return float("nan")
    return (series[-1] - sum(window) / len(window)) / sd


def _moving_avg(prices: Sequence[float], window: int) -> float:
    if len(prices) < window:
        return float("nan")
    return sum(prices[-window:]) / window


def _ma_slope(prices: Sequence[float], window: int,
                  lookback: int) -> float:
    """Simple slope: MA_now − MA_{lookback bars ago}, divided by lookback."""
    if len(prices) < window + lookback:
        return float("nan")
    now = sum(prices[-window:]) / window
    then = sum(prices[-(window + lookback):-lookback]) / window
    return (now - then) / lookback


def _rvol(prices: Sequence[float], window: int,
            periods_per_year: int) -> float:
    rets = _rets(prices)
    if len(rets) < window:
        return float("nan")
    sd = _stdev(rets[-window:])
    if not math.isfinite(sd):
        return float("nan")
    return sd * math.sqrt(periods_per_year)


def _vol_of_vol(prices: Sequence[float], window: int,
                  periods_per_year: int) -> float:
    """Std of rolling daily-vol series, normalized by mean. Higher
    = more unstable vol (whipsaw / regime transition)."""
    rets = _rets(prices)
    if len(rets) < window * 2:
        return float("nan")
    rolling = []
    for end in range(window, len(rets) + 1):
        sd = _stdev(rets[end - window:end])
        if math.isfinite(sd):
            rolling.append(sd)
    if len(rolling) < 5:
        return float("nan")
    mu = sum(rolling) / len(rolling)
    if mu == 0 or not math.isfinite(mu):
        return float("nan")
    return _stdev(rolling) / mu


def _atr_proxy(prices: Sequence[float], window: int) -> float:
    """ATR proxy from close-only data: rolling mean abs daily change."""
    if len(prices) < window + 1:
        return float("nan")
    diffs = [abs(float(prices[i]) - float(prices[i - 1]))
             for i in range(1, len(prices))]
    return sum(diffs[-window:]) / window


def _atr_ratio(prices: Sequence[float], window: int,
                  baseline_window: int = 60) -> float:
    if len(prices) < baseline_window + 1:
        return float("nan")
    atr_now = _atr_proxy(prices, window)
    atr_base = _atr_proxy(prices[-(baseline_window + 1):], baseline_window)
    if not (math.isfinite(atr_now) and math.isfinite(atr_base)) or \
        atr_base == 0:
        return float("nan")
    return atr_now / atr_base


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate(
    prices: Sequence[float],
    *,
    regime: str | None = None,
    engine_a_active: bool = False,
    config: dict | None = None,
) -> SignalDecision:
    """Decide LONG / FLAT for the next bar given current price history.

    `prices` is chronological closes; the decision is for the NEXT bar.
    """
    cfg = {**DEFAULTS, **(config or {})}
    reasons: list[str] = []
    rejected: list[str] = []

    # Components
    r20  = _ret_h(prices, 20)
    r60  = _ret_h(prices, 60)
    r120 = _ret_h(prices, 120)
    z20  = _zscore_of_h_returns(prices, 20,  cfg["z_lookback"])
    z60  = _zscore_of_h_returns(prices, 60,  cfg["z_lookback"])
    z120 = _zscore_of_h_returns(prices, 120, cfg["z_lookback"])

    # Trend score: weighted z-blend
    if all(math.isfinite(v) for v in (z20, z60, z120)):
        trend_score = (cfg["weight_z20"] * z20
                          + cfg["weight_z60"] * z60
                          + cfg["weight_z120"] * z120)
    else:
        trend_score = float("nan")

    ma50  = _moving_avg(prices, cfg["ma_fast"])
    ma200 = _moving_avg(prices, cfg["ma_slow"])
    slope50 = _ma_slope(prices, cfg["ma_fast"], cfg["ma_slope_lookback"])
    last = float(prices[-1]) if prices else float("nan")

    ma_confirm = (
        math.isfinite(ma50) and math.isfinite(ma200) and math.isfinite(last)
        and math.isfinite(slope50)
        and ma50 > ma200 and last > ma50 and slope50 > 0
    )

    rvol = _rvol(prices, cfg["rvol_window"], cfg["periods_per_year"])
    vov  = _vol_of_vol(prices, cfg["vol_of_vol_window"],
                          cfg["periods_per_year"])
    atr_r = _atr_ratio(prices, cfg["atr_window"])

    # Regime gate
    regime_allow = False
    if regime is None:
        regime_allow = True   # don't block on missing regime
        reasons.append("regime=None → permissive")
    elif regime in cfg["allowed_regimes"]:
        regime_allow = True
    elif regime == "STRESS":
        if cfg["stress_block_unless_engine_a_off"] and engine_a_active:
            rejected.append("regime=STRESS while Engine A active")
        else:
            regime_allow = True
            reasons.append("regime=STRESS but Engine A inactive → allowed")
    else:
        rejected.append(f"regime={regime} not in allowed set")

    # Chop / vol-of-vol filter
    chop_block = False
    if math.isfinite(vov) and vov >= cfg["vol_of_vol_high"]:
        if not (math.isfinite(trend_score)
                  and trend_score >= cfg["trend_score_extreme"]):
            chop_block = True
            rejected.append(
                f"vol_of_vol={vov:.2f}≥{cfg['vol_of_vol_high']} and "
                f"trend not extreme")

    # ATR-expansion filter (whipsaw guard): if ATR expanded but trend weak
    if math.isfinite(atr_r) and atr_r >= cfg["atr_expansion_threshold"]:
        if not (math.isfinite(trend_score)
                  and trend_score >= cfg["trend_score_min"]):
            chop_block = True
            rejected.append(
                f"atr_ratio={atr_r:.2f}≥{cfg['atr_expansion_threshold']}"
                f" with weak trend")

    # rvol absolute cap (unless trend is extreme)
    if math.isfinite(rvol) and rvol >= cfg["rvol_high"]:
        if not (math.isfinite(trend_score)
                  and trend_score >= cfg["trend_score_extreme"]):
            rejected.append(
                f"rvol={rvol:.2f}≥{cfg['rvol_high']} and trend not extreme")

    # Trend score floor
    trend_ok = math.isfinite(trend_score) and \
        trend_score >= cfg["trend_score_min"]
    if not trend_ok:
        rejected.append(
            f"trend_score={trend_score} < {cfg['trend_score_min']}")

    # Decision
    if rejected or chop_block or not (regime_allow and ma_confirm and trend_ok):
        action = "FLAT"
        if not ma_confirm:
            rejected.append("MA confirmation failed (need MA50>MA200, "
                              "price>MA50, slope50>0)")
    else:
        action = "LONG"
        reasons.append(
            f"trend_score={trend_score:.2f}, ma_confirm=True, "
            f"regime={regime or 'n/a'}")

    components = {
        "ret_20d": r20, "ret_60d": r60, "ret_120d": r120,
        "z20": z20, "z60": z60, "z120": z120,
        "ma50": ma50, "ma200": ma200, "ma_slope_50d": slope50,
        "price_last": last,
        "rvol_20d": rvol, "vol_of_vol_20d": vov, "atr_ratio": atr_r,
        "ma_confirm": ma_confirm,
        "regime_allow": regime_allow,
        "chop_block": chop_block,
    }
    return SignalDecision(
        action=action, trend_score=trend_score,
        components=components, reasons=reasons,
        rejected_by=list(dict.fromkeys(rejected)),
    )


def signal_position(
    prices: Sequence[float],
    *,
    regime: str | None = None,
    engine_a_active: bool = False,
    config: dict | None = None,
) -> int:
    """Convenience: 1 if LONG else 0 (long-flat only)."""
    d = evaluate(prices, regime=regime, engine_a_active=engine_a_active,
                  config=config)
    return 1 if d.action == "LONG" else 0
