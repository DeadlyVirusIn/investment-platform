"""Walk-forward validation harness for recommendation outcomes.

Audits whether realized performance in-sample (IS) holds up in the adjacent
out-of-sample (OOS) window. Uses calendar-day windows applied to the
`Recommendation.generated_at` timeline — not training a model, not replaying
the engine. The question answered: "are the outcomes in each fresh OOS block
as good as the outcomes in the preceding IS block?"

Deterministic. Decimal-only. Divide-by-zero guarded. No pandas / numpy.

Metric used for WFE: **expectancy** (mean realized return per rec).
Reason: it is well-defined for small samples (handles zero-loss windows that
would blow up `profit_factor`), sign-aware, and scale-free across windows.
Alternative metric `total_return_proxy` (sum of realized returns) is also
computed but not used for WFE because it grows with trade count and so
doesn't answer the "per-trade edge holds up" question cleanly.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Literal, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Recommendation,
    RecommendationEvidence,
    RecommendationOutcome,
)
from apps.api.src.domain.recommendations.outcome_labeling import (
    classify_signal_type,
)

# ---------------------------------------------------------------------------
# Defaults (calendar-day approximations of trading windows)
# ---------------------------------------------------------------------------

DEFAULT_TRAIN_DAYS = 252    # ~1 year of trading days
DEFAULT_TEST_DAYS = 63      # ~3 months of trading days
DEFAULT_STEP_DAYS = 63      # roll by 3 months

MIN_SAMPLES_FOR_SHARPE = 2

Stability = Literal["ROBUST", "MODERATE", "WEAK", "UNKNOWN"]


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class OutcomeRow:
    """Minimal outcome record used by the harness — decoupled from ORM."""
    recommendation_id: str
    asset_id: str
    generated_at: dt.datetime
    barrier_label: int | None                    # -1 | 0 | +1 | None
    realized_return: Decimal | None              # realized_30d_return by default
    signal_type: str                              # 'trend' | 'mean_reversion' | 'default'


@dataclass
class SplitWindow:
    train_start: dt.datetime
    train_end: dt.datetime       # exclusive
    test_start: dt.datetime      # == train_end
    test_end: dt.datetime        # exclusive


@dataclass
class WindowMetrics:
    count: int
    wins: int
    losses: int
    breakeven: int
    total_return_proxy: Decimal | None
    hit_rate: Decimal | None
    expectancy: Decimal | None
    profit_factor: Decimal | None
    sharpe: Decimal | None


@dataclass
class SplitResult:
    index: int
    window: SplitWindow
    is_metrics: WindowMetrics
    oos_metrics: WindowMetrics
    wfe: Decimal | None
    stability: Stability
    notes: list[str] = field(default_factory=list)


@dataclass
class WalkForwardReport:
    splits: list[SplitResult]
    aggregate_wfe: Decimal | None
    aggregate_stability: Stability
    config: dict[str, int]
    stratified_by: str | None


# ---------------------------------------------------------------------------
# Splitter
# ---------------------------------------------------------------------------


def build_splits(
    first_ts: dt.datetime,
    last_ts: dt.datetime,
    train_days: int = DEFAULT_TRAIN_DAYS,
    test_days: int = DEFAULT_TEST_DAYS,
    step_days: int = DEFAULT_STEP_DAYS,
) -> list[SplitWindow]:
    """Rolling-origin splits covering [first_ts, last_ts].

    Each split has a `train_days` IS window immediately followed by a
    `test_days` OOS window. Advances by `step_days`. Stops when the test
    window would extend past `last_ts`.

    Returns [] when the span is too short for even one full split.
    """
    if train_days <= 0 or test_days <= 0 or step_days <= 0:
        return []
    if last_ts <= first_ts:
        return []

    splits: list[SplitWindow] = []
    cursor = first_ts
    span_needed = dt.timedelta(days=train_days + test_days)
    while cursor + span_needed <= last_ts + dt.timedelta(days=1):
        train_start = cursor
        train_end = train_start + dt.timedelta(days=train_days)
        test_start = train_end
        test_end = test_start + dt.timedelta(days=test_days)
        splits.append(SplitWindow(
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
        ))
        cursor = cursor + dt.timedelta(days=step_days)
    return splits


# ---------------------------------------------------------------------------
# Metric aggregation
# ---------------------------------------------------------------------------


def _decimal_sqrt(x: Decimal, iterations: int = 25) -> Decimal:
    if x <= 0:
        return Decimal("0")
    guess = x / Decimal("2")
    for _ in range(iterations):
        if guess == 0:
            break
        guess = (guess + x / guess) / Decimal("2")
    return guess


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _sample_std(values: list[Decimal]) -> Decimal | None:
    n = len(values)
    if n < 2:
        return None
    mean = _mean(values) or Decimal("0")
    var = sum(((v - mean) ** 2 for v in values), Decimal("0")) / Decimal(n - 1)
    return _decimal_sqrt(var)


def aggregate_window(rows: Sequence[OutcomeRow]) -> WindowMetrics:
    """Compute per-window metrics safely. Returns all-None metrics when rows
    are empty or all-null (no division, no crash)."""
    labels = [r.barrier_label for r in rows if r.barrier_label is not None]
    wins = sum(1 for label in labels if label > 0)
    losses = sum(1 for label in labels if label < 0)
    breakeven = sum(1 for label in labels if label == 0)

    returns = [r.realized_return for r in rows if r.realized_return is not None]

    total_return = sum(returns, Decimal("0")) if returns else None
    expectancy = _mean(returns)

    gains = sum((r for r in returns if r > 0), Decimal("0"))
    losses_sum = sum((abs(r) for r in returns if r < 0), Decimal("0"))
    profit_factor: Decimal | None = None
    if losses_sum > 0:
        profit_factor = gains / losses_sum

    decisive = wins + losses
    hit_rate: Decimal | None
    if decisive > 0:
        hit_rate = Decimal(wins) / Decimal(decisive)
    else:
        hit_rate = None

    sharpe: Decimal | None = None
    if len(returns) >= MIN_SAMPLES_FOR_SHARPE:
        sd = _sample_std(returns)
        if sd is not None and sd > 0:
            sharpe = (expectancy or Decimal("0")) / sd

    return WindowMetrics(
        count=len(rows),
        wins=wins,
        losses=losses,
        breakeven=breakeven,
        total_return_proxy=total_return,
        hit_rate=hit_rate,
        expectancy=expectancy,
        profit_factor=profit_factor,
        sharpe=sharpe,
    )


# ---------------------------------------------------------------------------
# WFE + classification
# ---------------------------------------------------------------------------


def compute_wfe(is_expectancy: Decimal | None, oos_expectancy: Decimal | None) -> Decimal | None:
    """WFE = OOS expectancy / IS expectancy.

    Conventions (practical, avoids NaN noise):
    - IS is None or zero → None (undefined reference).
    - OOS is None → None.
    - IS positive and OOS negative → 0 (edge completely lost).
    - IS negative → None (negative baseline makes the ratio uninterpretable).
    """
    if is_expectancy is None or oos_expectancy is None:
        return None
    if is_expectancy <= 0:
        return None
    if oos_expectancy <= 0:
        return Decimal("0")
    return oos_expectancy / is_expectancy


def classify_stability(wfe: Decimal | None) -> Stability:
    if wfe is None:
        return "UNKNOWN"
    if wfe >= Decimal("0.70"):
        return "ROBUST"
    if wfe >= Decimal("0.50"):
        return "MODERATE"
    return "WEAK"


# ---------------------------------------------------------------------------
# Core harness
# ---------------------------------------------------------------------------


def _rows_in_window(
    rows: Iterable[OutcomeRow],
    start: dt.datetime,
    end: dt.datetime,
) -> list[OutcomeRow]:
    """Half-open [start, end)."""
    return [r for r in rows if start <= r.generated_at < end]


def run_walk_forward(
    rows: Sequence[OutcomeRow],
    train_days: int = DEFAULT_TRAIN_DAYS,
    test_days: int = DEFAULT_TEST_DAYS,
    step_days: int = DEFAULT_STEP_DAYS,
    signal_type: str | None = None,
) -> WalkForwardReport:
    """Run walk-forward over pre-loaded outcome rows.

    `signal_type` stratification: when provided, rows are filtered to that
    family before splitting. Empty filtered set → empty report (no splits).
    """
    filtered = [r for r in rows if signal_type is None or r.signal_type == signal_type]
    filtered = sorted(filtered, key=lambda r: r.generated_at)

    config = {
        "train_days": train_days,
        "test_days": test_days,
        "step_days": step_days,
    }

    if not filtered:
        return WalkForwardReport(
            splits=[],
            aggregate_wfe=None,
            aggregate_stability="UNKNOWN",
            config=config,
            stratified_by=signal_type,
        )

    first_ts = filtered[0].generated_at
    # Pad last_ts by one test window: when the latest labeled rec lands a few
    # days before the nominal test_end boundary, still emit the split. Rows
    # are aggregated on whatever actually falls inside the window.
    last_ts = filtered[-1].generated_at + dt.timedelta(days=test_days)
    windows = build_splits(first_ts, last_ts, train_days, test_days, step_days)

    split_results: list[SplitResult] = []
    for i, w in enumerate(windows):
        is_rows = _rows_in_window(filtered, w.train_start, w.train_end)
        oos_rows = _rows_in_window(filtered, w.test_start, w.test_end)
        notes: list[str] = []
        if not is_rows:
            notes.append("empty_IS")
        if not oos_rows:
            notes.append("empty_OOS")
        is_m = aggregate_window(is_rows)
        oos_m = aggregate_window(oos_rows)
        wfe = compute_wfe(is_m.expectancy, oos_m.expectancy)
        if wfe is None:
            if is_m.expectancy is None:
                notes.append("wfe_undefined_is_none")
            elif is_m.expectancy <= 0:
                notes.append("wfe_undefined_is_nonpositive")
            elif oos_m.expectancy is None:
                notes.append("wfe_undefined_oos_none")
        stability = classify_stability(wfe)
        split_results.append(SplitResult(
            index=i,
            window=w,
            is_metrics=is_m,
            oos_metrics=oos_m,
            wfe=wfe,
            stability=stability,
            notes=notes,
        ))

    # Aggregate WFE = mean of per-split WFE (only splits where wfe is not None).
    non_null = [s.wfe for s in split_results if s.wfe is not None]
    aggregate_wfe: Decimal | None = (
        sum(non_null, Decimal("0")) / Decimal(len(non_null)) if non_null else None
    )
    aggregate_stability = classify_stability(aggregate_wfe)

    return WalkForwardReport(
        splits=split_results,
        aggregate_wfe=aggregate_wfe,
        aggregate_stability=aggregate_stability,
        config=config,
        stratified_by=signal_type,
    )


# ---------------------------------------------------------------------------
# DB loader
# ---------------------------------------------------------------------------


def _coerce_decimal(v: object) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except Exception:  # noqa: BLE001
        return None


def load_outcome_rows(session: Session) -> list[OutcomeRow]:
    """Load labeled outcomes + signal_type in one pass.

    Signal_type is taken from the stored column when present; otherwise
    derived on-the-fly from evidence factor_keys (backwards compatible with
    rows scored before the column existed).
    """
    stmt = (
        select(
            Recommendation.id,
            Recommendation.asset_id,
            Recommendation.generated_at,
            RecommendationOutcome.barrier_label,
            RecommendationOutcome.realized_30d_return,
            RecommendationOutcome.signal_type,
        )
        .join(RecommendationOutcome, RecommendationOutcome.recommendation_id == Recommendation.id)
        .order_by(Recommendation.generated_at.asc())
    )
    rows = session.execute(stmt).all()

    # Bulk-load evidence only for recs that are missing signal_type.
    missing_ids = [r[0] for r in rows if r[5] is None]
    backfill_map: dict[str, str] = {}
    if missing_ids:
        ev_stmt = select(
            RecommendationEvidence.recommendation_id,
            RecommendationEvidence.evidence_type,
        ).where(RecommendationEvidence.recommendation_id.in_(missing_ids))
        per_rec: dict[str, list[str]] = {}
        for rec_id, ev_type in session.execute(ev_stmt).all():
            per_rec.setdefault(rec_id, []).append(ev_type)
        for rec_id, keys in per_rec.items():
            backfill_map[rec_id] = classify_signal_type(keys)

    out: list[OutcomeRow] = []
    for rec_id, asset_id, generated_at, label, ret_30d, sig_type in rows:
        if generated_at is None:
            continue
        st = sig_type or backfill_map.get(rec_id) or "default"
        out.append(OutcomeRow(
            recommendation_id=rec_id,
            asset_id=asset_id,
            generated_at=generated_at,
            barrier_label=int(label) if label is not None else None,
            realized_return=_coerce_decimal(ret_30d),
            signal_type=st,
        ))
    return out
