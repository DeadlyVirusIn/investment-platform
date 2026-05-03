"""Phase 11Z — ML dataset rebuild from recovered execution data.

Produces a JSONL dataset of paper-trading rows joined with provenance,
context, and outcome metadata. SAFE BY DEFAULT:

  * Read-only. No writes to ANY table.
  * Tags every row with `source` from `replay_recovery_manifest`
    (defaults to 'live' when no manifest entry exists).
  * Marks open positions as `outcome_status='open_pending'` — never
    fabricates a label.
  * Refuses to enable ML execution: asserts settings.ML_CAN_AFFECT_TRADES
    is False before any output is written.
  * Train/eval separation is by date — caller picks the split with
    --train-end / --eval-start; rows must satisfy
    `train_end < eval_start` (no leakage).
  * Outcome columns (`return_*`, `outcome_class`) are pulled from
    `paper_observation_label` (forward-return labeller). Rows whose
    `entry_date >= as_of_today - holding_horizon` get
    `outcome_status='open_pending'` automatically.

Usage:
    python -m scripts.build_ml_dataset \\
        --start-date 2026-04-22 --end-date 2026-05-01 \\
        --train-end 2026-04-29 --eval-start 2026-04-30 \\
        --out artifacts/ml/dataset_2026-05-03.jsonl

    # Include replay rows (audit-only): pass --include-replay; default
    # excludes them so live ML never trains on synthetic recovery data.

Exit codes:
    0  ok
    2  bad args / leakage detected
    3  ML_CAN_AFFECT_TRADES is True (refuses to write)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from loguru import logger
from sqlalchemy import text

from apps.api.src.db import SessionLocal


HOLDING_HORIZON_DAYS = 20  # match paper_observation_label longest column


@dataclass
class BuildArgs:
    start_date: dt.date
    end_date: dt.date
    train_end: dt.date | None
    eval_start: dt.date | None
    out: Path
    include_replay: bool


def _parse(argv: Sequence[str] | None = None) -> BuildArgs:
    p = argparse.ArgumentParser(prog="build_ml_dataset")
    p.add_argument("--start-date", required=True,
                    type=lambda s: dt.date.fromisoformat(s))
    p.add_argument("--end-date", required=True,
                    type=lambda s: dt.date.fromisoformat(s))
    p.add_argument("--train-end",
                    type=lambda s: dt.date.fromisoformat(s))
    p.add_argument("--eval-start",
                    type=lambda s: dt.date.fromisoformat(s))
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--include-replay", action="store_true",
                    help="Audit mode. Default excludes replay rows.")
    ns = p.parse_args(argv)
    if ns.start_date > ns.end_date:
        p.error("--start-date must be <= --end-date")
    if (ns.train_end is None) != (ns.eval_start is None):
        p.error("--train-end and --eval-start must be set together")
    if ns.train_end and ns.eval_start and not (ns.train_end < ns.eval_start):
        p.error(
            f"leakage: --train-end ({ns.train_end}) must be < "
            f"--eval-start ({ns.eval_start})"
        )
    return BuildArgs(
        start_date=ns.start_date,
        end_date=ns.end_date,
        train_end=ns.train_end,
        eval_start=ns.eval_start,
        out=ns.out,
        include_replay=ns.include_replay,
    )


def _assert_ml_safe() -> None:
    """Refuse to run if ML_CAN_AFFECT_TRADES is True. This script
    never wires ML to execution, but the assertion is a tripwire so
    a bad env doesn't slip past."""
    from apps.api.src.config import settings
    if getattr(settings, "ML_CAN_AFFECT_TRADES", False):
        logger.error(
            "REFUSED: ML_CAN_AFFECT_TRADES=true. This script is "
            "advisory-only; refusing to produce dataset under an "
            "execution-affecting config."
        )
        raise SystemExit(3)


def _today() -> dt.date:
    return dt.datetime.utcnow().date()


