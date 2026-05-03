"""Scheduled job: label RecommendationOutcome rows via triple-barrier.

Runs after the nightly recommendation job. Only labels rows whose parent
Recommendation is at least 30 days old and whose barrier_label is still null.
Deterministic — no randomness, no lookahead.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from loguru import logger
from sqlalchemy import select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import (
    PriceBar,
    Recommendation,
    RecommendationEvidence,
    RecommendationOutcome,
)
from apps.api.src.domain.features.regime_classifier import classify_all
from apps.api.src.domain.recommendations.outcome_labeling import (
    classify_signal_type,
    compute_sigma_t0,
    horizon_for_signal,
    realized_return_at,
    triple_barrier_label,
)

MIN_AGE_DAYS = 30       # only score recs this old or older
SIGMA_LOOKBACK_DAYS = 30  # trailing window for sigma_t0
PT_SIGMAS = Decimal("2.0")
SL_SIGMAS = Decimal("2.0")


def _load_evidence_factor_keys(session, recommendation_id: str) -> list[str]:
    stmt = select(RecommendationEvidence.evidence_type).where(
        RecommendationEvidence.recommendation_id == recommendation_id,
    )
    return [k for (k,) in session.execute(stmt).all() if k]


def _load_price_series(
    session,
    asset_id: str,
    start: dt.datetime,
    end: dt.datetime,
) -> list[tuple[dt.datetime, Decimal]]:
    stmt = (
        select(PriceBar)
        .where(
            PriceBar.asset_id == asset_id,
            PriceBar.timeframe == "1d",
            PriceBar.ts >= start,
            PriceBar.ts <= end,
        )
        .order_by(PriceBar.ts.asc())
    )
    result: list[tuple[dt.datetime, Decimal]] = []
    for bar in session.execute(stmt).scalars():
        price = bar.adjusted_close if bar.adjusted_close is not None else bar.close
        if price is None:
            continue
        if not isinstance(price, Decimal):
            price = Decimal(str(price))
        result.append((bar.ts, price))
    return result


def score_one_outcome(session, outcome: RecommendationOutcome, rec: Recommendation) -> bool:
    """Label a single outcome row in-place. Returns True if updated."""
    entry_ts = rec.generated_at
    if entry_ts is None:
        return False

    factor_keys = _load_evidence_factor_keys(session, rec.id)
    signal_type = classify_signal_type(factor_keys)
    n_bars = horizon_for_signal(signal_type)

    start = entry_ts - dt.timedelta(days=SIGMA_LOOKBACK_DAYS * 2)
    # Calendar slack = 2× trading horizon, enough for weekends/holidays.
    end = entry_ts + dt.timedelta(days=n_bars * 2)
    series = _load_price_series(session, rec.asset_id, start, end)
    if len(series) < SIGMA_LOOKBACK_DAYS:
        return False

    prices_before_entry = [px for ts, px in series if ts <= entry_ts]
    sigma = compute_sigma_t0(prices_before_entry, lookback=20)
    if sigma is None or sigma <= 0:
        return False

    p0: Decimal | None = None
    if outcome.price_at_recommendation is not None:
        p0 = outcome.price_at_recommendation if isinstance(outcome.price_at_recommendation, Decimal) \
            else Decimal(str(outcome.price_at_recommendation))

    barrier = triple_barrier_label(
        series, entry_ts, sigma,
        pt=PT_SIGMAS, sl=SL_SIGMAS, n_bars=n_bars,
    )
    if barrier is None:
        return False

    r30 = realized_return_at(series, entry_ts, 30, entry_price=p0)
    r90 = realized_return_at(series, entry_ts, 90, entry_price=p0)

    outcome.barrier_label = barrier.label
    outcome.barrier_first_touch_at = barrier.first_touch_at
    outcome.barrier_n_bars = n_bars
    outcome.signal_type = signal_type
    if p0 is None:
        outcome.price_at_recommendation = barrier.entry_price

    if r30 is not None:
        price_30d, ret_30d = r30
        outcome.price_after_30d = price_30d
        outcome.realized_30d_return = ret_30d
    if r90 is not None:
        price_90d, ret_90d = r90
        outcome.price_after_90d = price_90d
        outcome.realized_90d_return = ret_90d

    # Regime classification — only pre-entry prices (no lookahead).
    regimes = classify_all(prices_before_entry)
    outcome.trend_regime = regimes["trend_regime"]
    outcome.volatility_regime = regimes["volatility_regime"]
    outcome.drawdown_regime = regimes["drawdown_regime"]

    return True


async def score_recommendation_outcomes() -> None:
    """Iterate unlabeled outcomes for recs older than MIN_AGE_DAYS and label them."""
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=MIN_AGE_DAYS)

    updated = 0
    scanned = 0

    with SessionLocal() as session:
        stmt = (
            select(RecommendationOutcome, Recommendation)
            .join(Recommendation, RecommendationOutcome.recommendation_id == Recommendation.id)
            .where(
                Recommendation.generated_at <= cutoff,
                RecommendationOutcome.barrier_label.is_(None),
            )
        )
        for outcome, rec in session.execute(stmt).all():
            scanned += 1
            try:
                if score_one_outcome(session, outcome, rec):
                    updated += 1
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "score_outcomes failed for rec={} asset={}: {}",
                    rec.id, rec.asset_id, exc,
                )
        session.commit()

    logger.info(
        "score_recommendation_outcomes complete: scanned={} updated={}",
        scanned, updated,
    )
