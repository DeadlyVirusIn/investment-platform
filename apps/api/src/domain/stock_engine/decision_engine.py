"""Decision-engine orchestrator for stock-swing candidates.

Per-day pipeline:
  1. Load regime_snapshot(as_of) and factor_snapshot rows.
  2. Resolve point-in-time universe membership.
  3. Compute per-universe atr_p90 + median(atr_percent_14).
  4. For each asset in the evaluation set (universe members + any factor
     rows on as_of — latter may be extra-universe, flagged not_in_universe):
       a. Run ``first_rejection_reason`` → if rejection, log candidate.
       b. Else compute composite + action. Buys go into the top-N queue.
  5. Cap Buys at ``TOP_N`` (excess → status='accepted' action='Hold',
     rejection_reason='topn_overflow' per spec 5.6).
  6. Return list of candidate rows ready to upsert.

Shadow mode: the candidate rows are persisted regardless. No
``recommendation`` rows are created in Batch 4; ``recommendation_id`` stays
NULL. Downstream routing arrives in Batch 6.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    CandidateIdea,
    FactorSnapshot,
    RegimeSnapshot,
    UniverseMembership,
)
from apps.api.src.domain.stock_engine.eligibility import (
    REJ_HIGH_VOL_TOPN_OVERFLOW,
    REJ_TOPN_OVERFLOW,
    DecisionContext,
    PortfolioView,
    first_rejection_reason,
)
from apps.api.src.domain.stock_engine.scoring import (
    MODEL_VERSION,
    composite_score,
    factor_breakdown_payload,
)

DEFAULT_UNIVERSE = "stock_swing_v1"
TOP_N = 10                   # default Buy cap in low/normal vol regimes
HIGH_VOL_TOP_N = 3           # soft cap under vol_regime='high'
ATR_P90_QUANTILE = 0.90
ATR_MEDIAN_QUANTILE = 0.50


# ---------------------------------------------------------------------------
# Intermediate types
# ---------------------------------------------------------------------------


@dataclass
class CandidateRow:
    """In-memory representation of a candidate_idea row pending persistence."""
    as_of_date: dt.date
    asset_id: str
    model_version: str
    status: str
    action: str | None
    rejection_reason: str | None
    composite_score: Decimal | None
    confidence: Decimal | None
    factor_breakdown: dict
    regime_snapshot: dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _regime_payload(regime: RegimeSnapshot | None) -> dict:
    if regime is None:
        return {"missing": True}
    return {
        "as_of_date": regime.as_of_date.isoformat(),
        "benchmark_symbol": regime.benchmark_symbol,
        "market_trend": regime.market_trend,
        "vol_regime": regime.vol_regime,
        "breadth_regime": regime.breadth_regime,
        "sma50_over_sma200": regime.sma50_over_sma200,
        "realized_vol_20d": str(regime.realized_vol_20d),
        "atr_pctile_1y": str(regime.atr_pctile_1y),
    }


def _percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile of non-null values. q in [0,1]."""
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    idx = max(0, min(len(xs) - 1, int(round(q * (len(xs) - 1)))))
    return xs[idx]


def _universe_asset_ids(
    session: Session, universe_name: str, as_of: dt.date,
) -> set[str]:
    stmt = select(UniverseMembership.asset_id).where(
        UniverseMembership.universe_name == universe_name,
        UniverseMembership.start_date <= as_of,
        or_(
            UniverseMembership.end_date.is_(None),
            UniverseMembership.end_date >= as_of,
        ),
    )
    return {r[0] for r in session.execute(stmt).all()}


def _load_factor_rows(
    session: Session, asset_ids: Iterable[str], as_of: dt.date,
) -> list[FactorSnapshot]:
    stmt = (
        select(FactorSnapshot)
        .where(
            FactorSnapshot.as_of_date == as_of,
            FactorSnapshot.asset_id.in_(list(asset_ids)),
        )
    )
    return list(session.scalars(stmt))


def _compute_atr_quantiles(
    rows: list[FactorSnapshot],
) -> tuple[Decimal | None, Decimal | None]:
    """Return (p90, p50) of atr_percent_14 across eligible (non-stale,
    enough_data) rows. None on empty input."""
    vals: list[float] = []
    for r in rows:
        if not r.enough_data or r.stale_data:
            continue
        if r.atr_percent_14 is None:
            continue
        try:
            vals.append(float(r.atr_percent_14))
        except (TypeError, ValueError):
            continue
    p90 = _percentile(vals, ATR_P90_QUANTILE)
    p50 = _percentile(vals, ATR_MEDIAN_QUANTILE)
    return (
        Decimal(str(p90)) if p90 is not None else None,
        Decimal(str(p50)) if p50 is not None else None,
    )


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