SQL_PAPER_TRADE_DATASET = text("""
    SELECT
      pt.id                AS trade_id,
      pt.portfolio_id      AS portfolio_id,
      pt.recommendation_id AS recommendation_id,
      pp.name              AS portfolio_name,
      a.symbol             AS symbol,
      pt.side              AS side,
      pt.quantity          AS quantity,
      pt.fill_price        AS fill_price,
      pt.fill_ts           AS fill_ts,
      pt.submitted_at      AS submitted_at,
      pt.realized_pnl      AS realized_pnl,
      pt.slippage_bps      AS slippage_bps,
      pt.reason            AS reason,
      m.source             AS manifest_source,
      m.replay_run_id      AS replay_run_id,
      m.replay_generated_at AS replay_generated_at,
      pos.is_open          AS position_is_open,
      pos.opened_at        AS position_opened_at,
      pos.closed_at        AS position_closed_at,
      lbl.return_1d        AS return_1d,
      lbl.return_5d        AS return_5d,
      lbl.return_10d       AS return_10d,
      lbl.return_20d       AS return_20d,
      lbl.outcome_class    AS outcome_class
    FROM paper_trade pt
    JOIN paper_portfolio pp ON pp.id = pt.portfolio_id
    JOIN asset a            ON a.id = pt.asset_id
    LEFT JOIN replay_recovery_manifest m
      ON m.entity_type = 'paper_trade' AND m.entity_id = pt.id::text
    LEFT JOIN paper_position pos
      ON pos.portfolio_id = pt.portfolio_id
     AND pos.asset_id     = pt.asset_id
     AND pos.opened_at::date <= pt.fill_ts::date
    LEFT JOIN paper_observation_label lbl
      ON lbl.paper_trade_id::text = pt.id
    WHERE pt.fill_ts::date BETWEEN :start AND :end
    ORDER BY pt.fill_ts, pt.id
""")


def _row_to_record(row, *, today: dt.date) -> dict:
    fill_date = row.fill_ts.date() if row.fill_ts else None
    open_pending = (
        bool(row.position_is_open)
        or row.outcome_class is None
        or (
            fill_date is not None
            and (today - fill_date).days < HOLDING_HORIZON_DAYS
        )
    )
    if open_pending:
        outcome_status = "open_pending"
    elif row.outcome_class is not None:
        outcome_status = "labeled"
    else:
        outcome_status = "unlabeled_closed"

    source = row.manifest_source or "live"
    notional = (
        float(row.quantity) * float(row.fill_price)
        if row.quantity is not None and row.fill_price is not None
        else None
    )
    return {
        "trade_id": str(row.trade_id),
        "portfolio_id": row.portfolio_id,
        "portfolio_name": row.portfolio_name,
        "recommendation_id": row.recommendation_id,
        "symbol": row.symbol,
        "side": row.side,
        "quantity": float(row.quantity) if row.quantity is not None else None,
        "fill_price": (
            float(row.fill_price) if row.fill_price is not None else None
        ),
        "notional_usd": notional,
        "submitted_at": (
            row.submitted_at.isoformat() if row.submitted_at else None
        ),
        "fill_ts": row.fill_ts.isoformat() if row.fill_ts else None,
        "fill_date": fill_date.isoformat() if fill_date else None,
        "position_is_open": (
            bool(row.position_is_open)
            if row.position_is_open is not None else None
        ),
        "position_opened_at": (
            row.position_opened_at.isoformat()
            if row.position_opened_at else None
        ),
        "position_closed_at": (
            row.position_closed_at.isoformat()
            if row.position_closed_at else None
        ),
        "return_1d":  _f(row.return_1d),
        "return_5d":  _f(row.return_5d),
        "return_10d": _f(row.return_10d),
        "return_20d": _f(row.return_20d),
        "outcome_class": row.outcome_class,
        "outcome_status": outcome_status,
        "source": source,
        "replay_run_id": row.replay_run_id,
        "replay_generated_at": (
            row.replay_generated_at.isoformat()
            if row.replay_generated_at else None
        ),
    }


def _f(v) -> float | None:
    return float(v) if v is not None else None


