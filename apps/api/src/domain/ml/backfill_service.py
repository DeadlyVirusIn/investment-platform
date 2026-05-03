"""Backfill historical_label rows for a date range.

Per-day pipeline:
  1. Load regime_snapshot(as_of). If missing → SKIP (log reason).
  2. Load factor_snapshot rows for the day (full universe).
  3. Compute per-universe atr_median for scoring.
  4. For each asset with enough_data=True:
       a. Compute composite + action.
       b. If action in {Buy, Trim, Sell}: compute triple-barrier forward
          label using price_bar n_bars forward from as_of+1.
       c. Upsert historical_label row.

Triple-barrier:
  - pt_price = entry * (1 + 2 * realized_vol_20d * sqrt(n_bars / 252))
  - sl_price = entry * (1 - 2 * realized_vol_20d * sqrt(n_bars / 252))
  - n_bars   = 20 (Buy/Trim/Sell all use 20-bar swing horizon)
  - label    = +1 if high >= pt before low <= sl
               -1 if low <= sl before high >= pt
                0 if neither within n_bars (timeout)

Deep validation sanity queries run at end; failure raises.
"""

from __future__ import annotations

import datetime as dt
import math
import uuid
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from loguru import logger
from sqlalchemy import and_, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import (
    Asset,
    FactorSnapshot,
    HistoricalLabel,
    PriceBar,
    RegimeSnapshot,
    UniverseMembership,
)
from apps.api.src.domain.stock_engine.decision_engine import (
    DEFAULT_UNIVERSE as ENGINE_DEFAULT_UNIVERSE,
    generate_candidates,
)
from apps.api.src.domain.stock_engine.scoring import (
    MODEL_VERSION,
    composite_score,
)

DEFAULT_UNIVERSE = "stock_swing_v1"
N_BARS_FORWARD = 20
BARRIER_SIGMA = Decimal("2.0")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class DaySkip:
    as_of: dt.date
    reason: str


@dataclass
class DayResult:
    as_of: dt.date
    universe: int
    candidates_evaluated: int
    labeled: int
    skip_reasons: dict[str, int]


