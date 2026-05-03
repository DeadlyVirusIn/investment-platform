"""Daily live-forward orchestrator.

Stages (in order):
  1. verify data freshness
  2. generate candidates (live engine)
  3. run paper trading (consumes candidates)
  4. verify paper trading output + duplicate guard
  5. verify equity snapshot
  6. verify ML sizing log matches ENABLE_ML_SIZING state
  7. persist summary + dispatch alerts

Lock:
  A `daily_run_status` row per run_date. `status='running'` on start. Duplicate
  execution attempts with same date raise AlreadyRan unless force=True.

Market closed (weekend / detected):
  Insert row with status='skipped', stage_failed=None, emit INFO alert.

Dry run:
  Perform all read-only checks + skip write stages (generate/paper_trading).
  Does not write daily_run_status.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import asdict, dataclass, field

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.db.models import DailyRunStatus
from apps.api.src.domain.ops.alerting import (
    SEV_CRITICAL,
    SEV_INFO,
    SEV_WARNING,
    Alert,
    dispatch,
)
from apps.api.src.domain.ops.health_checks import (
    check_data_freshness,
    check_duplicate_execution,
    check_engine_output,
    check_equity_snapshot,
    check_ml_sizing_log,
    check_paper_trading,
    classify_buy_skips,
)


class AlreadyRan(RuntimeError):
    pass


@dataclass
class DailyRunResult:
    run_date: dt.date
    status: str                        # success | failed | skipped
    stage_failed: str | None = None
    alerts: list[Alert] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def _is_trading_day(d: dt.date) -> bool:
    # Weekday 0=Mon..6=Sun. No holiday calendar — acceptable simplification.
    return d.weekday() < 5


def _get_run(session: Session, run_date: dt.date) -> DailyRunStatus | None:
    return session.get(DailyRunStatus, run_date)


def _upsert_running(session: Session, run_date: dt.date, now: dt.datetime) -> None:
    stmt = pg_insert(DailyRunStatus).values(
        run_date=run_date, started_at=now, status="running",
    ).on_conflict_do_update(
        index_elements=["run_date"],
        set_={"started_at": now, "status": "running", "stage_failed": None},
    )
    session.execute(stmt)
    session.commit()


def _finalize(
    session: Session, run_date: dt.date, status: str,
    stage_failed: str | None, alerts: list[Alert], summary: dict,
) -> None:
    row = session.get(DailyRunStatus, run_date)
    if row is None:
        row = DailyRunStatus(
            run_date=run_date, started_at=dt.datetime.now(dt.timezone.utc),
            status=status,
        )
        session.add(row)
    row.status = status
    row.stage_failed = stage_failed
    row.alert_count = len(alerts)
    row.summary_json = summary
    row.finished_at = dt.datetime.now(dt.timezone.utc)
    session.commit()


# ---------------------------------------------------------------------------
# Stage runners
# ---------------------------------------------------------------------------


async def _stage_generate_candidates(as_of: dt.date) -> None:
    from apps.worker.src.jobs.generate_stock_candidates import (
        generate_stock_candidates,
    )
    await generate_stock_candidates(as_of)


async def _stage_run_paper_trading(as_of: dt.date) -> None:
    from apps.worker.src.jobs.run_paper_trading import run_paper_trading
    await run_paper_trading(as_of=as_of)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_daily_pipeline(
    as_of: dt.date | None = None,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> DailyRunResult:
    run_date = as_of or dt.date.today()
    now = dt.datetime.now(dt.timezone.utc)
    alerts: list[Alert] = []
    summary: dict = {"run_date": str(run_date), "dry_run": dry_run}

    logger.info(
        "[daily] start run_date={} dry_run={} force={}",
        run_date, dry_run, force,
    )

    # Market closed → skipped
    if not _is_trading_day(run_date):
        alerts.append(Alert(
            SEV_INFO, "market_closed",
            f"{run_date} is not a trading day — skipped.",
            {"weekday": run_date.strftime("%A")},
        ))
        summary["market_closed"] = True
        if not dry_run:
            with SessionLocal() as session:
                _finalize(session, run_date, "skipped", None, alerts, summary)
        dispatch(alerts)
        return DailyRunResult(run_date, "skipped", None, alerts, summary)

    # Lock check
    if not dry_run:
        with SessionLocal() as session:
            existing = _get_run(session, run_date)
            if existing is not None and existing.status in ("running", "success"):
                if not force:
                    alerts.append(Alert(
                        SEV_CRITICAL, "duplicate_run_attempt",
                        f"Daily run already exists for {run_date} "
                        f"(status={existing.status}). Pass --force to rerun.",
                        {"existing_status": existing.status,
                         "started_at": str(existing.started_at)},
                    ))
                    dispatch(alerts)
                    raise AlreadyRan(
                        f"daily run already {existing.status} for {run_date}"
                    )
            _upsert_running(session, run_date, now)

    stage_failed: str | None = None
    final_status = "success"

    try:
        # Stage 1 — data freshness
        with SessionLocal() as session:
            ok, detail = check_data_freshness(session, run_date)
            summary["data_freshness"] = detail
        if not ok:
            sev = SEV_CRITICAL if detail.get("price_lag_days", 999) > 5 else SEV_WARNING
            alerts.append(Alert(
                sev, "data_stale",
                "Data freshness check failed.",
                detail,
            ))
            if sev == SEV_CRITICAL:
                stage_failed = "data_freshness"
                final_status = "failed"
                raise RuntimeError("data freshness critical")

        # Stage 2 — generate candidates (write)
        if not dry_run:
            try:
                asyncio.run(_stage_generate_candidates(run_date))
            except Exception as exc:  # noqa: BLE001
                alerts.append(Alert(
                    SEV_CRITICAL, "generate_candidates_crash",
                    f"generate_stock_candidates failed: {exc}",
                    {"exception": str(exc)},
                ))
                stage_failed = "generate_candidates"
                final_status = "failed"
                raise

        # Stage 3 — run paper trading (write)
        if not dry_run:
            try:
                asyncio.run(_stage_run_paper_trading(run_date))
            except Exception as exc:  # noqa: BLE001
                alerts.append(Alert(
                    SEV_CRITICAL, "paper_trading_crash",
                    f"run_paper_trading failed: {exc}",
                    {"exception": str(exc)},
                ))
                stage_failed = "paper_trading"
                final_status = "failed"
                raise

        # Stage 4 — verify engine + paper trading output
        with SessionLocal() as session:
            eng_ok, eng_detail = check_engine_output(session, run_date)
            summary["engine_output"] = eng_detail
            if not eng_ok:
                alerts.append(Alert(
                    SEV_CRITICAL, "engine_no_output",
                    f"No candidate_idea rows for {run_date}.",
                    eng_detail,
                ))
                stage_failed = stage_failed or "engine_output"
                final_status = "failed"
            elif eng_detail["buys"] == 0:
                alerts.append(Alert(
                    SEV_INFO, "zero_buys",
                    f"Engine produced no accepted Buys for {run_date} "
                    f"(healthy; may be regime-off or fully rejected).",
                    eng_detail,
                ))

            pt_ok, pt_detail = check_paper_trading(session, run_date)
            summary["paper_trading"] = pt_detail
            if eng_detail.get("buys", 0) > 0 and pt_detail["trade_count"] == 0:
                all_safe, skip_detail = classify_buy_skips(run_date)
                summary["buy_skip_counts"] = skip_detail["counts"]
                summary["buy_skip_total"] = skip_detail["total"]
                summary["buy_skip_all_safe"] = skip_detail.get("all_safe", True)
                severity = SEV_INFO if all_safe else SEV_WARNING
                reason_label = (
                    "all skips in safe set (duplicate_holding / portfolio_full)"
                    if all_safe else
                    f"unsafe skip reasons present: {skip_detail.get('unsafe_reasons', [])}"
                )
                alerts.append(Alert(
                    severity, "buys_without_execution",
                    f"Engine produced {eng_detail['buys']} Buys, 0 executed — "
                    f"{reason_label}.",
                    {**eng_detail, **pt_detail, **skip_detail},
                ))

            # Always surface skip counts (even when some Buys executed)
            if "buy_skip_counts" not in summary:
                _, skip_summary = classify_buy_skips(run_date)
                summary["buy_skip_counts"] = skip_summary["counts"]
                summary["buy_skip_total"] = skip_summary["total"]

            dup_ok, dup_detail = check_duplicate_execution(session, run_date)
            summary["duplicate_check"] = dup_detail
            if not dup_ok:
                alerts.append(Alert(
                    SEV_CRITICAL, "duplicate_trades",
                    "Duplicate trades detected for same asset/side within run_date.",
                    dup_detail,
                ))
                stage_failed = stage_failed or "duplicate_guard"
                final_status = "failed"

        # Stage 5 — equity snapshot
        with SessionLocal() as session:
            eq_ok, eq_detail = check_equity_snapshot(session, run_date)
            summary["equity_snapshot"] = eq_detail
            if not eq_ok:
                alerts.append(Alert(
                    SEV_WARNING, "equity_snapshot_missing",
                    f"No paper_equity_snapshot row for {run_date}.",
                    eq_detail,
                ))

        # Stage 6 — ML sizing log consistency
        expected_mode = "ml_sized" if settings.ENABLE_ML_SIZING else "deterministic"
        ml_ok, ml_detail = check_ml_sizing_log(run_date, expected_mode)
        summary["ml_sizing"] = ml_detail
        if not ml_ok:
            if ml_detail.get("exists") is False:
                alerts.append(Alert(
                    SEV_WARNING, "ml_sizing_log_missing",
                    "ML sizing JSONL log not found for run_date.",
                    ml_detail,
                ))
            elif ml_detail.get("sizing_mode_actual") != expected_mode:
                alerts.append(Alert(
                    SEV_CRITICAL, "ml_sizing_mode_mismatch",
                    f"ENABLE_ML_SIZING={settings.ENABLE_ML_SIZING} but log reports "
                    f"{ml_detail.get('sizing_mode_actual')}. Deployment drift.",
                    ml_detail,
                ))
                stage_failed = stage_failed or "ml_sizing_mode"
                final_status = "failed"

    except Exception as exc:  # noqa: BLE001
        if final_status != "failed":
            final_status = "failed"
            stage_failed = stage_failed or "unknown"
        summary["exception"] = str(exc)
        logger.error("[daily] pipeline failed at {}: {}", stage_failed, exc)

    summary["alert_count"] = len(alerts)
    summary["status"] = final_status
    summary["stage_failed"] = stage_failed

    if not dry_run:
        with SessionLocal() as session:
            _finalize(session, run_date, final_status, stage_failed, alerts, summary)

    dispatch(alerts)
    logger.info(
        "[daily] end run_date={} status={} stage_failed={} alerts={}",
        run_date, final_status, stage_failed, len(alerts),
    )
    return DailyRunResult(run_date, final_status, stage_failed, alerts, summary)


def latest_run_status() -> dict | None:
    with SessionLocal() as session:
        row = session.execute(
            select(DailyRunStatus).order_by(DailyRunStatus.run_date.desc()).limit(1)
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "run_date": str(row.run_date),
            "status": row.status,
            "stage_failed": row.stage_failed,
            "started_at": str(row.started_at),
            "finished_at": str(row.finished_at) if row.finished_at else None,
            "alert_count": row.alert_count,
            "summary": row.summary_json,
        }
