"""Paper-run audit writer.

Single INSERT per run. Called from scripts/run_paper_daily.py at end.
Human-readable summary sentence assembled here.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class PaperRunCounts:
    decisions_evaluated: int = 0
    trades_opened: int = 0
    trades_closed: int = 0
    trades_skipped: int = 0
    exploratory_trades: int = 0
    strict_trades: int = 0
    blocked_by_gates: int = 0
    blocked_by_anomaly: int = 0
    blocked_by_data_quality: int = 0


def build_run_summary(
    *,
    status: str,
    counts: PaperRunCounts,
    gates_passed: int | None = None,
    gates_total: int | None = None,
    gates_failed: list[str] | None = None,
    exploratory_mode: bool = False,
) -> str:
    if status == "failed":
        return "Paper run failed — check logs."
    if counts.trades_opened == 0 and counts.trades_closed == 0:
        why = ""
        if gates_passed is not None and gates_total is not None:
            missing = ", ".join(gates_failed or [])
            suffix = f" because {missing} gate(s) incomplete" if missing else ""
            why = (f" System evaluated {counts.decisions_evaluated} "
                    f"signal(s) but stayed flat "
                    f"({gates_passed}/{gates_total} gates)" + suffix + ".")
        return (
            f"Today's run completed. {counts.decisions_evaluated} "
            f"decision(s) evaluated, 0 trades opened, 0 trades closed."
            + why
        )
    parts: list[str] = [f"Today's run completed."]
    if counts.trades_opened:
        parts.append(
            f"{counts.trades_opened} paper trade(s) opened"
            + (f" ({counts.exploratory_trades} exploratory, "
               f"{counts.strict_trades} strict)"
               if counts.exploratory_trades or counts.strict_trades else "")
            + "."
        )
    if counts.trades_closed:
        parts.append(f"{counts.trades_closed} trade(s) closed.")
    if exploratory_mode and counts.exploratory_trades:
        parts.append(
            "Exploratory trades run at reduced size for learning only."
        )
    return " ".join(parts)


def write_paper_run_log(
    session: Session,
    *,
    run_date: dt.date,
    started_at: dt.datetime,
    status: str,
    counts: PaperRunCounts,
    net_pnl_today: float | None,
    nav_start: float | None,
    nav_end: float | None,
    summary: str,
    warnings: list[str] | None = None,
    details: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> str | None:
    if dry_run:
        logger.info("paper_run_log (dry): {}", summary)
        return None
    try:
        row = session.execute(text("""
            INSERT INTO paper_run_log
              (run_date, started_at, finished_at, status,
               decisions_evaluated, trades_opened, trades_closed,
               trades_skipped, exploratory_trades, strict_trades,
               blocked_by_gates, blocked_by_anomaly,
               blocked_by_data_quality,
               net_pnl_today, nav_start, nav_end,
               summary, warnings, details)
            VALUES
              (:rd, :sa, :fa, :st,
               :de, :to_, :tc,
               :ts, :et, :stk,
               :bg, :ba, :bdq,
               :npl, :nvs, :nve,
               :sum, CAST(:warn AS jsonb), CAST(:det AS jsonb))
            ON CONFLICT ON CONSTRAINT ux_paper_run_log_run_date
              DO UPDATE SET
                finished_at = EXCLUDED.finished_at,
                status      = EXCLUDED.status,
                decisions_evaluated = EXCLUDED.decisions_evaluated,
                trades_opened       = EXCLUDED.trades_opened,
                trades_closed       = EXCLUDED.trades_closed,
                trades_skipped      = EXCLUDED.trades_skipped,
                exploratory_trades  = EXCLUDED.exploratory_trades,
                strict_trades       = EXCLUDED.strict_trades,
                blocked_by_gates    = EXCLUDED.blocked_by_gates,
                blocked_by_anomaly  = EXCLUDED.blocked_by_anomaly,
                blocked_by_data_quality = EXCLUDED.blocked_by_data_quality,
                net_pnl_today = EXCLUDED.net_pnl_today,
                nav_end       = EXCLUDED.nav_end,
                summary       = EXCLUDED.summary,
                warnings      = EXCLUDED.warnings,
                details       = EXCLUDED.details
            RETURNING id
        """), {
            "rd":  run_date,
            "sa":  started_at,
            "fa":  dt.datetime.now(dt.timezone.utc),
            "st":  status,
            "de":  counts.decisions_evaluated,
            "to_": counts.trades_opened,
            "tc":  counts.trades_closed,
            "ts":  counts.trades_skipped,
            "et":  counts.exploratory_trades,
            "stk": counts.strict_trades,
            "bg":  counts.blocked_by_gates,
            "ba":  counts.blocked_by_anomaly,
            "bdq": counts.blocked_by_data_quality,
            "npl": net_pnl_today,
            "nvs": nav_start,
            "nve": nav_end,
            "sum": summary,
            "warn": json.dumps(warnings or []),
            "det":  json.dumps(details or {}, default=str),
        }).fetchone()
        session.commit()
        return str(row[0])
    except Exception as e:
        logger.warning("paper_run_log write failed: {}", e)
        return None