def _business_days(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def _atr_median(rows: list[FactorSnapshot]) -> Decimal | None:
    vals = [r.atr_percent_14 for r in rows if r.atr_percent_14 is not None]
    if not vals:
        return None
    vals = sorted(vals)
    n = len(vals)
    mid = n // 2
    if n % 2 == 0:
        return (Decimal(vals[mid - 1]) + Decimal(vals[mid])) / Decimal("2")
    return Decimal(vals[mid])


def _resolve_universe(
    session: Session, universe: str, as_of: dt.date,
) -> dict[str, Asset]:
    stmt = (
        select(Asset)
        .join(
            UniverseMembership,
            UniverseMembership.asset_id == Asset.id,
        )
        .where(
            UniverseMembership.universe_name == universe,
            UniverseMembership.start_date <= as_of,
            (
                (UniverseMembership.end_date.is_(None))
                | (UniverseMembership.end_date >= as_of)
            ),
        )
    )
    return {a.id: a for a in session.execute(stmt).scalars().all()}


def _load_forward_bars(
    session: Session, asset_id: str, as_of: dt.date, n_bars: int,
) -> list[PriceBar]:
    # Need bars strictly AFTER as_of (use next business day close as entry).
    stmt = (
        select(PriceBar)
        .where(
            PriceBar.asset_id == asset_id,
            PriceBar.timeframe == "1d",
            PriceBar.ts > dt.datetime.combine(as_of, dt.time(23, 59, 59)),
        )
        .order_by(PriceBar.ts.asc())
        .limit(n_bars + 2)
    )
    return list(session.execute(stmt).scalars().all())


def _compute_barrier(
    entry: Decimal, realized_vol_20d: Decimal, n_bars: int,
) -> tuple[Decimal, Decimal]:
    """Symmetric barrier — back-compat wrapper."""
    return compute_triple_barrier_prices(
        entry, realized_vol_20d, n_bars,
        pt_sigma=BARRIER_SIGMA, sl_sigma=BARRIER_SIGMA,
    )


def compute_triple_barrier_prices(
    entry: Decimal, realized_vol_20d: Decimal, n_bars: int,
    pt_sigma: Decimal = BARRIER_SIGMA, sl_sigma: Decimal = BARRIER_SIGMA,
) -> tuple[Decimal, Decimal]:
    """Asymmetric-capable triple barrier. Returns (pt_price, sl_price).

    Asymmetric form per AFML Ch.3 for directional long-only strategies:
    typically `pt_sigma > sl_sigma` (wider profit, tighter stop). Defaults
    to the symmetric BARRIER_SIGMA on both sides (backward-compat).

    `realized_vol_20d` is fractional (0.02 == 2%).
    """
    scale = Decimal(str(math.sqrt(n_bars / 252.0)))
    pt_move = pt_sigma * realized_vol_20d * scale
    sl_move = sl_sigma * realized_vol_20d * scale
    pt = entry * (Decimal("1") + pt_move)
    sl = entry * (Decimal("1") - sl_move)
    return pt, sl


def label_from_bars(
    entry: Decimal, pt: Decimal, sl: Decimal, bars: list[PriceBar],
) -> tuple[int, int | None, Decimal, Decimal]:
    """Returns (label, first_touch_bar, exit_price, forward_return_pct).

    +1  pt hit first
    -1  sl hit first
     0  timeout (full n_bars elapsed)
    """
    for i, bar in enumerate(bars):
        if bar.high is None or bar.low is None:
            continue
        hi = Decimal(bar.high)
        lo = Decimal(bar.low)
        hit_pt = hi >= pt
        hit_sl = lo <= sl
        if hit_pt and hit_sl:
            # Assume worst-case: stop first (conservative).
            exit_p = sl
            ret = (exit_p / entry - Decimal("1")) * Decimal("100")
            return -1, i, exit_p, ret
        if hit_pt:
            exit_p = pt
            ret = (exit_p / entry - Decimal("1")) * Decimal("100")
            return 1, i, exit_p, ret
        if hit_sl:
            exit_p = sl
            ret = (exit_p / entry - Decimal("1")) * Decimal("100")
            return -1, i, exit_p, ret
    # Timeout — use final close.
    if not bars:
        return 0, None, entry, Decimal("0")
    final_close = Decimal(bars[-1].close) if bars[-1].close is not None else entry
    ret = (final_close / entry - Decimal("1")) * Decimal("100")
    return 0, None, final_close, ret


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------


def _upsert_label(session: Session, row: dict) -> None:
    stmt = pg_insert(HistoricalLabel).values(**row)
    stmt = stmt.on_conflict_do_update(
        index_elements=["as_of_date", "asset_id", "engine_version"],
        set_={k: v for k, v in row.items() if k not in ("id", "created_at")},
    )
    session.execute(stmt)


# ---------------------------------------------------------------------------
# Per-day processor
# ---------------------------------------------------------------------------


def _process_day(
    session: Session,
    as_of: dt.date,
    universe: str,
    include_actions: set[str],
) -> DayResult | DaySkip:
    regime = session.get(RegimeSnapshot, as_of)
    if regime is None:
        logger.info(
            "[backfill] {} SKIP reason=no_regime_snapshot", as_of,
        )
        return DaySkip(as_of, "no_regime_snapshot")

    if regime.realized_vol_20d is None:
        logger.info("[backfill] {} SKIP reason=no_realized_vol", as_of)
        return DaySkip(as_of, "no_realized_vol")
    rv = Decimal(regime.realized_vol_20d)
    if rv <= 0:
        logger.info("[backfill] {} SKIP reason=zero_vol", as_of)
        return DaySkip(as_of, "zero_vol")

    members = _resolve_universe(session, universe, as_of)
    if not members:
        logger.info("[backfill] {} SKIP reason=empty_universe", as_of)
        return DaySkip(as_of, "empty_universe")

    # Route through the production decision engine — applies all gates
    # (including the new extended_from_sma200 gate) and TOP_N / HIGH_VOL_TOP_N
    # caps identical to live paper trading.
    candidates = generate_candidates(session, as_of, universe_name=universe)

    labeled = 0
    candidates_evaluated = 0
    skip_reasons: Counter[str] = Counter()

    # Factor rows for the day — we still need to enrich rows with factor
    # values (composite_score / regime are already in CandidateRow payload
    # but individual factor values come from the factor_snapshot table).
    f_by_asset: dict[str, FactorSnapshot] = {
        f.asset_id: f for f in session.execute(
            select(FactorSnapshot).where(FactorSnapshot.as_of_date == as_of),
        ).scalars().all()
    }

    for cand in candidates:
        if cand.status != "accepted":
            skip_reasons[f"rejected_{cand.rejection_reason or 'unknown'}"] += 1
            continue
        if cand.action not in include_actions:
            # Includes TOP_N overflow rows routed to action='Hold'.
            skip_reasons[f"action_excluded_{cand.action}"] += 1
            continue

        candidates_evaluated += 1
        asset = members.get(cand.asset_id)
        if asset is None:
            skip_reasons["not_in_universe"] += 1
            continue

        f = f_by_asset.get(cand.asset_id)
        if f is None:
            skip_reasons["no_factor_row"] += 1
            continue

        bars = _load_forward_bars(session, cand.asset_id, as_of, N_BARS_FORWARD)
        if len(bars) < 2:
            skip_reasons["insufficient_forward_bars"] += 1
            continue
        entry_bar = bars[0]
        if entry_bar.close is None:
            skip_reasons["no_entry_close"] += 1
            continue
        entry = Decimal(entry_bar.close)
        forward_bars = bars[1 : 1 + N_BARS_FORWARD]
        if len(forward_bars) < N_BARS_FORWARD:
            skip_reasons["insufficient_forward_bars"] += 1
            continue

        pt, sl = _compute_barrier(entry, rv, N_BARS_FORWARD)
        label, first_touch, exit_price, fwd_ret = label_from_bars(
            entry, pt, sl, forward_bars,
        )

        row = {
            "id": str(uuid.uuid4()),
            "as_of_date": as_of,
            "asset_id": asset.id,
            "symbol": asset.symbol,
            "engine_version": MODEL_VERSION,
            "action": cand.action,
            "composite_score": cand.composite_score,
            "confidence": cand.confidence,
            "residual_momentum_20d": f.residual_momentum_20d,
            "residual_momentum_60d": f.residual_momentum_60d,
            "sector_relative_rank": f.sector_relative_rank,
            "trend_strength_20d": f.trend_strength_20d,
            "price_vs_200sma": f.price_vs_200sma,
            "atr_percent_14": f.atr_percent_14,
            "avg_dollar_volume_20d": f.avg_dollar_volume_20d,
            "market_trend": regime.market_trend,
            "vol_regime": regime.vol_regime,
            "realized_vol_20d": regime.realized_vol_20d,
            "atr_pctile_1y": regime.atr_pctile_1y,
            "label": label,
            "forward_return_pct": fwd_ret,
            "barrier_first_touch_bar": first_touch,
            "barrier_n_bars": N_BARS_FORWARD,
            "entry_price": entry,
            "exit_price": exit_price,
            "pt_price": pt,
            "sl_price": sl,
            "sector": asset.sector,
            "raw_payload": {
                "entry_bar_ts": entry_bar.ts.isoformat(),
                "factor_breakdown": cand.factor_breakdown,
            },
        }
        _upsert_label(session, row)
        labeled += 1

    session.commit()
    logger.info(
        "[backfill] {} universe={} candidates_in={} labeled={} skips={}",
        as_of, len(members), len(candidates), labeled, dict(skip_reasons),
    )
    return DayResult(
        as_of, len(members), candidates_evaluated, labeled, dict(skip_reasons),
    )


# ---------------------------------------------------------------------------
# Sanity validation
# ---------------------------------------------------------------------------


class BackfillValidationError(RuntimeError):
    pass


def _sanity_validate(session: Session, engine_version: str) -> None:
    total = session.execute(
        select(func.count()).select_from(HistoricalLabel).where(
            HistoricalLabel.engine_version == engine_version,
        )
    ).scalar_one()
    logger.info("[validate] total_rows={}", total)
    if total == 0:
        raise BackfillValidationError("no rows written")

    dist = dict(
        session.execute(
            select(HistoricalLabel.label, func.count())
            .where(HistoricalLabel.engine_version == engine_version)
            .group_by(HistoricalLabel.label)
        ).all()
    )
    logger.info("[validate] label_distribution={}", dist)
    total_lbl = sum(dist.values())
    hit = dist.get(1, 0) / total_lbl if total_lbl else 0
    timeout = dist.get(0, 0) / total_lbl if total_lbl else 0
    if timeout > 0.9:
        raise BackfillValidationError(
            f"label distribution degenerate: timeout={timeout:.2%}"
        )
    if hit > 0.9:
        raise BackfillValidationError(
            f"label distribution degenerate: hit={hit:.2%}"
        )

    engine_versions = session.execute(
        select(func.count(func.distinct(HistoricalLabel.engine_version)))
    ).scalar_one()
    logger.info("[validate] distinct_engine_versions={}", engine_versions)

    min_d, max_d, days = session.execute(
        select(
            func.min(HistoricalLabel.as_of_date),
            func.max(HistoricalLabel.as_of_date),
            func.count(func.distinct(HistoricalLabel.as_of_date)),
        ).where(HistoricalLabel.engine_version == engine_version)
    ).one()
    logger.info(
        "[validate] date_range={}..{} days_covered={}", min_d, max_d, days,
    )

    sparse = session.execute(
        select(HistoricalLabel.symbol, func.count())
        .where(HistoricalLabel.engine_version == engine_version)
        .group_by(HistoricalLabel.symbol)
        .having(func.count() < 5)
    ).all()
    if sparse:
        logger.warning("[validate] sparse_symbols={}", sparse)

    logger.info("[validate] OK")
    logger.info("")
    logger.info("=" * 72)
    logger.info("MANUAL VALIDATION CHECKLIST — confirm before Step 2:")
    logger.info("  [ ] Label distribution sane (no 90%+ of any class)")
    logger.info("  [ ] Engine version = {}", engine_version)
    logger.info("  [ ] Forward-return logic spot-checked on 5 rows")
    logger.info("  [ ] Regime labels match known market periods")
    logger.info("  [ ] No symbols with zero labels")
    logger.info("=" * 72)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def backfill_historical_labels(
    start: dt.date,
    end: dt.date,
    universe: str = DEFAULT_UNIVERSE,
    actions: set[str] | None = None,
    reset: bool = False,
) -> None:
    """Backfill historical_label rows between start and end (inclusive).

    reset=True → delete existing rows for the engine_version before run.
    actions    → default {"Buy", "Trim", "Sell"}; omit "Hold" (no thesis).
    """
    if actions is None:
        actions = {"Buy", "Trim", "Sell"}

    logger.info(
        "[backfill] start={} end={} universe={} engine_version={} actions={}",
        start, end, universe, MODEL_VERSION, sorted(actions),
    )

    with SessionLocal() as session:
        if reset:
            n = session.execute(
                delete(HistoricalLabel).where(
                    HistoricalLabel.engine_version == MODEL_VERSION,
                )
            ).rowcount
            session.commit()
            logger.warning("[backfill] RESET deleted {} rows", n)

        days_processed = 0
        days_skipped = 0
        total_labeled = 0
        agg_skips: Counter[str] = Counter()

        for as_of in _business_days(start, end):
            result = _process_day(session, as_of, universe, actions)
            if isinstance(result, DaySkip):
                days_skipped += 1
                agg_skips[result.reason] += 1
                continue
            days_processed += 1
            total_labeled += result.labeled
            for k, v in result.skip_reasons.items():
                agg_skips[k] += v

        logger.info("")
        logger.info("=" * 72)
        logger.info(
            "[backfill] SUMMARY processed={} skipped={} total_labeled={}",
            days_processed, days_skipped, total_labeled,
        )
        logger.info("[backfill] aggregate_skip_reasons={}", dict(agg_skips))
        logger.info("=" * 72)

        _sanity_validate(session, MODEL_VERSION)