def build_dataset(args: BuildArgs) -> dict:
    _assert_ml_safe()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    today = _today()

    train_count = 0
    eval_count = 0
    other_count = 0
    open_pending = 0
    labeled = 0
    excluded_replay = 0
    by_source: dict[str, int] = {}
    leakage_violations: list[str] = []

    with SessionLocal() as s, args.out.open("w", encoding="utf-8") as fh:
        rows = s.execute(SQL_PAPER_TRADE_DATASET, {
            "start": args.start_date, "end": args.end_date,
        }).all()
        for row in rows:
            rec = _row_to_record(row, today=today)
            src = rec["source"]
            if src == "replay" and not args.include_replay:
                excluded_replay += 1
                continue
            by_source[src] = by_source.get(src, 0) + 1

            # Leakage check: if a record's fill_date falls into eval
            # window but recommendation was generated AFTER eval_start,
            # that's leakage. Here we rely on fill_date as the time-
            # ordering anchor — train rows MUST have fill_date <= train_end,
            # eval rows fill_date >= eval_start.
            split = "other"
            fdate = (
                dt.date.fromisoformat(rec["fill_date"])
                if rec["fill_date"] else None
            )
            if fdate is not None and args.train_end and args.eval_start:
                if fdate <= args.train_end:
                    split = "train"
                elif fdate >= args.eval_start:
                    split = "eval"
                else:
                    # Falls into the gap — not used.
                    split = "gap"
            rec["split"] = split

            if rec["outcome_status"] == "open_pending":
                open_pending += 1
            elif rec["outcome_status"] == "labeled":
                labeled += 1

            if split == "train":
                train_count += 1
            elif split == "eval":
                eval_count += 1
            else:
                other_count += 1

            fh.write(json.dumps(rec, default=str) + "\n")

    if args.train_end and args.eval_start:
        # Sanity: every train row's fill_date <= train_end; every eval
        # row's fill_date >= eval_start. The split logic above
        # enforces this — re-read the file to verify.
        with args.out.open("r", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                fd = r.get("fill_date")
                if fd and r.get("split") == "train" and fd > args.train_end.isoformat():
                    leakage_violations.append(
                        f"train row {r['trade_id']} fill_date {fd} > train_end"
                    )
                if fd and r.get("split") == "eval" and fd < args.eval_start.isoformat():
                    leakage_violations.append(
                        f"eval row {r['trade_id']} fill_date {fd} < eval_start"
                    )

    return {
        "ok": not leakage_violations,
        "out": str(args.out),
        "rows_written": train_count + eval_count + other_count,
        "train_rows": train_count,
        "eval_rows": eval_count,
        "other_rows": other_count,
        "open_pending": open_pending,
        "labeled": labeled,
        "by_source": by_source,
        "excluded_replay": excluded_replay,
        "include_replay": args.include_replay,
        "leakage_violations": leakage_violations,
        "ml_can_affect_trades": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse(argv)
    summary = build_dataset(args)
    print("=" * 78)
    print(f"ML DATASET BUILD  [{'OK' if summary['ok'] else 'LEAKAGE'}]")
    print("=" * 78)
    print(f"  out:                 {summary['out']}")
    print(f"  rows_written:        {summary['rows_written']}")
    print(f"  train_rows:          {summary['train_rows']}")
    print(f"  eval_rows:           {summary['eval_rows']}")
    print(f"  other_rows:          {summary['other_rows']}")
    print(f"  open_pending:        {summary['open_pending']}")
    print(f"  labeled:             {summary['labeled']}")
    print(f"  by_source:           {summary['by_source']}")
    print(f"  excluded_replay:     {summary['excluded_replay']}")
    print(f"  include_replay:      {summary['include_replay']}")
    print(f"  ml_can_affect_trades:{summary['ml_can_affect_trades']}")
    if summary["leakage_violations"]:
        print("  LEAKAGE:")
        for v in summary["leakage_violations"]:
            print(f"    - {v}")
    print("=" * 78)
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
