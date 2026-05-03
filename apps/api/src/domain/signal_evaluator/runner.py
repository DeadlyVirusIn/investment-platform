"""Nightly evaluation runner — reads signal + price_bar, writes signal_outcome.

STRICT RULES:
  - Does NOT modify signal, candidate_idea, action_item, paper_trade, or any
    other table outside signal_outcome.
  - Never overwrites existing signal_outcome rows (unique index on signal_id).
  - Skips signals lacking sufficient forward price data; retries next run.
  - Emits structured per-run stats to the logger.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable

from loguru import logger
from sqlalchemy import and_, not_, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import PriceBar, Signal, SignalOutcome
from apps.api.src.domain.signal_evaluator.evaluator import (
    MAX_WAIT_MULTIPLIER,
    evaluate,
    is_timeout,
)


@dataclass
class EvalReport:
    signals_total: int = 0
    signals_evaluated: int = 0
    signals_skipped: int = 0
    signals_timeout: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pending_signals(session: Session, today: dt.date) -> list[Signal]:
    """Signals where as_of_date + holding_period_bars ≤ today AND no outcome yet.

    Using a LEFT-JOIN exclusion so we never re-evaluate existing rows.
    """
    existing_ids_stmt = select(SignalOutcome.signal_id)
    stmt = (
        select(Signal)
        .where(not_(Signal.signal_id.in_(existing_ids_stmt)))
        .order_by(Signal.as_of_date.asc(), Signal.signal_id.asc())
    )
    rows: list[Signal] = list(session.scalars(stmt))
    # Apply holding_period cutoff in Python — business-day math is fragile in SQL
    return [r for r in rows if r.as_of_date + dt.timedelta(days=r.holding_period_bars) <= today]


def _load_window(
    session: Session, asset_id: str,
    entry_date: dt.date, horizon_bars: int,
) -> list[PriceBar]:
    """Load daily bars from entry_date (inclusive) through entry + horizon_bars."""
    start = dt.datetime.combine(entry_date, dt.time.min, tzinfo=dt.timezone.utc)
    # Upper bound generously — horizon_bars in calendar days + weekend buffer
    end = start + dt.timedelta(days=horizon_bars + 10)
    stmt = (
        select(PriceBar)
        .where(
            PriceBar.asset_id == asset_id,
            PriceBar.timeframe == "1d",
            PriceBar.ts >= start,
            PriceBar.ts < end,
        )
        .order_by(PriceBar.ts.asc())
    )
    return list(session.scalars(stmt))


def _signal_age_days(signal_date: dt.date, today: dt.date) -> int:
    return max(0, (today - signal_date).days)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def evaluate_pending_signals(
    session: Session, *, today: dt.date | None = None,
) -> EvalReport:
    today = today or dt.date.today()
    now_utc = dt.datetime.now(dt.timezone.utc)
    report = EvalReport()

    def skip(reason: str) -> None:
        report.signals_skipped += 1
        report.skip_reasons[reason] = report.skip_reasons.get(reason, 0) + 1

    pending = _pending_signals(session, today)
    report.signals_total = len(pending)
    logger.info(
        "[signal_eval] run today={} pending={} (horizon-eligible, no existing outcome)",
        today, report.signals_total,
    )

    for sig in pending:
        age_days = _signal_age_days(sig.as_of_date, today)

        # Timeout takes priority — no price fetch needed if we're past MAX_WAIT
        if is_timeout(age_days, sig.holding_period_bars):
            # Still need an entry_price. Attempt to read one; if absent, skip.
            bars = _load_window(session, sig.asset_id, sig.as_of_date, sig.holding_period_bars)
            if not bars:
                skip("timeout_no_entry_price")
                logger.warning(
                    "[signal_eval] signal={} timeout but no price data — skip",
                    sig.signal_id,
                )
                continue
            entry = bars[0]
            if entry.close is None:
                skip("timeout_null_close")
                continue
            outcome = SignalOutcome(
                id=str(uuid.uuid4()),
                signal_id=sig.signal_id,
                signal_direction=sig.signal_direction,
                entry_price=Decimal(entry.close),
                realized_return=Decimal("0"),
                max_drawdown=None,
                outcome_label="timeout",
                evaluation_timestamp=now_utc,
            )
            session.add(outcome)
            report.signals_timeout += 1
            report.signals_evaluated += 1
            logger.info("[signal_eval] signal={} TIMEOUT age={}d", sig.signal_id, age_days)
            continue

        bars = _load_window(
            session, sig.asset_id, sig.as_of_date, sig.holding_period_bars,
        )
        # Minimum: 1 entry bar + holding_period_bars forward bars required
        if len(bars) < sig.holding_period_bars + 1:
            skip("insufficient_forward_bars")
            logger.warning(
                "[signal_eval] signal={} insufficient bars ({} < {}) — retry next run",
                sig.signal_id, len(bars), sig.holding_period_bars + 1,
            )
            continue

        entry_bar = bars[0]
        exit_bar = bars[sig.holding_period_bars]   # Nth bar after entry
        if entry_bar.close is None or exit_bar.close is None:
            skip("null_price")
            logger.warning(
                "[signal_eval] signal={} null close entry={} exit={} — skip",
                sig.signal_id, entry_bar.close, exit_bar.close,
            )
            continue

        entry_price = Decimal(entry_bar.close)
        exit_price = Decimal(exit_bar.close)

        # Window closes for drawdown (excluding entry to avoid zero-DD trivially)
        window_closes: list[Decimal] = []
        for b in bars[1 : sig.holding_period_bars + 1]:
            if b.close is None:
                continue
            try:
                window_closes.append(Decimal(b.close))
            except Exception:   # noqa: BLE001
                continue

        if entry_price <= 0:
            skip("bad_entry_price")
            continue

        try:
            result = evaluate(
                entry_price=entry_price,
                exit_price=exit_price,
                closes_over_window=window_closes,
                signal_direction=sig.signal_direction,
                signal_age_bars=age_days,
                holding_period_bars=sig.holding_period_bars,
            )
        except Exception as exc:   # noqa: BLE001 — never let one bad signal kill the job
            skip("evaluator_exception")
            logger.error(
                "[signal_eval] signal={} evaluator crashed: {}", sig.signal_id, exc,
            )
            continue

        if not result.realized_return.is_finite():
            skip("nan_or_inf_return")
            logger.warning("[signal_eval] signal={} non-finite return — skip", sig.signal_id)
            continue

        outcome = SignalOutcome(
            id=str(uuid.uuid4()),
            signal_id=sig.signal_id,
            signal_direction=sig.signal_direction,
            entry_price=result.entry_price,
            realized_return=result.realized_return,
            max_drawdown=result.max_drawdown,
            outcome_label=result.outcome_label,
            evaluation_timestamp=now_utc,
        )
        session.add(outcome)
        report.signals_evaluated += 1
        if result.outcome_label == "timeout":
            report.signals_timeout += 1
        logger.info(
            "[signal_eval] signal={} label={} realized={:.4f} dd={}",
            sig.signal_id, result.outcome_label, float(result.realized_return),
            float(result.max_drawdown) if result.max_drawdown is not None else "—",
        )

    session.commit()
    logger.info(
        "[signal_eval] done total={} evaluated={} skipped={} timeouts={} reasons={}",
        report.signals_total, report.signals_evaluated,
        report.signals_skipped, report.signals_timeout,
        report.skip_reasons,
    )
    return report
