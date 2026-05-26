"""Pending next-bar replay — fill yesterday's stuck buy decisions.

Problem this solves:
  `run_paper_trading(as_of=D)` regenerates decisions from
  `candidate_idea` rows for D and submits them with
  `submitted_at = combine(D, 15:00 UTC)`. When D's price_bar exists
  but D+1's does NOT yet (intraday run on day D, or markets closed),
  the next-bar fill rule (`bar.ts > submitted_at`) cannot match a
  future bar, so each decision is rejected and logged to a per-day
  skip JSONL with `reason='execution_failure'` and an exec_reason
  containing 'no price bar available after submitted_at'.

  Until now, those rejections were terminal — the next day's run
  generated a NEW set of decisions for day D+1 and never retried D's.
  Pending fills were lost.

This module replays pending fills WITHOUT relaxing the next-bar
guard: it re-invokes `auto_trade_portfolio` for the original date D
with the original `submitted_at = combine(D, 15:00 UTC)`. Today's
price_bar (D+1 or later) is strictly after that timestamp, so
`find_next_open` matches and fills land normally. Already-filled
positions are deduplicated by `auto_trader`'s `held_asset_ids`
check, so reruns are idempotent.

Same-bar fills remain forbidden — `find_next_open` still requires
`bar.ts > submitted_at`. We only ever advance the *availability* of
a future bar; the guard itself is unchanged.

Persistence:
  After a date D is replayed, a sibling marker
  `artifacts/paper_trading_skips/<D>.replayed.jsonl` is written with
  a single summary line. Subsequent runs skip dates whose marker
  exists. The skip JSONL itself is left untouched.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import PaperPortfolio
from apps.api.src.domain.paper_trading.auto_trader import (
    AutoTradeConfig, auto_trade_portfolio,
)
from apps.api.src.domain.paper_trading.paper_service import (
    snapshot_equity_now,
)


SKIPS_DIR = Path("artifacts/paper_trading_skips")
REPLAYED_SUFFIX = ".replayed.jsonl"

PENDING_REASON = "execution_failure"
PENDING_MARKER = "no price bar available after submitted_at"


def _is_pending_row(row: dict[str, Any]) -> bool:
    if row.get("reason") != PENDING_REASON:
        return False
    detail = row.get("detail") or {}
    return PENDING_MARKER.lower() in (
        (detail.get("exec_reason") or "").lower()
    )


def collect_pending_dates(
    *, before: dt.date,
    skips_dir: Path = SKIPS_DIR,
    from_date: dt.date | None = None,
    force: bool = False,
) -> list[dt.date]:
    """Return sorted dates D with >=1 pending_next_bar skip entry,
    where (from_date <= D < before) AND (force OR no `.replayed`
    marker present). `from_date=None` defaults to no lower bound."""
    if not skips_dir.exists():
        return []
    out: list[dt.date] = []
    for p in skips_dir.iterdir():
        if p.suffix != ".jsonl":
            continue
        # Skip our own marker files.
        if p.name.endswith(REPLAYED_SUFFIX):
            continue
        try:
            d = dt.date.fromisoformat(p.stem)
        except ValueError:
            continue
        if d >= before:
            continue
        if from_date is not None and d < from_date:
            continue
        if not force:
            marker = skips_dir / f"{d.isoformat()}{REPLAYED_SUFFIX}"
            if marker.exists():
                continue
        # Cheap content scan — first matching row is enough.
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if _is_pending_row(row):
                    out.append(d)
                    break
        except OSError:
            continue
    return sorted(out)


def _write_marker(
    skips_dir: Path, original_date: dt.date,
    summary: dict[str, Any],
) -> None:
    skips_dir.mkdir(parents=True, exist_ok=True)
    path = skips_dir / f"{original_date.isoformat()}{REPLAYED_SUFFIX}"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "replayed_at_utc": dt.datetime.now(
                dt.timezone.utc
            ).isoformat(),
            "original_date": original_date.isoformat(),
            **summary,
        }) + "\n")


def replay_pending_for_date(
    *, original_date: dt.date,
    SessionFactory,  # callable returning a new SessionLocal()
    skips_dir: Path = SKIPS_DIR,
) -> dict[str, Any]:
    """Re-invoke `auto_trade_portfolio(as_of=original_date)` for every
    active paper portfolio. Returns aggregate counts."""
    # Anchor exactly the same submitted_at the original run used.
    submitted_at = dt.datetime.combine(
        original_date, dt.time(15, 0), tzinfo=dt.timezone.utc,
    )
    decisions_total = 0
    executed_total = 0
    rejected_total = 0
    per_portfolio: list[dict[str, Any]] = []
    new_pending_count = 0

    with SessionFactory() as session:
        portfolio_ids = [
            p.id for p in session.scalars(
                select(PaperPortfolio)
                .where(PaperPortfolio.is_active.is_(True))
            )
        ]

    for pid in portfolio_ids:
        try:
            with SessionFactory() as session:
                portfolio = session.get(PaperPortfolio, pid)
                if portfolio is None:
                    continue
                result = auto_trade_portfolio(
                    session, portfolio, AutoTradeConfig(),
                    now=submitted_at, as_of=original_date,
                )
                snap_at = dt.datetime.combine(
                    original_date, dt.time(22, 0),
                    tzinfo=dt.timezone.utc,
                )
                # Phase L M079: pending-replay is by definition replay; tag accordingly.
                snapshot_equity_now(session, portfolio, as_of=snap_at, source="replay")
                session.commit()

                p_decisions = len(result.decisions)
                p_executed = len(result.executed)
                p_rejected = len(result.rejected)
                p_new_pending = sum(
                    1 for s in result.buy_skips
                    if s.get("reason") == "execution_failure"
                )
                decisions_total += p_decisions
                executed_total += p_executed
                rejected_total += p_rejected
                new_pending_count += p_new_pending
                per_portfolio.append({
                    "portfolio_id": pid,
                    "decisions": p_decisions,
                    "executed": p_executed,
                    "rejected": p_rejected,
                    "new_pending": p_new_pending,
                })
                logger.info(
                    "[pending-replay] D={} portfolio={} "
                    "decisions={} executed={} rejected={} "
                    "still_pending={}",
                    original_date, pid, p_decisions, p_executed,
                    p_rejected, p_new_pending,
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[pending-replay] portfolio={} crashed: {}",
                pid, exc,
            )
            per_portfolio.append({
                "portfolio_id": pid, "error": str(exc),
            })

    # Marker — write only if at least some attempt was made AND
    # no portfolios crashed (so the next run will retry on crash).
    crashed = any("error" in p for p in per_portfolio)
    summary = {
        "decisions_total": decisions_total,
        "executed_total": executed_total,
        "rejected_total": rejected_total,
        "still_pending_count": new_pending_count,
        "per_portfolio": per_portfolio,
    }
    if not crashed:
        _write_marker(skips_dir, original_date, summary)
    return summary


def replay_all_pending(
    *, before: dt.date,
    SessionFactory,
    skips_dir: Path = SKIPS_DIR,
    max_dates: int = 30,
    from_date: dt.date | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Replay every prior date with pending fills. Bounded by
    `max_dates` to avoid runaway loops on a stale skips_dir.

    `from_date` enforces a lower bound (default: no lower bound).
    `force=True` ignores existing `.replayed.jsonl` markers — used
    for explicit operator backfill."""
    dates = collect_pending_dates(
        before=before, skips_dir=skips_dir,
        from_date=from_date, force=force,
    )[:max_dates]
    logger.info(
        "[pending-replay] candidate dates from={} before={} "
        "force={} : {}",
        from_date, before, force,
        [d.isoformat() for d in dates],
    )
    per_date: list[dict[str, Any]] = []
    total_executed = 0
    total_still_pending = 0
    for d in dates:
        s = replay_pending_for_date(
            original_date=d, SessionFactory=SessionFactory,
            skips_dir=skips_dir,
        )
        per_date.append({"date": d.isoformat(), **s})
        total_executed += s["executed_total"]
        total_still_pending += s["still_pending_count"]
    return {
        "dates_replayed": [d.isoformat() for d in dates],
        "executed_total": total_executed,
        "still_pending_total": total_still_pending,
        "per_date": per_date,
        "from_date": from_date.isoformat() if from_date else None,
        "before": before.isoformat(),
        "force": force,
    }
