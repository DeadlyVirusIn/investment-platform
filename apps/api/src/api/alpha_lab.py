"""Alpha Lab read-only endpoint.

GET /api/performance/paper/alpha-lab

Aggregates real paper-trading state into one endpoint optimized
for the Alpha Lab UI. Reads:

  paper_portfolio       (active filter)
  paper_position        (open vs closed, qty, avg_cost, holding age)
  paper_trade           (sell rows for realized PnL + reason)
  paper_equity_snapshot (latest cash/equity/upnl per portfolio)
  price_bar             (latest mark for unrealized PnL)
  replay_recovery_manifest (live vs replay tag — best-effort)

Pure read; no writes; no fabricated values; missing prices flow
through as null.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.auth import identity as ident
from apps.api.src.api.admin_guard import _email_and_role, is_owner
from apps.api.src.domain.paper_trading.paper_service import public_book_label


router = APIRouter(prefix="/performance/paper", tags=["alpha-lab"])

_PENDING_REASON = "execution_failure"
_PENDING_MARKER = "no price bar available after submitted_at"
_SKIPS_DIR = Path("artifacts/paper_trading_skips")


def _replay_ids(db: Session) -> set[str]:
    try:
        return {
            r[0] for r in db.execute(text("""
                SELECT entity_id FROM replay_recovery_manifest
                WHERE entity_type = 'paper_trade'
            """)).all()
        }
    except Exception:  # noqa: BLE001
        db.rollback()
        return set()


def _pending_count(as_of: dt.date) -> int:
    """Sum unmarked pending entries across every prior date in the
    skip JSONL store. Mirrors `/performance/paper/pending-fills`."""
    if not _SKIPS_DIR.exists():
        return 0
    n = 0
    for p in _SKIPS_DIR.iterdir():
        if p.suffix != ".jsonl":
            continue
        if p.name.endswith(".replayed.jsonl"):
            continue
        try:
            d = dt.date.fromisoformat(p.stem)
        except ValueError:
            continue
        if d > as_of:
            continue
        marker = _SKIPS_DIR / f"{d.isoformat()}.replayed.jsonl"
        if marker.exists() and d != as_of:
            continue
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("reason") != _PENDING_REASON:
                    continue
                detail = row.get("detail") or {}
                if _PENDING_MARKER.lower() in (
                    (detail.get("exec_reason") or "").lower()
                ):
                    n += 1
        except OSError:
            continue
    return n


def _age_bucket(days: int) -> str:
    if days <= 1:
        return "<=1d"
    if days <= 5:
        return "2-5d"
    if days <= 10:
        return "6-10d"
    if days <= 20:
        return "11-20d"
    return ">20d"


@router.get("/alpha-lab")
def alpha_lab(
    request: Request,
    db: Session = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    owner_uid = ident.session_user_id(db, request.cookies.get(ident.SESSION_COOKIE))
    request_is_owner = False
    if owner_uid:
        email, role = _email_and_role(db, owner_uid)
        request_is_owner = role == "owner" or is_owner(email)
    today = dt.datetime.now(dt.timezone.utc).date()
    replay_set = _replay_ids(db)

    # Open positions joined to latest price_bar for mark.
    open_rows = db.execute(text(f"""
        WITH latest_bar AS (
            SELECT DISTINCT ON (asset_id)
                   asset_id, ts::date AS bar_date,
                   coalesce(adjusted_close, close)::numeric AS px
            FROM price_bar
            WHERE timeframe = '1d'
            ORDER BY asset_id, ts DESC
        )
        SELECT pp.id, pp.portfolio_id, p.name AS portfolio_name,
               pp.asset_id, a.symbol, pp.quantity, pp.avg_cost,
               pp.opened_at,
               lb.px AS last_price, lb.bar_date AS last_price_date
        FROM paper_position pp
        JOIN paper_portfolio p ON p.id = pp.portfolio_id
        JOIN asset a ON a.id = pp.asset_id
        LEFT JOIN latest_bar lb ON lb.asset_id = pp.asset_id
        WHERE pp.is_open = TRUE AND p.is_active = TRUE {"" if request_is_owner else "AND p.name NOT LIKE 'user:%'"}
    """)).mappings().all()

    open_items: list[dict[str, Any]] = []
    open_unrealized = 0.0
    for r in open_rows:
        qty = float(r["quantity"])
        basis = float(r["avg_cost"])
        last_px = (
            float(r["last_price"])
            if r["last_price"] is not None else None
        )
        upnl = (
            (last_px - basis) * qty
            if last_px is not None else None
        )
        upnl_pct = (
            ((last_px - basis) / basis) if last_px is not None
            and basis > 0 else None
        )
        if upnl is not None:
            open_unrealized += upnl
        opened_at = r["opened_at"]
        held_days = (today - opened_at.date()).days if opened_at else None
        item = {
            "position_id": r["id"],
            "portfolio_id": r["portfolio_id"],
            "portfolio_name": public_book_label(
                r["portfolio_name"], is_owner=request_is_owner
            ),
            "symbol": r["symbol"],
            "asset_id": r["asset_id"],
            "quantity": qty,
            "entry_price": basis,
            "last_price": last_px,
            "last_price_date": (
                r["last_price_date"].isoformat()
                if r["last_price_date"] else None
            ),
            "unrealized_pnl": upnl,
            "unrealized_pnl_pct": upnl_pct,
            "held_days": held_days,
            "age_bucket": (
                _age_bucket(held_days)
                if held_days is not None else None
            ),
        }
        open_items.append(item)

    open_items.sort(
        key=lambda x: (
            x["unrealized_pnl_pct"] is None,
            -(x["unrealized_pnl_pct"] or 0.0),
        ),
    )
    open_winners = [
        x for x in open_items
        if x["unrealized_pnl_pct"] is not None
        and x["unrealized_pnl_pct"] > 0
    ][:limit]
    open_losers = [
        x for x in sorted(
            (
                x for x in open_items
                if x["unrealized_pnl_pct"] is not None
                and x["unrealized_pnl_pct"] < 0
            ),
            key=lambda x: x["unrealized_pnl_pct"] or 0.0,
        )
    ][:limit]

    # Closed paper trades (sell rows) joined back to entry trade for
    # holding-day calc + symbol.
    closed_rows = db.execute(text(f"""
        SELECT t.id AS trade_id, p.name AS portfolio_name,
               t.portfolio_id, a.symbol, t.quantity,
               t.fill_price AS exit_price, t.fill_ts AS exit_ts,
               t.realized_pnl, t.reason
        FROM paper_trade t
        JOIN paper_portfolio p ON p.id = t.portfolio_id
        JOIN asset a ON a.id = t.asset_id
        WHERE t.side = 'sell' {"" if request_is_owner else "AND p.name NOT LIKE 'user:%'"}
        ORDER BY t.fill_ts DESC
        LIMIT 200
    """)).mappings().all()

    closed_items: list[dict[str, Any]] = []
    closed_realized = 0.0
    for r in closed_rows:
        pnl = (
            float(r["realized_pnl"])
            if r["realized_pnl"] is not None else 0.0
        )
        closed_realized += pnl
        closed_items.append({
            "trade_id": str(r["trade_id"]),
            "portfolio_name": public_book_label(
                r["portfolio_name"], is_owner=request_is_owner
            ),
            "portfolio_id": str(r["portfolio_id"]),
            "symbol": r["symbol"],
            "quantity": float(r["quantity"]),
            "exit_price": float(r["exit_price"]),
            "exit_ts": (
                r["exit_ts"].isoformat() if r["exit_ts"] else None
            ),
            "realized_pnl": pnl,
            "reason": r["reason"],
            "is_replay": str(r["trade_id"]) in replay_set,
        })

    closed_winners = sorted(
        [c for c in closed_items if c["realized_pnl"] > 0],
        key=lambda x: -x["realized_pnl"],
    )[:limit]
    closed_losers = sorted(
        [c for c in closed_items if c["realized_pnl"] < 0],
        key=lambda x: x["realized_pnl"],
    )[:limit]

    # Live vs replay counts come from paper_trade buy rows.
    trade_rows = db.execute(text(f"""
        SELECT t.id FROM paper_trade t
        JOIN paper_portfolio p ON p.id = t.portfolio_id
        WHERE t.side = 'buy'
          {"" if request_is_owner else "AND p.name NOT LIKE 'user:%'"}
    """)).all()
    total_buys = len(trade_rows)
    replay_buys = sum(
        1 for r in trade_rows if str(r[0]) in replay_set
    )
    live_buys = total_buys - replay_buys

    # Patterns — open-aware aggregations.
    by_age_bucket: dict[str, dict[str, Any]] = {}
    for it in open_items:
        b = it["age_bucket"] or "unknown"
        bucket = by_age_bucket.setdefault(
            b, {"bucket": b, "n": 0, "avg_upnl_pct": 0.0,
                 "sum_pct": 0.0},
        )
        bucket["n"] += 1
        if it["unrealized_pnl_pct"] is not None:
            bucket["sum_pct"] += it["unrealized_pnl_pct"]
    for b in by_age_bucket.values():
        b["avg_upnl_pct"] = (
            b["sum_pct"] / b["n"] if b["n"] else 0.0
        )
        del b["sum_pct"]

    by_portfolio: dict[str, dict[str, Any]] = {}
    for it in open_items:
        key = it["portfolio_name"] or "?"
        b = by_portfolio.setdefault(
            key, {
                "portfolio": key, "n_open": 0,
                "sum_unrealized": 0.0,
            },
        )
        b["n_open"] += 1
        if it["unrealized_pnl"] is not None:
            b["sum_unrealized"] += it["unrealized_pnl"]

    concentration: list[dict[str, Any]] = []
    by_symbol: dict[str, dict[str, Any]] = {}
    for it in open_items:
        s = it["symbol"]
        b = by_symbol.setdefault(s, {
            "symbol": s, "n_open": 0,
            "total_notional": 0.0,
        })
        b["n_open"] += 1
        if it["last_price"] is not None:
            b["total_notional"] += it["last_price"] * it["quantity"]
    concentration = sorted(
        by_symbol.values(),
        key=lambda x: -x["total_notional"],
    )[:10]

    # Paper portfolio aggregate from latest equity snapshot.
    # Phase L M079: canonical alpha-lab summary — live-only.
    snap = db.execute(text(f"""
        SELECT DISTINCT ON (s.portfolio_id)
               s.snapshot_date, sum(s.total_equity)
               OVER (PARTITION BY s.snapshot_date) AS total_eq,
               s.cash, s.unrealized_pnl
        FROM paper_equity_snapshot s
        JOIN paper_portfolio p ON p.id = s.portfolio_id
        WHERE p.is_active = TRUE {"" if request_is_owner else "AND p.name NOT LIKE 'user:%'"}
          AND s.source = 'live'
        ORDER BY s.portfolio_id, s.snapshot_date DESC, s.recorded_at DESC, s.id DESC
    """)).all()
    pending_n = _pending_count(today)

    summary = {
        "as_of_date": today.isoformat(),
        "open_positions": len(open_items),
        "closed_positions": len(closed_items),
        "open_unrealized_pnl": open_unrealized,
        "closed_realized_pnl": closed_realized,
        "pending_fills": pending_n,
        "live_trades": live_buys,
        "replay_trades": replay_buys,
        "open_winners_count": sum(
            1 for x in open_items
            if (x["unrealized_pnl_pct"] or 0) > 0
        ),
        "open_losers_count": sum(
            1 for x in open_items
            if (x["unrealized_pnl_pct"] or 0) < 0
        ),
    }

    return {
        "as_of_date": today.isoformat(),
        "summary": summary,
        "open_winners": open_winners,
        "open_losers": open_losers,
        "closed_winners": closed_winners,
        "closed_losers": closed_losers,
        "patterns": {
            "by_age_bucket": list(by_age_bucket.values()),
            "by_portfolio": list(by_portfolio.values()),
            "concentration": concentration,
        },
        "notice": (
            "Read-only Alpha Lab data. Unrealized P&L computed from "
            "latest price_bar; missing marks flow through as null. "
            "Replay-flagged trades tagged via "
            "replay_recovery_manifest, not subtracted from "
            "headline figures."
        ),
    }
