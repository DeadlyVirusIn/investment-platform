"""Phase 11X.2 — controlled paper-only pilot runner.

Standalone CLI that evaluates the safe-gate-evolution pilot for one
or more dates and (when the env flag is on) opens at most one
0.25× paper trade per day. Read-only by default —
SAFE_GATE_EVOLUTION_PILOT_EXECUTION must be true for any write.

Default dry-run: prints eligibility per date without invoking
`evaluate_and_execute_pilot`. Pass --execute to actually evaluate
+ execute (still gated by the env flag).

Exit codes:
  0   evaluation completed successfully (no trade required)
  10  evaluation completed, at least 1 pilot trade opened
  2   precondition failure (config / DB / arg parse)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from typing import Sequence

from loguru import logger

from apps.api.src.config import settings
from apps.api.src.data.strategy.safe_gate_evolution_pilot import (
    evaluate_and_execute_pilot, evaluate_eligibility,
)
from apps.api.src.db import SessionLocal


def _parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_safe_gate_evolution_pilot",
        description=(
            "Controlled paper-only pilot path gated by "
            "safe_gate_evolution_shadow + macro context. Default "
            "dry-run; execution requires --execute AND env flag "
            "SAFE_GATE_EVOLUTION_PILOT_EXECUTION=true."
        ),
    )
    p.add_argument(
        "--start", type=lambda s: dt.date.fromisoformat(s), required=True,
    )
    p.add_argument(
        "--end", type=lambda s: dt.date.fromisoformat(s), required=True,
    )
    p.add_argument(
        "--execute", action="store_true",
        help="If set, will call evaluate_and_execute_pilot. Without "
             "this flag, only dry-run eligibility is printed.",
    )
    p.add_argument(
        "--flag-override", choices=("on", "off"), default=None,
        help="Test/dev only — override env flag for this invocation.",
    )
    return p.parse_args(argv)


def _business_days(start: dt.date, end: dt.date) -> list[dt.date]:
    out: list[dt.date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse(argv)
    if args.start > args.end:
        sys.stderr.write("--start must be <= --end\n")
        return 2

    flag_override: bool | None = None
    if args.flag_override == "on":
        flag_override = True
    elif args.flag_override == "off":
        flag_override = False

    days = _business_days(args.start, args.end)
    n_opened = 0
    n_evaluated = 0

    with SessionLocal() as session:
        for d in days:
            n_evaluated += 1
            if args.execute:
                res = evaluate_and_execute_pilot(
                    session, d, flag_override=flag_override,
                )
                summary = {
                    "run_date": d.isoformat(),
                    "flag_enabled": res.flag_enabled,
                    "opened": res.opened,
                    "symbol": res.symbol,
                    "qty": str(res.quantity) if res.quantity else None,
                    "fill_price": (
                        str(res.fill_price) if res.fill_price else None
                    ),
                    "notional_usd": (
                        str(res.notional_usd) if res.notional_usd else None
                    ),
                    "reason": res.reason,
                    "eligibility": {
                        "eligible": res.eligibility.eligible,
                        "reason": res.eligibility.reason,
                        "macro_favorable": res.eligibility.macro_favorable,
                        "unknown_count": res.eligibility.unknown_count,
                        "shadow_would_trade": (
                            res.eligibility.shadow_would_trade
                        ),
                        "shadow_symbol": res.eligibility.shadow_symbol,
                    },
                }
                if res.opened:
                    n_opened += 1
                logger.info("[pilot] {}", json.dumps(summary, default=str))
            else:
                # Dry-run path — pure read-only.
                elig = evaluate_eligibility(session, d)
                logger.info(
                    "[pilot:dry] {} eligible={} reason={} fav={} unknown={} "
                    "shadow_would_trade={} shadow_symbol={}",
                    d, elig.eligible, elig.reason,
                    elig.macro_favorable, elig.unknown_count,
                    elig.shadow_would_trade, elig.shadow_symbol,
                )

    logger.info(
        "[pilot] dates_evaluated={} pilot_trades_opened={} "
        "flag_env={} flag_effective={}",
        n_evaluated, n_opened,
        bool(settings.SAFE_GATE_EVOLUTION_PILOT_EXECUTION),
        (
            flag_override
            if flag_override is not None
            else bool(settings.SAFE_GATE_EVOLUTION_PILOT_EXECUTION)
        ),
    )
    return 10 if n_opened > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
