"""Phase 1.5 daily signals shadow pipeline.

Flow (5 steps):
  1. Adapter → list[Signal]
  2. Ranker → list[RankedSignal]
  3. Persist to `signal` table (upsert)
  4. Persist to `ranked_signal` table (idempotent per (as_of, strategy))
  5. Optional: diff vs scheduler → write `shadow_run_log` row

SHADOW MODE ONLY:
  - Does NOT touch action_item, paper_trade, paper_position.
  - Safe re-run. Unique indices enforce dedup.

# --------------------------------------------------------------------------
# PREFECT READINESS MARKER
# --------------------------------------------------------------------------
# When Prefect lands, wrap:
#   @flow(name="daily_signals",
#         retries=2, retry_delay_seconds=60,
#         log_prints=True)
#   def run_daily_signals(as_of: date | None = None) -> FlowResult: ...
# Mark these as @task:
#   _persist_signals, _persist_ranked_signals, _run_diff, _write_run_log
# Retry policy placeholder: 2 retries × 60s delay on transient DB errors.
# Expected parameters (flow): as_of (date | None, default today UTC).
# --------------------------------------------------------------------------

Usage::

    python -m pipelines.daily_signals                          # today UTC
    python -m pipelines.daily_signals --as-of 2026-04-17
    python -m pipelines.daily_signals --as-of 2026-04-17 --no-diff
"""

from __future__ import annotations

import argparse
import datetime as dt
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from loguru import logger
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import (
    RankedSignalRow,
    ShadowRunLog,
    Signal as SignalOrm,
)
from packages.ensemble_ranker.scorer import rank
from packages.signal_schema.ranked_signal import RankedSignal
from packages.signal_schema.signal import Signal
from services.adapter_deterministic.run import DeterministicAdapter

RANKED_TOP_N = 50


# ---------------------------------------------------------------------------
# Persistence (@task candidates)
# ---------------------------------------------------------------------------


def _persist_signals(session, signals: list[Signal]) -> int:
    """Upsert signals on (as_of_date, asset_id, strategy_id) dedup key."""
    written = 0
    for s in signals:
        row = {
            "signal_id": s.signal_id,
            "as_of_date": s.as_of_date,
            "asset_id": s.asset_id,
            "symbol": s.symbol,
            "timeframe": s.timeframe,
            "strategy_id": s.strategy_id,
            "model_family": s.model_family,
            "model_version": s.model_version,
            "features_version": s.features_version,
            "signal_direction": s.signal_direction,
            "signal_strength": s.signal_strength,
            "confidence": s.confidence,
            "expected_return": s.expected_return,
            "expected_drawdown": s.expected_drawdown,
            "holding_period_bars": s.holding_period_bars,
            "risk_score": s.risk_score,
            "regime_tag": s.regime_tag,
            "raw_payload_ref": s.raw_payload_ref,
            "generated_at": s.timestamp,
        }
        stmt = pg_insert(SignalOrm.__table__).values(**row)
        stmt = stmt.on_conflict_do_update(
            index_elements=["as_of_date", "asset_id", "strategy_id"],
            set_={
                k: v for k, v in row.items()
                if k not in ("signal_id", "as_of_date", "asset_id", "strategy_id")
            },
        )
        session.execute(stmt)
        written += 1
    session.commit()
    return written


def _persist_ranked_signals(
    session, as_of: dt.date, ranked: list[RankedSignal],
    strategy_id: str, top_n: int = RANKED_TOP_N,
) -> int:
    """Overwrite (as_of, strategy_id) tuple for idempotency."""
    session.execute(
        delete(RankedSignalRow).where(
            RankedSignalRow.as_of_date == as_of,
            RankedSignalRow.strategy_id == strategy_id,
        )
    )
    written = 0
    for pos, r in enumerate(ranked[:top_n], start=1):
        session.add(RankedSignalRow(
            id=str(uuid.uuid4()),
            as_of_date=as_of,
            asset_id=r.asset_id,
            symbol=r.symbol,
            score=Decimal(str(round(r.score, 6))),
            rank_position=pos,
            strategy_id=strategy_id,
            contributing_count=len(r.contributing),
            payload={
                "contributing_signal_ids": [s.signal_id for s in r.contributing],
                "direction": r.contributing[0].signal_direction if r.contributing else None,
                "confidence": str(r.contributing[0].confidence) if r.contributing else None,
            },
        ))
        written += 1
    session.commit()
    return written


