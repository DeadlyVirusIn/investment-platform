"""Operator script — compute + upsert options strategy outcomes.

Pure read of `options_chain_snapshot`; writes only to
`options_strategy_outcome`. Idempotent — re-running with fresh
future snapshots updates pending rows in place via the natural-key
ON CONFLICT path.

Sources of strategy inputs:
  1. `/api/performance/options/strategy-suggestions` for the target
     date (mode='strict' for accepted strategies).
  2. `options_paper_trade` rows that are PROPOSED or OPEN (source
     ='paper_trade', mode='options_exploratory').

NEVER fabricates a quote. NEVER backfills with stock proxies. NEVER
uses same-bar fills (entry guard inside compute_strategy_outcomes
requires snapshot::date > submitted::date).

Usage:

  python -m scripts.compute_options_strategy_outcomes
  python -m scripts.compute_options_strategy_outcomes \\
      --as-of 2026-05-04 --horizons 1D,3D,5D,10D,20D
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Any

from loguru import logger
from sqlalchemy import text


def _argparse() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="compute_options_strategy_outcomes",
        description="Read-only outcome scoring for options strategies.",
    )
    p.add_argument(
        "--as-of", default=None,
        help="ISO date for suggestion source. Defaults to today UTC.",
    )
    p.add_argument(
        "--horizons", default="1D,3D,5D,10D,20D",
        help="Comma-separated horizons.",
    )
    return p


def _suggestions_for(date: dt.date) -> list[dict[str, Any]]:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app
    c = TestClient(app)
    r = c.get(
        f"/api/performance/options/strategy-suggestions"
        f"?as_of={date.isoformat()}&limit=200"
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"strategy-suggestions returned {r.status_code}: "
            f"{r.text[:200]}"
        )
    return r.json().get("items", [])


def _paper_trades_for(session, date: dt.date) -> list[dict[str, Any]]:
    rows = session.execute(text("""
        SELECT t.id, t.underlying, t.strategy_name, t.opened_at,
               t.created_at,
               jsonb_agg(
                 jsonb_build_object(
                   'option_symbol', l.option_symbol,
                   'action', lower(l.side),
                   'type', lower(l.option_type),
                   'strike', l.strike,
                   'expiry', l.expiry::text
                 ) ORDER BY l.leg_index
               ) AS legs
        FROM options_paper_trade t
        JOIN options_paper_trade_leg l ON l.trade_id = t.id
        WHERE coalesce(t.opened_at, t.created_at)::date = :d
        GROUP BY t.id
    """), {"d": date}).mappings().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        legs = r["legs"] or []
        out.append({
            "trade_id": r["id"],
            "underlying": r["underlying"],
            "strategy_name": r["strategy_name"],
            "submitted_at_utc": r["opened_at"] or r["created_at"],
            "legs": legs,
        })
    return out


def main(argv: list[str] | None = None) -> int:
    args = _argparse().parse_args(argv)
    if args.as_of:
        try:
            target = dt.date.fromisoformat(args.as_of)
        except ValueError:
            sys.stderr.write(
                f"REFUSED: --as-of must be ISO date, got {args.as_of!r}\n"
            )
            return 2
    else:
        target = dt.datetime.now(dt.timezone.utc).date()

    horizons = tuple(h.strip() for h in args.horizons.split(",") if h.strip())
    from apps.api.src.domain.options_quality.outcome import (
        HORIZONS, StrategyInput, compute_strategy_outcomes, upsert_outcomes,
    )
    for h in horizons:
        if h not in HORIZONS:
            sys.stderr.write(
                f"REFUSED: unknown horizon {h}; allowed: {HORIZONS}\n"
            )
            return 2

    from apps.api.src.db import SessionLocal
    inputs: list[StrategyInput] = []

    # 1. Suggestions for target date.
    try:
        sugs = _suggestions_for(target)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[opt-quality] suggestions endpoint failed: {}", exc,
        )
        sugs = []
    submitted_at = dt.datetime.combine(
        target, dt.time(21, 0), tzinfo=dt.timezone.utc,
    )
    for s in sugs:
        strategy_lc = s.get("strategy")
        if not strategy_lc:
            continue
        legs = s.get("legs") or []
        if not legs:
            continue
        inputs.append(StrategyInput(
            underlying=s["underlying"],
            strategy_name=strategy_lc.upper(),
            legs=[
                {
                    "option_symbol": l["option_symbol"],
                    "action": l["action"],
                    "type": l["type"], "strike": l["strike"],
                    "expiry": l["expiry"],
                }
                for l in legs
            ],
            as_of_date=target,
            submitted_at_utc=submitted_at,
            source="suggestion",
            mode="strict",
        ))

    # 2. Paper trades for target date.
    with SessionLocal() as session:
        trades = _paper_trades_for(session, target)
    for t in trades:
        inputs.append(StrategyInput(
            underlying=t["underlying"],
            strategy_name=t["strategy_name"],
            legs=t["legs"],
            as_of_date=target,
            submitted_at_utc=t["submitted_at_utc"],
            source="paper_trade",
            mode="options_exploratory",
        ))

    logger.info(
        "[opt-quality] inputs={} (sugs={} trades={}) horizons={} "
        "as_of={}",
        len(inputs), len(sugs), len(trades), horizons, target,
    )

    if not inputs:
        logger.warning("[opt-quality] no strategy inputs to score")
        return 0

    with SessionLocal() as session:
        outcomes = compute_strategy_outcomes(
            session, inputs, horizons=horizons,
        )
        # Distribution + summary log.
        labels: dict[str, int] = {}
        for o in outcomes:
            labels[o.outcome_label] = labels.get(o.outcome_label, 0) + 1
        logger.info(
            "[opt-quality] computed_outcomes={} labels={}",
            len(outcomes), labels,
        )
        result = upsert_outcomes(session, outcomes)
        logger.info("[opt-quality] upsert={}", result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
