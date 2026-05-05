"""Options strategy auto-promotion + dynamic sizing — paper-only.

Reads `options_strategy_outcome` to compute per-unit aggregates,
assigns conservative tiers, and proposes bounded position sizes.

ALL FUNCTIONS PURE. No env reads here. No DB writes here. Engine-side
gating (env flags + execution caps) lives in the operator script and
the paper exec runner.

Promotion units supported:
  * "strategy_name"
  * "underlying_strategy"          -> (underlying, strategy_name)
  * "iv_bucket_strategy"           -> (iv_bucket,  strategy_name)
  * "direction_strategy"           -> (direction,  strategy_name)

iv_bucket / direction are derived at evaluation time. Direction comes
from a static map; iv_bucket comes from `options_feature_daily.atm_iv`
on the outcome's as_of_date (look-up only — never fabricated).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Config — conservative defaults. Overridable via constructor injection.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PromotionThresholds:
    min_samples: int = 20
    min_window_trading_days: int = 10
    min_hit_rate: float = 0.55
    min_avg_forward_return_pct: float = 0.0  # strict positive enforced below
    max_avg_mae_pct: float = -0.10           # avg MAE >= -10% (less negative)
    min_liquidity_pass_rate: float = 0.90
    max_data_blocked_rate: float = 0.30
    min_positive_horizons: int = 2           # of {1D,3D,5D,10D,20D}


@dataclass(frozen=True)
class SizingConfig:
    base_pct: float = 0.005    # 0.5%
    min_pct: float = 0.0025    # 0.25%
    max_pct: float = 0.02      # 2.0%
    # Per-strategy hard cap (must not exceed regardless of promotion):
    hard_max_per_strategy_pct: float = 0.02
    # Total/aggregate caps — enforced by execution layer, surfaced here:
    hard_max_total_options_exposure_pct: float = 0.05
    hard_max_per_underlying_pct: float = 0.02
    hard_max_daily_new_pct: float = 0.03


# Strategy -> direction mapping. Static; no fabrication.
STRATEGY_DIRECTION: dict[str, str] = {
    "LONG_CALL": "bullish",
    "BULL_CALL_SPREAD": "bullish",
    "LONG_PUT": "bearish",
    "BEAR_PUT_SPREAD": "bearish",
    "SHORT_PUT_CREDIT_SPREAD": "bullish",
    "SHORT_CALL_CREDIT_SPREAD": "bearish",
    "IRON_CONDOR": "neutral",
}

VALID_UNITS = (
    "strategy_name",
    "underlying_strategy",
    "iv_bucket_strategy",
    "direction_strategy",
)
VALID_HORIZONS = ("1D", "3D", "5D", "10D", "20D")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def strategy_direction(strategy_name: str) -> str:
    return STRATEGY_DIRECTION.get(strategy_name.upper(), "neutral")


def iv_bucket_from_atm(atm_iv: float | None) -> str:
    """Map an ATM-IV value to a coarse bucket. Mirror of
    `_iv_bucket()` used by the suggestion engine. Returns 'unknown'
    when no atm_iv is available — never fabricates."""
    if atm_iv is None:
        return "unknown"
    iv = float(atm_iv)
    if iv < 0.25:
        return "low"
    if iv < 0.45:
        return "medium"
    return "high"


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

@dataclass
class PromotionCandidate:
    promotion_key: str
    unit: str                          # one of VALID_UNITS
    strategy_name: str
    underlying: str | None = None
    iv_bucket: str | None = None
    direction: str | None = None
    horizon: str = "5D"
    sample_count: int = 0
    n_finalized: int = 0
    window_trading_days: int = 0
    hit_rate: float = 0.0
    avg_forward_return_pct: float = 0.0
    avg_mae_pct: float = 0.0
    avg_mfe_pct: float = 0.0
    liquidity_pass_rate: float = 1.0  # default 1.0; we don't have a
                                       # rejection counter at outcome
                                       # level so we approximate with
                                       # 1 - data_blocked_rate
    data_blocked_rate: float = 0.0
    positive_horizon_count: int = 0
    tier: int = 0
    eligible: bool = False
    blocking_reasons: list[str] = field(default_factory=list)
    proposed_size_pct: float = 0.005


def _trading_days_between(start: dt.date, end: dt.date) -> int:
    """Coarse calendar-business-day count (Mon-Fri only). No holiday
    calendar; fine for promotion thresholds. Inclusive on both ends."""
    if end < start:
        return 0
    days = 0
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            days += 1
        cur = cur + dt.timedelta(days=1)
    return days


def _iv_bucket_lookup(
    session: Session, underlying: str, as_of: dt.date,
) -> str:
    row = session.execute(text("""
        SELECT atm_iv FROM options_feature_daily
        WHERE underlying = :u AND as_of_date = :d
    """), {"u": underlying, "d": as_of}).first()
    return iv_bucket_from_atm(row[0] if row else None)


def _aggregate_rows(
    session: Session, horizon: str,
) -> list[dict]:
    """Pull per (underlying, strategy_name, as_of) row stats from
    options_strategy_outcome at the specified horizon."""
    rows = session.execute(text("""
        SELECT underlying, strategy_name, as_of_date,
               outcome_label, forward_return_pct, mae_pct, mfe_pct
        FROM options_strategy_outcome
        WHERE horizon = :h
    """), {"h": horizon}).mappings().all()
    return [dict(r) for r in rows]


def _aggregate_per_horizon_positive(
    session: Session, group_filter,
) -> int:
    """Count distinct horizons (in VALID_HORIZONS) where the group's
    avg forward_return_pct is > 0 across all finalized rows.

    `group_filter` is a dict of equality predicates applied per row.
    """
    positives = 0
    for h in VALID_HORIZONS:
        rows = session.execute(text("""
            SELECT avg(forward_return_pct) AS avg_fr
            FROM options_strategy_outcome
            WHERE horizon = :h
              AND forward_return_pct IS NOT NULL
              AND ({where})
        """.format(where=group_filter["sql"])),
            {"h": h, **group_filter["params"]},
        ).first()
        if rows and rows[0] is not None and float(rows[0]) > 0:
            positives += 1
    return positives


def _build_candidate(
    session: Session,
    *, unit: str, key_parts: tuple,
    horizon: str,
    rows: list[dict],
    thresholds: PromotionThresholds,
    sizing: SizingConfig,
) -> PromotionCandidate:
    """Build one candidate from a list of outcome rows already grouped
    by the caller. Pure aggregation + thresholding."""
    strategy_name = ""
    underlying = None
    iv_bucket = None
    direction = None

    if unit == "strategy_name":
        strategy_name = key_parts[0]
        promotion_key = strategy_name
    elif unit == "underlying_strategy":
        underlying, strategy_name = key_parts
        promotion_key = f"{underlying}:{strategy_name}"
    elif unit == "iv_bucket_strategy":
        iv_bucket, strategy_name = key_parts
        promotion_key = f"{iv_bucket}_iv:{strategy_name}"
    elif unit == "direction_strategy":
        direction, strategy_name = key_parts
        promotion_key = f"{direction}:{strategy_name}"
    else:
        raise ValueError(f"unknown unit {unit!r}")

    sample_count = len(rows)
    finalized = [
        r for r in rows if r.get("forward_return_pct") is not None
    ]
    n_fin = len(finalized)

    if rows:
        as_of_dates = sorted({r["as_of_date"] for r in rows})
        window_days = _trading_days_between(
            as_of_dates[0], as_of_dates[-1],
        )
    else:
        window_days = 0

    hit_rate = 0.0
    avg_fr = 0.0
    avg_mae = 0.0
    avg_mfe = 0.0
    if n_fin:
        hit_rate = sum(
            1 for r in finalized if r["outcome_label"] == "good"
        ) / n_fin
        avg_fr = sum(
            float(r["forward_return_pct"]) for r in finalized
        ) / n_fin
        mae_vals = [
            float(r["mae_pct"]) for r in finalized
            if r.get("mae_pct") is not None
        ]
        mfe_vals = [
            float(r["mfe_pct"]) for r in finalized
            if r.get("mfe_pct") is not None
        ]
        if mae_vals:
            avg_mae = sum(mae_vals) / len(mae_vals)
        if mfe_vals:
            avg_mfe = sum(mfe_vals) / len(mfe_vals)

    data_blocked_count = sum(
        1 for r in rows if r["outcome_label"] == "data_blocked"
    )
    data_blocked_rate = (
        data_blocked_count / sample_count if sample_count else 0.0
    )
    liquidity_pass_rate = 1.0 - data_blocked_rate

    # Per-horizon positivity (group filter for SQL)
    positive_horizons = _count_positive_horizons(
        session, unit, key_parts,
    )

    # Eligibility
    blocking: list[str] = []
    if sample_count < thresholds.min_samples:
        blocking.append(
            f"sample_count<{thresholds.min_samples}"
        )
    if window_days < thresholds.min_window_trading_days:
        blocking.append(
            f"window_trading_days<"
            f"{thresholds.min_window_trading_days}"
        )
    if hit_rate < thresholds.min_hit_rate:
        blocking.append(f"hit_rate<{thresholds.min_hit_rate}")
    if avg_fr <= thresholds.min_avg_forward_return_pct:
        blocking.append("avg_forward_return_pct<=0")
    if avg_mae < thresholds.max_avg_mae_pct:
        blocking.append(
            f"avg_mae_pct<{thresholds.max_avg_mae_pct}"
        )
    if liquidity_pass_rate < thresholds.min_liquidity_pass_rate:
        blocking.append(
            f"liquidity_pass_rate<"
            f"{thresholds.min_liquidity_pass_rate}"
        )
    if data_blocked_rate > thresholds.max_data_blocked_rate:
        blocking.append(
            f"data_blocked_rate>"
            f"{thresholds.max_data_blocked_rate}"
        )
    if positive_horizons < thresholds.min_positive_horizons:
        blocking.append(
            f"positive_horizons<"
            f"{thresholds.min_positive_horizons}"
        )

    eligible = not blocking

    # Tier assignment (conservative)
    tier = 0
    if eligible:
        if hit_rate >= 0.65 and avg_fr >= 0.05 and sample_count >= 40:
            tier = 3
        elif hit_rate >= 0.60 and avg_fr >= 0.03:
            tier = 2
        else:
            tier = 1

    # Sizing
    proposed = _compute_size_pct(
        hit_rate=hit_rate, avg_fr=avg_fr, avg_mae=avg_mae,
        liquidity_pass_rate=liquidity_pass_rate,
        sizing=sizing, eligible=eligible, tier=tier,
    )

    return PromotionCandidate(
        promotion_key=promotion_key,
        unit=unit,
        strategy_name=strategy_name,
        underlying=underlying,
        iv_bucket=iv_bucket,
        direction=direction,
        horizon=horizon,
        sample_count=sample_count,
        n_finalized=n_fin,
        window_trading_days=window_days,
        hit_rate=round(hit_rate, 6),
        avg_forward_return_pct=round(avg_fr, 6),
        avg_mae_pct=round(avg_mae, 6),
        avg_mfe_pct=round(avg_mfe, 6),
        liquidity_pass_rate=round(liquidity_pass_rate, 6),
        data_blocked_rate=round(data_blocked_rate, 6),
        positive_horizon_count=positive_horizons,
        tier=tier,
        eligible=eligible,
        blocking_reasons=blocking,
        proposed_size_pct=proposed,
    )


def _count_positive_horizons(
    session: Session, unit: str, key_parts: tuple,
) -> int:
    """For this unit/key, count VALID_HORIZONS where avg forward_return
    is > 0 across finalized rows."""
    if unit == "strategy_name":
        where = "strategy_name = :s"
        params = {"s": key_parts[0]}
    elif unit == "underlying_strategy":
        where = "underlying = :u AND strategy_name = :s"
        params = {"u": key_parts[0], "s": key_parts[1]}
    else:
        # iv_bucket / direction: approximated using strategy + direction
        # since iv_bucket is computed per-as_of and would require a
        # join. For per-horizon positivity we just use strategy_name
        # for these units (conservative — same direction same strategy
        # is dominated by strategy effect).
        where = "strategy_name = :s"
        params = {"s": key_parts[1]}
    positives = 0
    for h in VALID_HORIZONS:
        row = session.execute(text(f"""
            SELECT avg(forward_return_pct) AS avg_fr
            FROM options_strategy_outcome
            WHERE horizon = :h
              AND forward_return_pct IS NOT NULL
              AND {where}
        """), {"h": h, **params}).first()
        if row and row[0] is not None and float(row[0]) > 0:
            positives += 1
    return positives


def _compute_size_pct(
    *, hit_rate: float, avg_fr: float, avg_mae: float,
    liquidity_pass_rate: float, sizing: SizingConfig,
    eligible: bool, tier: int,
) -> float:
    """Bounded sizing formula. Returns a fraction of equity in the
    closed interval [sizing.min_pct, sizing.hard_max_per_strategy_pct].
    Ineligible / tier 0–1 candidates always return base_pct (no boost).
    """
    if not eligible or tier <= 1:
        return float(sizing.base_pct)

    # Confidence multiplier: use hit_rate centered at 0.55, capped.
    # 0.55 -> 1.0; 0.65 -> 1.5; 0.75 -> 2.0; clamped to [0.6, 2.0].
    conf_mult = 1.0 + max(0.0, hit_rate - 0.55) * 10.0
    conf_mult = max(0.6, min(2.0, conf_mult))

    # Performance multiplier: tied to avg forward return.
    # 0% -> 1.0; +5% -> 1.5; +10% -> 2.0; clamped.
    perf_mult = 1.0 + max(0.0, avg_fr) * 10.0
    perf_mult = max(0.5, min(2.0, perf_mult))

    # Liquidity multiplier — penalises any data_blocked.
    liq_mult = max(0.5, min(1.0, liquidity_pass_rate))

    # Drawdown penalty: avg_mae more negative -> smaller multiplier.
    # avg_mae=  0.0  -> 1.0; -0.10 -> 0.8; -0.20 -> 0.6; clamped [0.4, 1.0]
    dd_pen = 1.0 + (avg_mae * 2.0)  # avg_mae is negative
    dd_pen = max(0.4, min(1.0, dd_pen))

    raw = sizing.base_pct * conf_mult * perf_mult * liq_mult * dd_pen

    # Tier 2 cap — half-way between min and hard cap.
    if tier == 2:
        upper = (sizing.base_pct + sizing.hard_max_per_strategy_pct) / 2.0
    else:  # tier 3
        upper = sizing.hard_max_per_strategy_pct

    sized = max(sizing.min_pct, min(upper, raw))
    sized = min(sized, sizing.hard_max_per_strategy_pct)
    return float(sized)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_promotions(
    session: Session,
    *, horizon: str = "5D",
    unit: str = "strategy_name",
    thresholds: PromotionThresholds = PromotionThresholds(),
    sizing: SizingConfig = SizingConfig(),
) -> list[PromotionCandidate]:
    """Aggregate outcomes by `unit` at `horizon`, compute candidates."""
    if horizon not in VALID_HORIZONS:
        raise ValueError(f"horizon must be one of {VALID_HORIZONS}")
    if unit not in VALID_UNITS:
        raise ValueError(f"unit must be one of {VALID_UNITS}")

    rows = _aggregate_rows(session, horizon)
    if not rows:
        return []

    # Group rows by the unit key.
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        if unit == "strategy_name":
            k = (r["strategy_name"],)
        elif unit == "underlying_strategy":
            k = (r["underlying"], r["strategy_name"])
        elif unit == "direction_strategy":
            d = strategy_direction(r["strategy_name"])
            k = (d, r["strategy_name"])
        elif unit == "iv_bucket_strategy":
            bucket = _iv_bucket_lookup(
                session, r["underlying"], r["as_of_date"],
            )
            k = (bucket, r["strategy_name"])
        else:
            continue
        groups.setdefault(k, []).append(r)

    out: list[PromotionCandidate] = []
    for key_parts, grouped in groups.items():
        cand = _build_candidate(
            session,
            unit=unit, key_parts=key_parts, horizon=horizon,
            rows=grouped, thresholds=thresholds, sizing=sizing,
        )
        out.append(cand)

    # Order: eligible first, then by hit_rate desc, then sample_count desc.
    out.sort(
        key=lambda c: (
            not c.eligible, -c.hit_rate, -c.sample_count,
        ),
    )
    return out


def candidate_to_dict(c: PromotionCandidate) -> dict:
    return {
        "promotion_key": c.promotion_key,
        "unit": c.unit,
        "strategy_name": c.strategy_name,
        "underlying": c.underlying,
        "iv_bucket": c.iv_bucket,
        "direction": c.direction,
        "horizon": c.horizon,
        "sample_count": c.sample_count,
        "n_finalized": c.n_finalized,
        "window_trading_days": c.window_trading_days,
        "hit_rate": c.hit_rate,
        "avg_forward_return_pct": c.avg_forward_return_pct,
        "avg_mae_pct": c.avg_mae_pct,
        "avg_mfe_pct": c.avg_mfe_pct,
        "liquidity_pass_rate": c.liquidity_pass_rate,
        "data_blocked_rate": c.data_blocked_rate,
        "positive_horizon_count": c.positive_horizon_count,
        "tier": c.tier,
        "eligible": c.eligible,
        "blocking_reasons": list(c.blocking_reasons),
        "proposed_size_pct": c.proposed_size_pct,
    }
