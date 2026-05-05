"""Operator script — cross-signal stock vs options auto-router.

Default --dry-run. Writes a versioned artifact under
artifacts/cross_signal_routing/. Default behavior is byte-identical
to NOT running this script — no DB writes, no execution dispatch.

Phase 4 dispatch path (writes nothing here either):
  Both AUTO_ROUTE_STOCK_OPTIONS_ENABLED=true AND
  AUTO_ROUTE_EXECUTION_ENABLED=true must be set, AND --apply must
  be passed. Even then this v1 release marks routes
  `execution_allowed=True` in the artifact but does NOT subprocess
  the runners — operator dispatches them separately, which forces
  each runner's own confirmation env (EXPLORATORY_PAPER_CONFIRM /
  OPTIONS_PAPER_EXEC_CONFIRM) to be set explicitly. This keeps
  every existing safety gate in the path.

  Result: actual_executed is always 0 in this script.

Usage:
  python -m scripts.run_cross_signal_router --dry-run
  AUTO_ROUTE_STOCK_OPTIONS_ENABLED=true \\
  AUTO_ROUTE_EXECUTION_ENABLED=true \\
    python -m scripts.run_cross_signal_router --apply
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

from loguru import logger


AUTO_ROUTE_ENABLED = "AUTO_ROUTE_STOCK_OPTIONS_ENABLED"
AUTO_ROUTE_EXEC_ENABLED = "AUTO_ROUTE_EXECUTION_ENABLED"
ARTIFACT_DIR = Path("artifacts/cross_signal_routing")
ARTIFACT_NAME_TEMPLATE = "route_eval_{date}.json"


def _argparse() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_cross_signal_router",
        description=(
            "Cross-signal auto-router. Default dry-run; "
            "execution gate opens only with both env flags."
        ),
    )
    p.add_argument(
        "--dry-run", action="store_true", default=True,
        help="No execution dispatch. Default.",
    )
    p.add_argument(
        "--apply", action="store_true",
        help=f"Open execution gate. Requires {AUTO_ROUTE_ENABLED}"
             f"=true and {AUTO_ROUTE_EXEC_ENABLED}=true.",
    )
    p.add_argument("--as-of", default=None,
                   help="ISO date. Defaults to today UTC.")
    p.add_argument("--lookback-days", type=int, default=90)
    p.add_argument("--limit", type=int, default=25)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _argparse().parse_args(argv)
    auto_route_on = (
        os.environ.get(AUTO_ROUTE_ENABLED, "").strip().lower() == "true"
    )
    auto_route_exec_on = (
        os.environ.get(AUTO_ROUTE_EXEC_ENABLED, "").strip().lower()
        == "true"
    )
    gate_open = bool(args.apply and auto_route_on and auto_route_exec_on)

    if args.apply and not (auto_route_on and auto_route_exec_on):
        sys.stderr.write(
            f"REFUSED: --apply requires {AUTO_ROUTE_ENABLED}=true "
            f"AND {AUTO_ROUTE_EXEC_ENABLED}=true.\n"
        )
        return 2

    if args.as_of:
        try:
            target = dt.date.fromisoformat(args.as_of)
        except ValueError:
            sys.stderr.write(
                f"REFUSED: --as-of must be ISO date, got "
                f"{args.as_of!r}\n",
            )
            return 2
    else:
        target = dt.datetime.now(dt.timezone.utc).date()

    from apps.api.src.db import SessionLocal
    from apps.api.src.domain.cross_signal import (
        build_today_assistant, build_route_candidates,
        candidate_to_dict, RoutingThresholds, RoutingCaps,
    )
    from sqlalchemy import text

    logger.info(
        "[router] as_of={} lookback={} limit={} mode={} "
        "{}={} {}={}",
        target, args.lookback_days, args.limit,
        "apply" if args.apply else "dry-run",
        AUTO_ROUTE_ENABLED, auto_route_on,
        AUTO_ROUTE_EXEC_ENABLED, auto_route_exec_on,
    )

    with SessionLocal() as session:
        items = build_today_assistant(
            session, as_of=target,
            lookback_days=args.lookback_days, limit=args.limit,
        )

        def _chain_ok(u: str) -> bool:
            row = session.execute(text("""
                SELECT 1 FROM options_chain_snapshot
                WHERE underlying = :u
                  AND snapshot_at_utc::date > :d
                LIMIT 1
            """), {"u": u, "d": target}).first()
            return row is not None

        cands = build_route_candidates(
            items,
            options_chain_available_for=_chain_ok,
            thresholds=RoutingThresholds(),
            caps=RoutingCaps(),
            gate_open=gate_open,
        )

    items_out = [candidate_to_dict(c) for c in cands]
    counts = {
        "prefer_stock": 0, "prefer_options": 0,
        "watchlist_only": 0, "insufficient_data": 0,
    }
    for c in items_out:
        counts[c["route_hint"]] = counts.get(c["route_hint"], 0) + 1
    would_execute = sum(
        1 for c in items_out
        if c["execution_allowed"] and c["blocked_reason"] is None
    )
    actual_executed = 0  # v1 — operator dispatches runners themselves

    logger.info(
        "[router] candidates={} prefer_stock={} prefer_options={} "
        "watchlist_only={} insufficient_data={} "
        "would_execute={} actual_executed={}",
        len(items_out), counts["prefer_stock"], counts["prefer_options"],
        counts["watchlist_only"], counts["insufficient_data"],
        would_execute, actual_executed,
    )
    for c in items_out[:25]:
        logger.info(
            "[router.item] {} hint={} conf={} edge={} "
            "exec_allowed={} blocked={}",
            c["underlying"], c["route_hint"],
            c["cross_signal_confidence"],
            c["relative_edge_pct"],
            c["execution_allowed"], c["blocked_reason"],
        )

    artifact = {
        "schema_version": 1,
        "as_of_date": target.isoformat(),
        "lookback_days": args.lookback_days,
        "limit": args.limit,
        "auto_route_enabled": auto_route_on,
        "auto_route_exec_enabled": auto_route_exec_on,
        "execution_gate_open": gate_open,
        "would_execute": would_execute,
        "actual_executed": actual_executed,
        "counts_by_hint": counts,
        "items": items_out,
        "caps": {
            "max_routed_per_day": 5, "max_options_per_day": 2,
            "max_stock_per_day": 3, "max_per_underlying": 1,
            "max_total_options_exposure_pct": 0.05,
            "max_per_underlying_exposure_pct": 0.02,
        },
        "notice": (
            "Routing decisions only. v1 never subprocess-dispatches "
            "the stock/options runners — operator runs those "
            "explicitly so each runner's own confirmation env is "
            "always required. Liquidity, next-bar, paper-only, "
            "duplicate-position, and exposure caps remain enforced "
            "by the runners."
        ),
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACT_DIR / ARTIFACT_NAME_TEMPLATE.format(
        date=target.isoformat(),
    )
    out_path.write_text(json.dumps(artifact, indent=2, default=str))
    logger.info("[router] wrote artifact: {}", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
