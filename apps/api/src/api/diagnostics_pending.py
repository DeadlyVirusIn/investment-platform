"""Read-only "Pending T+1 Decisions" diagnostic.

Surfaces today's evaluation signals that the auto-trader rejected
because no `price_bar` row exists with `ts > submitted_at` yet (the
v1 fill model is next-bar-open). Pure read. NEVER mutates DB. NEVER
imports strict engine modules. NEVER schedules itself.

Sources:
  * artifacts/paper_trading_skips/<YYYY-MM-DD>.jsonl
  * decision_log (skip rows whose reason matches the frozen regex)
  * price_bar (latest ts per asset to confirm next bar absent)

Frozen constants:
  DEFAULT_LOOKBACK_DAYS, MAX_LOOKBACK_DAYS, SKIP_REASON_REGEX,
  EXPECTED_FILL_OFFSET_DAYS — bumping any requires registry-review.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import get_session


# Frozen constants — DO NOT bump without registry-review.
DEFAULT_LOOKBACK_DAYS = 5
MAX_LOOKBACK_DAYS = 30
SKIP_REASON_REGEX = r"no price bar available after submitted_at"
EXPECTED_FILL_OFFSET_DAYS = 1
SKIPS_DIR = Path("artifacts/paper_trading_skips")
FILL_STATUS = "waiting_for_next_bar"


router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


# ---------------------------------------------------------------------------
# Helpers (pure-fn)
# ---------------------------------------------------------------------------

def _read_skip_lines(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL skip artifact. Returns empty list when missing.
    NEVER raises on a malformed line; skips it."""
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                out.append(row)
        except json.JSONDecodeError:
            continue
    return out


def _expected_fill_run_utc(as_of_date: dt.date) -> dt.datetime:
    """T+1 next-bar-fill expectation. v1 daily cron fires next at the
    next ET-23:30 boundary, encoded here as +1 calendar day @ 03:30
    UTC for simplicity (the daily cron runs around that time)."""
    target = as_of_date + dt.timedelta(days=EXPECTED_FILL_OFFSET_DAYS)
    return dt.datetime(
        target.year, target.month, target.day, 3, 30,
        tzinfo=dt.timezone.utc,
    )


def _next_ingest_eta_utc(as_of_date: dt.date) -> dt.datetime:
    """ingest_prices_daily cron fires `0 22 * * 1-5` ET — encoded as
    +1 calendar day @ 02:00 UTC."""
    target = as_of_date + dt.timedelta(days=1)
    return dt.datetime(
        target.year, target.month, target.day, 2, 0,
        tzinfo=dt.timezone.utc,
    )


def _latest_bar_ts(
    session: Session, *, symbol: str | None,
) -> dt.datetime | None:
    """Latest price_bar.ts for a symbol; None when symbol missing or
    no bar exists. Pure read."""
    if not symbol:
        return None
    row = session.execute(text(
        """
        SELECT MAX(pb.ts)
        FROM price_bar pb
        JOIN asset a ON a.id = pb.asset_id
        WHERE a.symbol = :sym
          AND pb.timeframe = '1d'
        """
    ), {"sym": symbol}).first()
    if row is None or row[0] is None:
        return None
    val = row[0]
    if isinstance(val, dt.datetime):
        return val
    return None


def _decision_log_skips(
    session: Session,
    *,
    cutoff: dt.date,
) -> list[dict[str, Any]]:
    """Skip rows in decision_log within the lookback window whose
    reason text matches the frozen regex."""
    rows = session.execute(text(
        """
        SELECT
            d.as_of_date           AS as_of_date,
            d.decision_ts          AS submitted_at,
            d.instrument           AS symbol,
            d.engine               AS engine,
            d.decision_version     AS rule,
            d.action               AS kind,
            d.reason               AS reason
        FROM decision_log d
        WHERE d.as_of_date >= :cutoff
          AND d.reason ~* :regex
        ORDER BY d.as_of_date DESC, d.decision_ts DESC
        """
    ), {"cutoff": cutoff, "regex": SKIP_REASON_REGEX}).all()
    return [dict(r._mapping) for r in rows]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/pending-t1")