def _write_run_log(
    session, *, as_of: dt.date, signals_count: int, ranked_count: int,
    runtime_ms: int, diff_payload: dict | None,
) -> None:
    """Upsert one row per day (unique on as_of_date)."""
    row = {
        "id": str(uuid.uuid4()),
        "as_of_date": as_of,
        "signals_count": signals_count,
        "ranked_count": ranked_count,
        "runtime_ms": runtime_ms,
    }
    if diff_payload is not None:
        row.update({
            "diff_status": "ok" if diff_payload.get("ok") else "fail",
            "diff_reason": diff_payload.get("reason"),
            "reorder_count": diff_payload.get("reorder_count"),
            "asset_set_match": diff_payload.get("asset_set_match"),
            "topn_match": diff_payload.get("topn_match"),
            "max_score_delta": (
                Decimal(str(diff_payload.get("max_score_delta")))
                if diff_payload.get("max_score_delta") is not None else None
            ),
            "failing_symbols": diff_payload.get("failing_symbols") or [],
        })
    else:
        row["diff_status"] = "not_run"

    stmt = pg_insert(ShadowRunLog.__table__).values(**row)
    stmt = stmt.on_conflict_do_update(
        index_elements=["as_of_date"],
        set_={k: v for k, v in row.items() if k not in ("id",)},
    )
    session.execute(stmt)
    session.commit()


# ---------------------------------------------------------------------------
# Flow orchestrator
# ---------------------------------------------------------------------------


@dataclass
class FlowResult:
    as_of: dt.date
    signals_generated: int = 0
    ranked_generated: int = 0
    top_symbols: list[str] = field(default_factory=list)
    runtime_ms: int = 0
    diff_ok: bool | None = None
    diff_reason: str | None = None


def run_daily_signals(
    as_of: dt.date | None = None,
    *,
    run_diff: bool = True,
) -> FlowResult:
    as_of = as_of or dt.date.today()
    t0 = time.perf_counter()
    logger.info("[daily_signals] start as_of={} run_diff={}", as_of, run_diff)

    with SessionLocal() as session:
        adapter = DeterministicAdapter()
        signals = adapter.generate_signals(session, as_of)
        ranked = rank(signals)
        sw = _persist_signals(session, signals)
        rw = _persist_ranked_signals(session, as_of, ranked, adapter.strategy_id)

    top_syms = [r.symbol for r in ranked[:10]]
    runtime_ms = int((time.perf_counter() - t0) * 1000)

    # Diff + log (optional)
    diff_payload: dict | None = None
    diff_ok: bool | None = None
    diff_reason: str | None = None
    if run_diff:
        try:
            from scripts.diff_shadow_vs_scheduler import diff_day
            dr = diff_day(as_of)
            diff_payload = dr.to_json()
            diff_ok = dr.ok
            diff_reason = dr.reason
        except Exception as exc:       # noqa: BLE001
            logger.warning("[daily_signals] diff skipped: {}", exc)

    with SessionLocal() as session:
        _write_run_log(
            session, as_of=as_of,
            signals_count=sw, ranked_count=rw,
            runtime_ms=runtime_ms,
            diff_payload=diff_payload,
        )

    logger.info(
        "[daily_signals] done as_of={} signals_generated={} ranked_generated={} "
        "top_symbols={} runtime_ms={} diff_ok={}",
        as_of, sw, rw, top_syms, runtime_ms, diff_ok,
    )
    return FlowResult(
        as_of=as_of,
        signals_generated=sw,
        ranked_generated=rw,
        top_symbols=top_syms,
        runtime_ms=runtime_ms,
        diff_ok=diff_ok,
        diff_reason=diff_reason,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", type=lambda s: dt.date.fromisoformat(s), default=None)
    parser.add_argument("--no-diff", action="store_true",
                        help="Skip diff vs scheduler (useful in tests).")
    args = parser.parse_args()
    run_daily_signals(args.as_of, run_diff=not args.no_diff)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
