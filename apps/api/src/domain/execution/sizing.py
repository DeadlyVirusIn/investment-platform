"""Position sizing — normalized + fractional-Kelly, safe-bounded.

Two sizing functions, both return a position-size scalar in [0, MAX_SIZE]:

  normalized_size(...)  — conviction x inverse-vol, clipped
  kelly_size(...)       — fractional Kelly via edge/variance, clipped

Both are pure. No DB. No mutation. Deterministic given inputs.

No leverage (max_size=1.0 default). No shorting (negative outputs clipped).
No runaway on zero-vol (epsilon floor).
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Defaults — ALL VOLATILITIES ARE ANNUALIZED
# ---------------------------------------------------------------------------

MAX_POSITION_SIZE: float = 1.0     # 1.0 = fully-allocated per-trade; no leverage

# Target-vol is annualized. Literal value per task spec 2026-04-21.
# Callers pass realized_vol_20d already annualized (use
# `normalize.ensure_annualized_vol` at ingestion boundary).
TARGET_ANNUAL_VOL: float = 0.02
# Legacy alias kept to avoid breaking older callers; semantics are annualized.
TARGET_DAILY_VOL = TARGET_ANNUAL_VOL

VOL_SCALE_CAP: float = 1.5         # cap vol-scaling upside (low-vol bonus)
VOL_SCALE_FLOOR: float = 0.25      # floor vol-scaling downside (high-vol penalty)
EPS: float = 1e-6

# Kelly defaults
KELLY_SIGNAL_NEUTRAL: float = 0.5         # composite below this = no bet
KELLY_FULL_EDGE_RETURN: float = 0.02      # 2% expected return at composite=1.0
KELLY_FRACTION_DEFAULT: float = 0.25      # quarter-Kelly (Thorp's rec)


# ---------------------------------------------------------------------------
# Output container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SizingDecision:
    method: str                 # "normalized" | "kelly"
    raw_size: float
    conviction: float           # composite x confidence (or edge-mapped)
    vol_scale: float            # inverse-vol multiplier applied
    kelly_fraction: float       # 0 for normalized method
    capped_reason: str          # "" | "max" | "zero" | "neutral"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _safe_ratio(num: float, denom: float, default: float = 1.0) -> float:
    return num / denom if denom > EPS else default


# ---------------------------------------------------------------------------
# Normalized sizing
# ---------------------------------------------------------------------------


def normalized_size(
    composite_score: float,
    confidence: float,
    realized_vol_20d: float,
    *,
    target_vol: float = TARGET_ANNUAL_VOL,
    max_size: float = MAX_POSITION_SIZE,
    vol_scale_cap: float = VOL_SCALE_CAP,
    vol_scale_floor: float = VOL_SCALE_FLOOR,
) -> SizingDecision:
    """Conviction * inverse-vol, clipped.

    size = clip(composite * confidence * (target_vol / vol_20d), 0, max_size)

    Intuition:
      - composite * confidence     = conviction in [0, 1]
      - target_vol / realized_vol  = shrink in high-vol, expand in low-vol
      - clip at [0, max_size]      = no shorts, no leverage

    Zero composite or zero confidence → zero size.
    Zero vol → defaults to vol_scale=1.0 (not infinite).
    """
    c = _clip(composite_score, 0.0, 1.0)
    q = _clip(confidence, 0.0, 1.0)
    conviction = c * q
    if conviction <= 0.0:
        return SizingDecision(
            method="normalized", raw_size=0.0, conviction=0.0,
            vol_scale=0.0, kelly_fraction=0.0, capped_reason="zero",
        )

    vol = max(realized_vol_20d, 0.0)
    vol_scale_raw = _safe_ratio(target_vol, vol, default=1.0)
    vol_scale = _clip(vol_scale_raw, vol_scale_floor, vol_scale_cap)

    sized = conviction * vol_scale
    capped = sized > max_size
    final = min(sized, max_size)
    return SizingDecision(
        method="normalized",
        raw_size=final,
        conviction=conviction,
        vol_scale=vol_scale,
        kelly_fraction=0.0,
        capped_reason="max" if capped else "",
    )


# ---------------------------------------------------------------------------
# Fractional Kelly sizing (safe bounded)
# ---------------------------------------------------------------------------


def kelly_size(
    composite_score: float,
    confidence: float,
    realized_vol_20d: float,
    *,
    kelly_fraction: float = KELLY_FRACTION_DEFAULT,
    full_edge_return: float = KELLY_FULL_EDGE_RETURN,
    signal_neutral: float = KELLY_SIGNAL_NEUTRAL,
    max_size: float = MAX_POSITION_SIZE,
) -> SizingDecision:
    """Fractional Kelly: f* = edge / variance. Always bounded.

    Edge mapping:
        edge_return = conviction_above_neutral * full_edge_return * confidence

    Where:
        conviction_above_neutral = max(0, (composite - signal_neutral) / (1 - signal_neutral))

    So at composite=signal_neutral -> edge=0; at composite=1 -> edge=full_edge.

    Variance estimator: realized_vol_20d^2 (daily variance, matching edge scale).

    f* = edge / variance
    f_fractional = kelly_fraction * f*   (quarter-Kelly is standard)
    Clip to [0, max_size]. No leverage, no shorting.

    Zero vol defaults to zero size (undefined Kelly).
    """
    c = _clip(composite_score, 0.0, 1.0)
    q = _clip(confidence, 0.0, 1.0)

    # Edge only above neutral
    conviction_above = max(0.0, (c - signal_neutral)) / max(1.0 - signal_neutral, EPS)
    if conviction_above <= 0.0:
        return SizingDecision(
            method="kelly", raw_size=0.0, conviction=0.0,
            vol_scale=0.0, kelly_fraction=kelly_fraction,
            capped_reason="neutral",
        )
    edge_return = conviction_above * full_edge_return * q

    variance = realized_vol_20d * realized_vol_20d
    if variance <= EPS:
        # Undefined Kelly — refuse bet (safer than infinite size)
        return SizingDecision(
            method="kelly", raw_size=0.0, conviction=conviction_above * q,
            vol_scale=0.0, kelly_fraction=kelly_fraction,
            capped_reason="zero",
        )

    f_star = edge_return / variance
    f = kelly_fraction * f_star
    capped = f > max_size
    final = _clip(f, 0.0, max_size)
    return SizingDecision(
        method="kelly",
        raw_size=final,
        conviction=conviction_above * q,
        vol_scale=edge_return / variance if variance > EPS else 0.0,
        kelly_fraction=kelly_fraction,
        capped_reason="max" if capped else "",
    )