def generate_candidates(
    session: Session,
    as_of: dt.date,
    universe_name: str = DEFAULT_UNIVERSE,
    portfolio: PortfolioView | None = None,
    top_n: int = TOP_N,
) -> list[CandidateRow]:
    """Generate candidate_idea rows for ``as_of``. One row per asset
    evaluated; all rejected rows carry a ``rejection_reason``.

    Evaluation set = universe members ∪ any asset with a factor_snapshot on
    ``as_of`` (the latter will be flagged ``not_in_universe`` and logged
    rather than silently dropped).
    """
    regime = session.get(RegimeSnapshot, as_of)
    universe_ids = _universe_asset_ids(session, universe_name, as_of)

    # Evaluation set: universe ∪ any asset with a factor row today
    all_factor_rows_today = list(session.scalars(
        select(FactorSnapshot).where(FactorSnapshot.as_of_date == as_of)
    ))
    factor_by_asset: dict[str, FactorSnapshot] = {
        r.asset_id: r for r in all_factor_rows_today
    }

    evaluated_ids: set[str] = set(universe_ids) | set(factor_by_asset.keys())
    if not evaluated_ids:
        return []

    atr_p90, atr_p50 = _compute_atr_quantiles(all_factor_rows_today)

    ctx = DecisionContext(
        regime=regime,
        universe_asset_ids=universe_ids,
        atr_p90=atr_p90,
        portfolio=portfolio or PortfolioView(),
    )

    regime_payload = _regime_payload(regime)

    accepted_buys: list[CandidateRow] = []
    rows: list[CandidateRow] = []

    # Need Asset rows for anything without a factor snapshot to still have a
    # candidate_idea row (e.g. a newly-added universe member with no bars).
    placeholder_asset_ids = evaluated_ids - set(factor_by_asset.keys())
    placeholders: dict[str, FactorSnapshot] = {}
    if placeholder_asset_ids:
        # Build an in-memory FactorSnapshot with all fields None / enough_data=False
        for aid in placeholder_asset_ids:
            fs = FactorSnapshot(
                as_of_date=as_of, asset_id=aid,
                feature_set_hash="",   # unknown — no snapshot existed
                enough_data=False, stale_data=False,
            )
            placeholders[aid] = fs

    for asset_id in sorted(evaluated_ids):
        row = factor_by_asset.get(asset_id) or placeholders[asset_id]
        reason = first_rejection_reason(ctx, row)

        score = composite_score(row, atr_p50)
        breakdown = factor_breakdown_payload(row, score)

        if reason is not None:
            rows.append(CandidateRow(
                as_of_date=as_of, asset_id=asset_id,
                model_version=MODEL_VERSION,
                status="rejected",
                action=None, rejection_reason=reason,
                composite_score=score.composite,
                confidence=score.confidence,
                factor_breakdown=breakdown,
                regime_snapshot=regime_payload,
            ))
            continue

        # Accepted — action mapped via composite
        cand = CandidateRow(
            as_of_date=as_of, asset_id=asset_id,
            model_version=MODEL_VERSION,
            status="accepted",
            action=score.action,
            rejection_reason=None,
            composite_score=score.composite,
            confidence=score.confidence,
            factor_breakdown=breakdown,
            regime_snapshot=regime_payload,
        )
        rows.append(cand)
        if cand.action == "Buy":
            accepted_buys.append(cand)

    # Top-N overflow.
    #
    # Determine cap by regime:
    #   * vol_regime='high' → soft cap of HIGH_VOL_TOP_N (3). Overflow rows
    #     become status='rejected' with reason='high_vol_topn_overflow' so
    #     they are clearly tagged as regime-constrained (not an
    #     accepted-but-held Buy).
    #   * otherwise → default cap of TOP_N (10). Overflow rows stay
    #     status='accepted', action='Hold', reason='topn_overflow' (spec
    #     5.6 literal, preserves existing Batch 4 behavior).
    is_high_vol = bool(regime is not None and regime.vol_regime == "high")
    effective_cap = HIGH_VOL_TOP_N if is_high_vol else top_n

    accepted_buys.sort(
        key=lambda c: (
            -(float(c.composite_score) if c.composite_score is not None else 0.0),
            c.asset_id,
        )
    )
    for overflow in accepted_buys[effective_cap:]:
        if is_high_vol:
            overflow.status = "rejected"
            overflow.action = None
            overflow.rejection_reason = REJ_HIGH_VOL_TOPN_OVERFLOW
        else:
            overflow.action = "Hold"
            overflow.rejection_reason = REJ_TOPN_OVERFLOW

    return rows