def pending_t1(
    as_of_date: dt.date = Query(default_factory=dt.date.today),
    lookback_days: int = Query(
        default=DEFAULT_LOOKBACK_DAYS, ge=1, le=MAX_LOOKBACK_DAYS,
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Read-only T+1 pending decisions surface.

    Aggregates:
      * artifact rows from artifacts/paper_trading_skips/*.jsonl
        within the lookback window, AND
      * decision_log rows tagged with the frozen
        `no price bar available after submitted_at` reason
    """
    cutoff = as_of_date - dt.timedelta(days=lookback_days)

    pending: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()

    # 1. Walk skip artifacts in the window
    d = cutoff
    artifacts_seen: list[str] = []
    while d <= as_of_date + dt.timedelta(days=1):
        # +1: skip artifact for "today's run" lands at next-day filename
        # in some pipelines (the file is keyed by next_date in the
        # auto-trader). Walk inclusive on both sides to catch both
        # conventions without changing anything.
        path = SKIPS_DIR / f"{d.isoformat()}.jsonl"
        if path.exists():
            artifacts_seen.append(path.name)
            for row in _read_skip_lines(path):
                reason = str(row.get("reason") or "")
                if not re.search(SKIP_REASON_REGEX, reason, re.IGNORECASE):
                    continue
                symbol = str(row.get("symbol") or row.get("asset") or "")
                submitted = str(row.get("submitted_at") or "")
                kind = str(row.get("kind") or "")
                key = (submitted, symbol, kind)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                latest_bar = _latest_bar_ts(session, symbol=symbol)
                pending.append({
                    "submitted_at": submitted,
                    "as_of_date": str(row.get("as_of_date") or d.isoformat()),
                    "symbol": symbol,
                    "asset_id": row.get("asset_id"),
                    "engine": row.get("engine"),
                    "rule": row.get("rule") or row.get("decision_version"),
                    "kind": kind,
                    "fill_status": FILL_STATUS,
                    "reason": (
                        "next price_bar not available yet "
                        f"(latest bar={latest_bar.isoformat() if latest_bar else 'none'}; "
                        "need bar with ts>submitted_at)"
                    ),
                    "latest_bar_ts": (
                        latest_bar.isoformat() if latest_bar else None
                    ),
                    "expected_fill_run":
                        _expected_fill_run_utc(as_of_date).isoformat(),
                    "source": "skip_artifact",
                })
        d += dt.timedelta(days=1)

    # 2. decision_log skip rows (covers any day where the artifact
    # was not written but the decision was logged)
    for row in _decision_log_skips(session, cutoff=cutoff):
        symbol = str(row.get("symbol") or "")
        submitted = (
            row["submitted_at"].isoformat()
            if isinstance(row.get("submitted_at"), dt.datetime)
            else str(row.get("submitted_at") or "")
        )
        kind = str(row.get("kind") or "")
        key = (submitted, symbol, kind)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        latest_bar = _latest_bar_ts(session, symbol=symbol)
        pending.append({
            "submitted_at": submitted,
            "as_of_date":
                row["as_of_date"].isoformat()
                if isinstance(row.get("as_of_date"), dt.date)
                else str(row.get("as_of_date") or ""),
            "symbol": symbol,
            "asset_id": None,
            "engine": row.get("engine"),
            "rule": row.get("rule"),
            "kind": kind,
            "fill_status": FILL_STATUS,
            "reason": (
                "next price_bar not available yet "
                f"(latest bar={latest_bar.isoformat() if latest_bar else 'none'}; "
                "need bar with ts>submitted_at)"
            ),
            "latest_bar_ts":
                latest_bar.isoformat() if latest_bar else None,
            "expected_fill_run":
                _expected_fill_run_utc(as_of_date).isoformat(),
            "source": "decision_log",
        })

    by_kind: dict[str, int] = {}
    for p in pending:
        by_kind[p["kind"]] = by_kind.get(p["kind"], 0) + 1

    return {
        "as_of_date": as_of_date.isoformat(),
        "now_utc":
            dt.datetime.now(dt.timezone.utc).isoformat(),
        "n_pending": len(pending),
        "pending": pending,
        "summary": {
            "by_kind": by_kind,
            "next_ingest_eta": _next_ingest_eta_utc(as_of_date).isoformat(),
            "next_paper_run_eta":
                _expected_fill_run_utc(as_of_date).isoformat(),
            "artifacts_seen": artifacts_seen,
        },
        "fill_model_note": (
            "v1 fill model is next-bar-open. Decisions submitted at "
            "time T fill at the open of the next available daily bar. "
            "Read-only diagnostic. No actions."
        ),
    }
