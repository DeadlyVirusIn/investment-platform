"""Personal-Analytics Phase — read-only paper-trading performance.

Surfaces the metrics a personal operator wants out of the
account-path paper-trading data: live-vs-replay split counts,
realized P&L, unrealized P&L when last-price data exists,
exposure-by-symbol, win rate (only when there are closed trades),
and best/worst realized trade.

Distinct from the existing `/performance/*` router which serves the
selector-strategy reports. These endpoints read from
`paper_trade` + `paper_position` and respect
`replay_recovery_manifest` provenance.

Hard rules:
  * GET-only. NO POST/PUT/PATCH/DELETE handlers may be added here.
  * No writes to any table.
  * Never call replay rows "live trades".
  * If there are zero closed trades, return `win_rate=null` and
    `note="no_closed_outcomes_yet"`. Never fabricate a denominator.
  * Default exclusion of replay rows mirrors `/paper/executed/*`:
    `?include_replay=false` (default) hides them; the response always
    surfaces split counts + `has_replay_recovered_rows` so the UI can
    show recovered availability without flipping the toggle.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import get_session


router = APIRouter(prefix="/performance/paper", tags=["performance"])
# Options shadow suggestions live at /performance/options/* per spec
# (intentionally distinct from the paper router so the URL surface
# matches the spec exactly).
options_router = APIRouter(
    prefix="/performance/options", tags=["performance-options"],
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
_REPLAY_NOT_EXISTS = """
NOT EXISTS (
  SELECT 1 FROM replay_recovery_manifest m
  WHERE m.entity_type = :etype
    AND m.entity_id = :eid
    AND m.source IN ('replay','test')
)
""".strip()


def _excl(include_replay: bool, etype: str, alias: str) -> str:
    """Inline NOT-EXISTS exclusion clause; bound parameters injected
    separately. `etype` is restricted to a literal allow-list and the
    alias must be alnum so we never interpolate untrusted values."""
    if include_replay:
        return ""
    if etype not in ("paper_trade", "paper_position"):
        raise ValueError(f"unknown entity type: {etype!r}")
    if not all(c.isalnum() or c == "_" for c in alias):
        raise ValueError(f"bad alias: {alias!r}")
    return (
        f" AND NOT EXISTS (SELECT 1 FROM replay_recovery_manifest m "
        f"WHERE m.entity_type = '{etype}' "
        f"AND m.entity_id = {alias}.id::text "
        f"AND m.source IN ('replay','test'))"
    )


def _f(v: Any) -> float | None:
    """Decimal → float; None passthrough."""
    if v is None:
        return None
    return float(v) if isinstance(v, Decimal) else float(v)


# ---------------------------------------------------------------------------
# /performance/paper/summary
# ---------------------------------------------------------------------------
@router.get("/summary")
def paper_summary(
    db: Session = Depends(get_session),
    include_replay: bool = Query(False),
) -> dict[str, Any]:
    """High-level rollup. Always returns split counts; trade-bound
    aggregates honor `include_replay` for the headline numbers."""
    excl = _excl(include_replay, "paper_trade", "pt")
    excl_pos = _excl(include_replay, "paper_position", "pp")

    # Headline counts.
    total_trades = db.execute(text(
        f"SELECT count(*) FROM paper_trade pt WHERE 1=1 {excl}"
    )).scalar() or 0
    closed_trades = db.execute(text(
        f"SELECT count(*) FROM paper_trade pt "
        f"WHERE pt.realized_pnl IS NOT NULL {excl}"
    )).scalar() or 0
    open_trades = int(total_trades) - int(closed_trades)
    open_positions = db.execute(text(
        f"SELECT count(*) FROM paper_position pp "
        f"WHERE pp.is_open = true {excl_pos}"
    )).scalar() or 0
    realized_pnl_sum = db.execute(text(
        f"SELECT coalesce(sum(pt.realized_pnl), 0) FROM paper_trade pt "
        f"WHERE pt.realized_pnl IS NOT NULL {excl}"
    )).scalar() or 0
    win_count = db.execute(text(
        f"SELECT count(*) FROM paper_trade pt "
        f"WHERE pt.realized_pnl IS NOT NULL "
        f"  AND pt.realized_pnl > 0 {excl}"
    )).scalar() or 0
    loss_count = db.execute(text(
        f"SELECT count(*) FROM paper_trade pt "
        f"WHERE pt.realized_pnl IS NOT NULL "
        f"  AND pt.realized_pnl < 0 {excl}"
    )).scalar() or 0
    breakeven_count = int(closed_trades) - int(win_count) - int(loss_count)
    avg_realized = db.execute(text(
        f"SELECT avg(pt.realized_pnl) FROM paper_trade pt "
        f"WHERE pt.realized_pnl IS NOT NULL {excl}"
    )).scalar()
    best = db.execute(text(
        f"SELECT max(pt.realized_pnl) FROM paper_trade pt "
        f"WHERE pt.realized_pnl IS NOT NULL {excl}"
    )).scalar()
    worst = db.execute(text(
        f"SELECT min(pt.realized_pnl) FROM paper_trade pt "
        f"WHERE pt.realized_pnl IS NOT NULL {excl}"
    )).scalar()

    # Always-on split counts (independent of include_replay).
    live_trades = db.execute(text("""
        SELECT count(*) FROM paper_trade pt
        WHERE NOT EXISTS (
          SELECT 1 FROM replay_recovery_manifest m
          WHERE m.entity_type = 'paper_trade'
            AND m.entity_id = pt.id::text
            AND m.source IN ('replay','test')
        )
    """)).scalar() or 0
    replay_trades = db.execute(text("""
        SELECT count(*) FROM paper_trade pt
        WHERE EXISTS (
          SELECT 1 FROM replay_recovery_manifest m
          WHERE m.entity_type = 'paper_trade'
            AND m.entity_id = pt.id::text
            AND m.source IN ('replay','test')
        )
    """)).scalar() or 0
    has_replay = bool(replay_trades and replay_trades > 0)

    # Source breakdown ('live' is the absence of a manifest row).
    src_rows = db.execute(text("""
        SELECT
          coalesce(m.source, 'live') AS source,
          count(*)                   AS n
        FROM paper_trade pt
        LEFT JOIN replay_recovery_manifest m
          ON m.entity_type = 'paper_trade' AND m.entity_id = pt.id::text
        GROUP BY 1
        ORDER BY 2 DESC
    """)).mappings().all()
    source_breakdown = {r["source"]: int(r["n"]) for r in src_rows}

    # Win rate ONLY if there are closed trades; never fabricate a 0/0.
    win_rate: float | None
    note: str | None
    decided = int(win_count) + int(loss_count)
    if decided == 0:
        win_rate = None
        note = "no_closed_outcomes_yet"
    else:
        win_rate = float(win_count) / decided
        note = None

    # Outcome breakdown — uses paper_position to determine open vs closed.
    outcome_rows = db.execute(text(
        f"SELECT pt.realized_pnl IS NOT NULL AS closed, count(*) AS n "
        f"FROM paper_trade pt WHERE 1=1 {excl} GROUP BY 1"
    )).mappings().all()
    outcomes = {
        "closed": sum(int(r["n"]) for r in outcome_rows if r["closed"]),
        "open_pending": sum(int(r["n"]) for r in outcome_rows if not r["closed"]),
    }

    return {
        "include_replay": include_replay,
        "total_trades": int(total_trades),
        "open_trades": int(open_trades),
        "closed_trades": int(closed_trades),
        "open_positions": int(open_positions),
        "win_count": int(win_count),
        "loss_count": int(loss_count),
        "breakeven_count": int(breakeven_count),
        "win_rate": win_rate,
        "note": note,
        "realized_pnl_total": _f(realized_pnl_sum),
        "avg_realized_pnl": _f(avg_realized),
        "best_realized_pnl": _f(best),
        "worst_realized_pnl": _f(worst),
        "has_replay_recovered_rows": has_replay,
        "live_trades_count": int(live_trades),
        "replay_trades_count": int(replay_trades),
        "source_breakdown": source_breakdown,
        "outcomes": outcomes,
    }


# ---------------------------------------------------------------------------
# /performance/paper/trades
# ---------------------------------------------------------------------------
@router.get("/trades")
def paper_trades(
    db: Session = Depends(get_session),
    limit: int = Query(500, ge=1, le=2000),
    include_replay: bool = Query(False),
    closed_only: bool = Query(False),
) -> dict[str, Any]:
    """Trade-level rows with provenance + outcome status."""
    excl = _excl(include_replay, "paper_trade", "pt")
    closed_clause = (
        " AND pt.realized_pnl IS NOT NULL " if closed_only else ""
    )
    rows = db.execute(text(f"""
        SELECT
          pt.id            AS trade_id,
          a.symbol         AS symbol,
          pt.side          AS side,
          pt.quantity      AS quantity,
          pt.fill_price    AS fill_price,
          pt.fill_ts       AS fill_ts,
          pt.realized_pnl  AS realized_pnl,
          pt.reason        AS reason,
          coalesce(m.source, 'live') AS source,
          m.replay_run_id  AS replay_run_id,
          (pt.realized_pnl IS NOT NULL) AS is_closed
        FROM paper_trade pt
        JOIN asset a ON a.id = pt.asset_id
        LEFT JOIN replay_recovery_manifest m
          ON m.entity_type = 'paper_trade' AND m.entity_id = pt.id::text
        WHERE 1=1 {excl} {closed_clause}
        ORDER BY pt.fill_ts DESC
        LIMIT :limit
    """), {"limit": limit}).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({
            "trade_id": r.trade_id,
            "symbol": r.symbol,
            "side": r.side,
            "quantity": _f(r.quantity),
            "fill_price": _f(r.fill_price),
            "fill_ts": r.fill_ts.isoformat() if r.fill_ts else None,
            "realized_pnl": _f(r.realized_pnl),
            "reason": r.reason,
            "source": r.source or "live",
            "replay_run_id": r.replay_run_id,
            "outcome_status": "closed" if r.is_closed else "open_pending",
        })
    return {
        "include_replay": include_replay,
        "count": len(out),
        "trades": out,
    }


# ---------------------------------------------------------------------------
# /performance/paper/equity
# ---------------------------------------------------------------------------
@router.get("/equity")
def paper_equity(
    db: Session = Depends(get_session),
    include_replay: bool = Query(False),
) -> dict[str, Any]:
    """Open-position exposure by symbol + sector aggregate (when
    sector data is available). Computes `unrealized_pnl_usd` only
    when a recent price_bar exists for the asset; otherwise returns
    `unrealized_status='unavailable'` for that row."""
    excl_pos = _excl(include_replay, "paper_position", "pp")

    rows = db.execute(text(f"""
        WITH last_px AS (
            SELECT DISTINCT ON (asset_id) asset_id, close, ts
            FROM price_bar
            ORDER BY asset_id, ts DESC
        )
        SELECT
          a.symbol           AS symbol,
          a.sector           AS sector,
          pp.quantity        AS quantity,
          pp.avg_cost        AS avg_cost,
          last_px.close      AS last_price,
          last_px.ts         AS last_price_ts,
          coalesce(m.source, 'live') AS source
        FROM paper_position pp
        JOIN asset a ON a.id = pp.asset_id
        LEFT JOIN last_px ON last_px.asset_id = pp.asset_id
        LEFT JOIN replay_recovery_manifest m
          ON m.entity_type = 'paper_position' AND m.entity_id = pp.id::text
        WHERE pp.is_open = true {excl_pos}
        ORDER BY pp.opened_at DESC
    """)).mappings().all()

    by_symbol: dict[str, dict[str, Any]] = {}
    by_sector: dict[str, dict[str, Any]] = {}
    total_market_value = 0.0
    total_cost_basis = 0.0
    total_unrealized = 0.0
    unrealized_unavailable_count = 0

    for r in rows:
        sym = r["symbol"]
        sector = r["sector"] or "unknown"
        qty = float(r["quantity"]) if r["quantity"] is not None else 0.0
        avg_cost = float(r["avg_cost"]) if r["avg_cost"] is not None else 0.0
        last = (
            float(r["last_price"]) if r["last_price"] is not None else None
        )
        cost_basis = qty * avg_cost
        if last is not None and qty != 0:
            mv = qty * last
            unrealized = mv - cost_basis
            total_market_value += mv
            total_cost_basis += cost_basis
            total_unrealized += unrealized
            unrealized_status = "ok"
        else:
            mv = None
            unrealized = None
            unrealized_unavailable_count += 1
            unrealized_status = "unavailable"

        sym_entry = by_symbol.setdefault(sym, {
            "symbol": sym,
            "sector": sector,
            "quantity": 0.0,
            "cost_basis_usd": 0.0,
            "market_value_usd": 0.0,
            "unrealized_pnl_usd": 0.0,
            "unrealized_status": "ok",
            "source": r["source"] or "live",
        })
        sym_entry["quantity"] += qty
        sym_entry["cost_basis_usd"] += cost_basis
        if mv is not None:
            sym_entry["market_value_usd"] += mv
            sym_entry["unrealized_pnl_usd"] += unrealized
        else:
            sym_entry["unrealized_status"] = "unavailable"

        sec_entry = by_sector.setdefault(sector, {
            "sector": sector,
            "cost_basis_usd": 0.0,
            "market_value_usd": 0.0,
            "unrealized_pnl_usd": 0.0,
            "n_positions": 0,
        })
        sec_entry["cost_basis_usd"] += cost_basis
        if mv is not None:
            sec_entry["market_value_usd"] += mv
            sec_entry["unrealized_pnl_usd"] += unrealized
        sec_entry["n_positions"] += 1

    return {
        "include_replay": include_replay,
        "n_open_positions": len(rows),
        "total_cost_basis_usd": total_cost_basis,
        "total_market_value_usd": total_market_value,
        "total_unrealized_pnl_usd": total_unrealized,
        "unrealized_unavailable_count": unrealized_unavailable_count,
        "by_symbol": list(by_symbol.values()),
        "by_sector": list(by_sector.values()),
    }


# ---------------------------------------------------------------------------
# /performance/paper/attribution
# ---------------------------------------------------------------------------
@router.get("/attribution")
def paper_attribution(
    db: Session = Depends(get_session),
    include_replay: bool = Query(False),
) -> dict[str, Any]:
    """Realized-P&L attribution by symbol + by source (live vs replay).

    Honest about pending: `outcome_status` per row is one of
    {closed, open_pending}. Pending rows are aggregated separately
    so the operator never sees a derived metric mixing realized and
    unrealized values."""
    excl = _excl(include_replay, "paper_trade", "pt")

    sym_rows = db.execute(text(f"""
        SELECT
          a.symbol AS symbol,
          count(*) FILTER (WHERE pt.realized_pnl IS NOT NULL) AS closed,
          count(*) FILTER (WHERE pt.realized_pnl IS NULL)     AS open_pending,
          coalesce(sum(pt.realized_pnl), 0)                   AS realized_pnl,
          count(*)                                            AS total
        FROM paper_trade pt
        JOIN asset a ON a.id = pt.asset_id
        WHERE 1=1 {excl}
        GROUP BY 1
        ORDER BY 4 DESC
    """)).mappings().all()
    by_symbol = [
        {
            "symbol": r["symbol"],
            "total_trades": int(r["total"]),
            "closed_trades": int(r["closed"]),
            "open_pending_trades": int(r["open_pending"]),
            "realized_pnl_usd": _f(r["realized_pnl"]),
        }
        for r in sym_rows
    ]

    src_rows = db.execute(text("""
        SELECT
          coalesce(m.source, 'live') AS source,
          count(*) FILTER (WHERE pt.realized_pnl IS NOT NULL) AS closed,
          count(*) FILTER (WHERE pt.realized_pnl IS NULL)     AS open_pending,
          coalesce(sum(pt.realized_pnl), 0)                   AS realized_pnl,
          count(*)                                            AS total
        FROM paper_trade pt
        LEFT JOIN replay_recovery_manifest m
          ON m.entity_type = 'paper_trade' AND m.entity_id = pt.id::text
        GROUP BY 1
        ORDER BY 5 DESC
    """)).mappings().all()
    by_source = [
        {
            "source": r["source"],
            "total_trades": int(r["total"]),
            "closed_trades": int(r["closed"]),
            "open_pending_trades": int(r["open_pending"]),
            "realized_pnl_usd": _f(r["realized_pnl"]),
        }
        for r in src_rows
    ]

    return {
        "include_replay": include_replay,
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "by_symbol": by_symbol,
        "by_source": by_source,
    }


# ---------------------------------------------------------------------------
# Unrealized-PnL + exit tracking (read-only, diagnostic)
# ---------------------------------------------------------------------------
# Stale-price threshold. A position whose latest price_bar is older than
# this is reported with `stale_price=true`. Conservative default —
# operator can interpret freshness without us imputing a price.
STALE_PRICE_DAYS = 7


def _open_position_rows(
    db: Session, *, include_replay: bool,
) -> list[dict[str, Any]]:
    """Per-open-position row with latest-price join + freshness flags.

    Shared between /open-positions, /unrealized, and /exit-tracking so
    the three endpoints agree on the same source rows."""
    excl_pos = _excl(include_replay, "paper_position", "pp")
    rows = db.execute(text(f"""
        WITH last_px AS (
            SELECT DISTINCT ON (asset_id) asset_id, close, ts
            FROM price_bar
            ORDER BY asset_id, ts DESC
        )
        SELECT
          pp.id              AS position_id,
          pp.portfolio_id    AS portfolio_id,
          a.symbol           AS symbol,
          a.sector           AS sector,
          pp.quantity        AS quantity,
          pp.avg_cost        AS avg_cost,
          pp.opened_at       AS opened_at,
          last_px.close      AS last_price,
          last_px.ts         AS last_price_ts,
          coalesce(m.source, 'live') AS source,
          m.replay_run_id    AS replay_run_id
        FROM paper_position pp
        JOIN asset a ON a.id = pp.asset_id
        LEFT JOIN last_px ON last_px.asset_id = pp.asset_id
        LEFT JOIN replay_recovery_manifest m
          ON m.entity_type = 'paper_position' AND m.entity_id = pp.id::text
        WHERE pp.is_open = true {excl_pos}
        ORDER BY pp.opened_at DESC
    """)).mappings().all()

    now = dt.datetime.now(dt.timezone.utc)
    out: list[dict[str, Any]] = []
    for r in rows:
        qty = float(r["quantity"]) if r["quantity"] is not None else 0.0
        avg_cost = (
            float(r["avg_cost"]) if r["avg_cost"] is not None else 0.0
        )
        last = (
            float(r["last_price"]) if r["last_price"] is not None else None
        )
        last_ts: dt.datetime | None = r["last_price_ts"]
        cost_basis = qty * avg_cost
        opened: dt.datetime | None = r["opened_at"]
        days_open = (
            (now - opened).total_seconds() / 86400.0
            if opened else None
        )

        latest_price_available = last is not None and last_ts is not None
        # `stale_price` is only meaningful when a price exists.
        if last_ts is None:
            stale_price = None
            missing_price = True
        else:
            age_days = (now - last_ts).total_seconds() / 86400.0
            stale_price = age_days > STALE_PRICE_DAYS
            missing_price = False

        if latest_price_available and qty != 0:
            unrealized_pnl = qty * (last - avg_cost)
            unrealized_return_pct = (
                (last - avg_cost) / avg_cost
                if avg_cost > 0 else None
            )
            unrealized_status = "ok"
        else:
            unrealized_pnl = None
            unrealized_return_pct = None
            unrealized_status = "unavailable"

        out.append({
            "position_id": r["position_id"],
            "portfolio_id": r["portfolio_id"],
            "symbol": r["symbol"],
            "sector": r["sector"],
            "source": r["source"] or "live",
            "replay_run_id": r["replay_run_id"],
            "is_replay": (r["source"] in ("replay", "test")),
            "entry_date": opened.date().isoformat() if opened else None,
            "fill_ts": opened.isoformat() if opened else None,
            "entry_price": avg_cost,
            "quantity": qty,
            "notional_at_entry_usd": cost_basis,
            "latest_price": last,
            "latest_price_date": (
                last_ts.date().isoformat() if last_ts else None
            ),
            "unrealized_pnl_usd": unrealized_pnl,
            "unrealized_return_pct": unrealized_return_pct,
            "unrealized_status": unrealized_status,
            "days_open": (
                round(days_open, 2) if days_open is not None else None
            ),
            "outcome_status": "open_pending",
            "data_quality": {
                "latest_price_available": latest_price_available,
                "stale_price": stale_price,
                "missing_price": missing_price,
                "stale_threshold_days": STALE_PRICE_DAYS,
            },
        })
    return out


@router.get("/open-positions")
def open_positions(
    db: Session = Depends(get_session),
    include_replay: bool = Query(False),
) -> dict[str, Any]:
    """Per-open-position rows with unrealized PnL when price data is
    available. Returns rows even when no price_bar is present so the
    UI can render "unavailable" instead of pretending zero."""
    rows = _open_position_rows(db, include_replay=include_replay)
    live_count = sum(1 for r in rows if not r["is_replay"])
    replay_count = sum(1 for r in rows if r["is_replay"])
    return {
        "include_replay": include_replay,
        "stale_threshold_days": STALE_PRICE_DAYS,
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "count": len(rows),
        "live_count": live_count,
        "replay_count": replay_count,
        "positions": rows,
    }


@router.get("/unrealized")
def unrealized_summary(
    db: Session = Depends(get_session),
    include_replay: bool = Query(False),
) -> dict[str, Any]:
    """Aggregate unrealized stats over open positions. Live and replay
    rows are reported in separate sub-totals so the UI never silently
    rolls them together. Skips rows where unrealized cannot be
    computed; surfaces those counts explicitly."""
    rows = _open_position_rows(db, include_replay=True)

    def _bucket(rows_in: list[dict[str, Any]]) -> dict[str, Any]:
        ok = [r for r in rows_in if r["unrealized_status"] == "ok"]
        unavail = [r for r in rows_in if r["unrealized_status"] == "unavailable"]
        if not ok:
            return {
                "n_positions": len(rows_in),
                "n_with_price": 0,
                "n_unavailable": len(unavail),
                "total_unrealized_pnl_usd": None,
                "avg_unrealized_return_pct": None,
                "best": None,
                "worst": None,
            }
        total_pnl = sum(r["unrealized_pnl_usd"] for r in ok)
        rets = [
            r["unrealized_return_pct"] for r in ok
            if r["unrealized_return_pct"] is not None
        ]
        avg_ret = sum(rets) / len(rets) if rets else None
        best = max(ok, key=lambda r: r["unrealized_pnl_usd"])
        worst = min(ok, key=lambda r: r["unrealized_pnl_usd"])
        return {
            "n_positions": len(rows_in),
            "n_with_price": len(ok),
            "n_unavailable": len(unavail),
            "total_unrealized_pnl_usd": total_pnl,
            "avg_unrealized_return_pct": avg_ret,
            "best": {
                "symbol": best["symbol"],
                "unrealized_pnl_usd": best["unrealized_pnl_usd"],
                "unrealized_return_pct": best["unrealized_return_pct"],
            },
            "worst": {
                "symbol": worst["symbol"],
                "unrealized_pnl_usd": worst["unrealized_pnl_usd"],
                "unrealized_return_pct": worst["unrealized_return_pct"],
            },
        }

    live_rows = [r for r in rows if not r["is_replay"]]
    replay_rows = [r for r in rows if r["is_replay"]]
    headline_rows = rows if include_replay else live_rows
    all_replay = bool(replay_rows) and not live_rows

    return {
        "include_replay": include_replay,
        "stale_threshold_days": STALE_PRICE_DAYS,
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "all_positions_are_replay": all_replay,
        "headline": _bucket(headline_rows),
        "live": _bucket(live_rows),
        "replay": _bucket(replay_rows),
    }


@router.get("/exit-tracking")
def exit_tracking(
    db: Session = Depends(get_session),
    include_replay: bool = Query(False),
) -> dict[str, Any]:
    """Diagnostic-only view of open positions for exit visibility.

    Strict policy:
      * Returns NO action recommendations. No "sell", "close", or
        "take profit" output ever.
      * `exit_rule` is `null` with `exit_rule_status="unavailable"`
        when no persisted exit-rule config exists for the position.
        (Engine config does not currently persist exit rules per
        symbol/strategy; surfacing them is a follow-up.)
      * Diagnostic labels are constrained to a frozen vocabulary so
        downstream UI cannot drift into action wording."""
    rows = _open_position_rows(db, include_replay=include_replay)

    diagnostics: list[dict[str, Any]] = []
    for r in rows:
        labels: list[str] = ["Monitoring", "Open pending"]
        if r["unrealized_status"] == "unavailable":
            labels.append("Exit rule unavailable")
        if r["data_quality"]["missing_price"]:
            labels.append("Missing price")
        elif r["data_quality"]["stale_price"]:
            labels.append("Price data stale")
        else:
            labels.append("Price data current")
        if r["is_replay"]:
            labels.append("Recovered replay")

        diagnostics.append({
            "position_id": r["position_id"],
            "symbol": r["symbol"],
            "source": r["source"],
            "is_replay": r["is_replay"],
            "entry_date": r["entry_date"],
            "days_open": r["days_open"],
            "outcome_status": "open_pending",
            "exit_rule": None,
            "exit_rule_status": "unavailable",
            "diagnostic_labels": labels,
        })

    return {
        "include_replay": include_replay,
        "stale_threshold_days": STALE_PRICE_DAYS,
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "count": len(diagnostics),
        "vocabulary": [
            "Monitoring",
            "Open pending",
            "Price data current",
            "Price data stale",
            "Missing price",
            "Exit rule unavailable",
            "Recovered replay",
        ],
        "notice": (
            "Diagnostic labels only. NO action recommendation, NO "
            "execution. Exit-rule data is not persisted; this endpoint "
            "reports rule availability only."
        ),
        "positions": diagnostics,
    }


# ---------------------------------------------------------------------------
# /performance/paper/lifecycle
# ---------------------------------------------------------------------------
# Lifecycle status / current_stage vocabularies — frozen so the UI
# can map them onto a fixed timeline. Any drift in copy here is a
# breaking contract change for the frontend.
_LIFECYCLE_STATUSES = (
    "entered",
    "open_pending",
    "closed",
    "outcome_pending",
    "outcome_labeled",
)
_LIFECYCLE_STAGES = (
    "entry",
    "monitoring",
    "exit_recorded",
    "label_pending",
    "label_available",
)


@router.get("/lifecycle")
def lifecycle(
    db: Session = Depends(get_session),
    include_replay: bool = Query(False),
    limit: int = Query(500, ge=1, le=2000),
) -> dict[str, Any]:
    """Per-trade lifecycle view: entry → monitoring → exit → label.

    Joins `paper_trade` with the matching `paper_position` (by
    portfolio + asset + buy-side timestamp), latest `price_bar`,
    and any `recommendation_outcome` row reachable via
    `paper_trade.recommendation_id`. Read-only — never inserts a
    label, never closes a position.

    Returned vocabulary is constrained to `_LIFECYCLE_STATUSES` /
    `_LIFECYCLE_STAGES` so the UI cannot drift."""
    excl = _excl(include_replay, "paper_trade", "pt")

    rows = db.execute(text(f"""
        WITH last_px AS (
            SELECT DISTINCT ON (asset_id) asset_id, close, ts
            FROM price_bar
            ORDER BY asset_id, ts DESC
        )
        SELECT
          pt.id              AS trade_id,
          pt.portfolio_id    AS portfolio_id,
          pt.recommendation_id AS recommendation_id,
          a.symbol           AS symbol,
          pt.side            AS side,
          pt.quantity        AS quantity,
          pt.fill_price      AS fill_price,
          pt.fill_ts         AS fill_ts,
          pt.realized_pnl    AS realized_pnl,
          pt.reason          AS reason,
          last_px.close      AS last_price,
          last_px.ts         AS last_price_ts,
          coalesce(m.source, 'live') AS source,
          m.replay_run_id    AS replay_run_id,
          pp.id              AS position_id,
          pp.is_open         AS position_is_open,
          pp.opened_at       AS position_opened_at,
          pp.closed_at       AS position_closed_at,
          ro.id              AS recommendation_outcome_id,
          ro.barrier_label   AS barrier_label,
          ro.realized_30d_return AS realized_30d_return,
          ro.realized_90d_return AS realized_90d_return
        FROM paper_trade pt
        JOIN asset a ON a.id = pt.asset_id
        LEFT JOIN last_px ON last_px.asset_id = pt.asset_id
        LEFT JOIN replay_recovery_manifest m
          ON m.entity_type = 'paper_trade' AND m.entity_id = pt.id::text
        LEFT JOIN paper_position pp
          ON pp.portfolio_id = pt.portfolio_id
         AND pp.asset_id     = pt.asset_id
        LEFT JOIN recommendation_outcome ro
          ON ro.recommendation_id = pt.recommendation_id
        WHERE 1=1 {excl}
        ORDER BY pt.fill_ts DESC
        LIMIT :limit
    """), {"limit": limit}).mappings().all()

    now = dt.datetime.now(dt.timezone.utc)
    out: list[dict[str, Any]] = []
    counts = {
        "entered": 0, "open_pending": 0, "closed": 0,
        "outcome_pending": 0, "outcome_labeled": 0,
    }

    for r in rows:
        qty = float(r["quantity"]) if r["quantity"] is not None else 0.0
        entry_price = (
            float(r["fill_price"]) if r["fill_price"] is not None else 0.0
        )
        last = (
            float(r["last_price"]) if r["last_price"] is not None else None
        )
        last_ts: dt.datetime | None = r["last_price_ts"]
        fill_ts: dt.datetime | None = r["fill_ts"]
        notional = qty * entry_price
        days_open = (
            (now - fill_ts).total_seconds() / 86400.0
            if fill_ts else None
        )
        if last is not None and qty != 0 and entry_price > 0:
            unrealized_pnl = qty * (last - entry_price)
            unrealized_return_pct = (last - entry_price) / entry_price
        else:
            unrealized_pnl = None
            unrealized_return_pct = None

        is_replay = r["source"] in ("replay", "test")
        is_closed = r["realized_pnl"] is not None
        has_label = (
            r["barrier_label"] is not None
            or r["realized_30d_return"] is not None
        )
        has_outcome_row = r["recommendation_outcome_id"] is not None

        # Lifecycle status — derived strictly from observed state.
        if has_label:
            lifecycle_status = "outcome_labeled"
            current_stage = "label_available"
        elif is_closed:
            # Trade closed but no label yet.
            lifecycle_status = "outcome_pending"
            current_stage = "exit_recorded"
        elif r["recommendation_outcome_id"] is not None:
            # Outcome row exists but neither closed nor labeled — pending.
            lifecycle_status = "open_pending"
            current_stage = "label_pending"
        elif fill_ts is not None:
            lifecycle_status = "open_pending"
            current_stage = "monitoring"
        else:
            lifecycle_status = "entered"
            current_stage = "entry"

        # Defensive: keep lifecycle vocab pinned at runtime.
        assert lifecycle_status in _LIFECYCLE_STATUSES
        assert current_stage in _LIFECYCLE_STAGES
        counts[lifecycle_status] = counts.get(lifecycle_status, 0) + 1

        # Missing-reason narrative — single string for the UI.
        missing_bits: list[str] = []
        if fill_ts is None:
            missing_bits.append("entry")
        if last is None:
            missing_bits.append("latest_price")
        if not is_closed:
            missing_bits.append("exit")
        if not has_label:
            missing_bits.append("label")
        missing_reason = (
            ", ".join(missing_bits) if missing_bits else None
        )

        out.append({
            "trade_id": r["trade_id"],
            "symbol": r["symbol"],
            "source": r["source"] or "live",
            "is_replay": is_replay,
            "side": r["side"],
            "entry_ts": fill_ts.isoformat() if fill_ts else None,
            "entry_price": entry_price,
            "quantity": qty,
            "notional_usd": notional,
            "latest_price": last,
            "latest_price_ts": last_ts.isoformat() if last_ts else None,
            "unrealized_pnl_usd": unrealized_pnl,
            "unrealized_return_pct": unrealized_return_pct,
            "days_open": (
                round(days_open, 2) if days_open is not None else None
            ),
            "lifecycle_status": lifecycle_status,
            "current_stage": current_stage,
            "linked_ids": {
                "recommendation_id": r["recommendation_id"],
                # decision_log has no recommendation_id FK in current
                # schema; the link will require a follow-up migration
                # or an instrument+as_of_date joiner. Surfaced as null
                # rather than guessed.
                "decision_log_id": None,
                "recommendation_outcome_id": r["recommendation_outcome_id"],
                "replay_run_id": r["replay_run_id"],
                "position_id": r["position_id"],
            },
            "data_quality": {
                "has_entry": fill_ts is not None,
                "has_latest_price": last is not None,
                "has_exit": is_closed,
                "has_label": has_label,
                "has_recommendation_outcome_row": has_outcome_row,
                "missing_reason": missing_reason,
            },
        })

    return {
        "include_replay": include_replay,
        "as_of": now.isoformat(),
        "count": len(out),
        "lifecycle_statuses": list(_LIFECYCLE_STATUSES),
        "lifecycle_stages": list(_LIFECYCLE_STAGES),
        "status_counts": counts,
        "trades": out,
    }


# ---------------------------------------------------------------------------
# /performance/paper/pending-fills
# ---------------------------------------------------------------------------
# Pending-fill source = paper-trading skip JSONL written by
# `apps/worker/src/jobs/run_paper_trading.py`. A "pending next-bar"
# row is one whose skip reason is `execution_failure` with
# `detail.exec_reason` matching the no-price-bar message. Read-only —
# no DB writes, no JSONL writes.
_SKIPS_DIR = "artifacts/paper_trading_skips"
_PENDING_FILL_REASON = "execution_failure"
_PENDING_FILL_MARKER = "no price bar available after submitted_at"


def _next_trading_day(d: dt.date) -> dt.date:
    """Mon..Fri → next weekday. No holiday calendar (matches
    `apps/api/src/domain/ops/daily_runner._is_trading_day`)."""
    cur = d + dt.timedelta(days=1)
    while cur.weekday() >= 5:
        cur += dt.timedelta(days=1)
    return cur


@router.get("/pending-fills")
def pending_fills(
    db: Session = Depends(get_session),
    as_of: str | None = Query(
        None, description="ISO date; defaults to latest skip JSONL date.",
    ),
) -> dict[str, Any]:
    """Surface paper-trade decisions that the existing next-bar fill
    guard rejected because no `price_bar` exists after the submission
    timestamp yet. These are NOT failed trades — they are valid
    decisions waiting for the next bar.

    Pure read-only:
      * reads the per-day skip JSONL produced by run_paper_trading
      * joins symbols + portfolio names + latest price_bar from DB
      * never writes
    """
    import json
    from pathlib import Path

    skips_dir = Path(_SKIPS_DIR)
    target_date: dt.date | None
    if as_of is not None:
        try:
            target_date = dt.date.fromisoformat(as_of)
        except ValueError:
            return {"error": "as_of must be ISO date YYYY-MM-DD"}
    else:
        # Pick the newest YYYY-MM-DD.jsonl file under the skips dir.
        candidates: list[dt.date] = []
        if skips_dir.exists():
            for p in skips_dir.iterdir():
                if p.suffix != ".jsonl":
                    continue
                try:
                    candidates.append(dt.date.fromisoformat(p.stem))
                except ValueError:
                    continue
        target_date = max(candidates) if candidates else None

    if target_date is None:
        return {
            "as_of_date": None,
            "count": 0,
            "items": [],
            "notice": (
                "No paper_trading_skips file found. Run "
                "scripts.run_paper_daily_safe to populate."
            ),
        }

    path = skips_dir / f"{target_date.isoformat()}.jsonl"
    if not path.exists():
        return {
            "as_of_date": target_date.isoformat(),
            "count": 0,
            "items": [],
        }

    raw_rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("reason") != _PENDING_FILL_REASON:
            continue
        detail = row.get("detail") or {}
        exec_reason = (detail.get("exec_reason") or "").lower()
        if _PENDING_FILL_MARKER.lower() not in exec_reason:
            continue
        raw_rows.append(row)

    if not raw_rows:
        return {
            "as_of_date": target_date.isoformat(),
            "count": 0,
            "items": [],
        }

    asset_ids = list({r["asset_id"] for r in raw_rows if r.get("asset_id")})
    portfolio_ids = list({
        r["portfolio_id"] for r in raw_rows if r.get("portfolio_id")
    })

    # Symbol resolution.
    sym_rows = db.execute(
        text("SELECT id, symbol FROM asset WHERE id = ANY(:ids)"),
        {"ids": asset_ids},
    ).all() if asset_ids else []
    sym_by_id = {r[0]: r[1] for r in sym_rows}

    # Portfolio name resolution.
    pf_rows = db.execute(
        text("SELECT id, name FROM paper_portfolio WHERE id = ANY(:ids)"),
        {"ids": portfolio_ids},
    ).all() if portfolio_ids else []
    pf_by_id = {r[0]: r[1] for r in pf_rows}

    # Latest price_bar timestamp per asset.
    latest_rows = db.execute(text("""
        SELECT asset_id, max(ts) AS latest_ts
        FROM price_bar
        WHERE asset_id = ANY(:ids)
        GROUP BY asset_id
    """), {"ids": asset_ids}).all() if asset_ids else []
    latest_ts_by_asset = {r[0]: r[1] for r in latest_rows}

    next_bar_date = _next_trading_day(target_date)

    items: list[dict[str, Any]] = []
    for r in raw_rows:
        aid = r.get("asset_id")
        latest_ts = latest_ts_by_asset.get(aid)
        items.append({
            "symbol": sym_by_id.get(aid, "?"),
            "asset_id": aid,
            "action": "Buy",
            "submitted_at": r.get("submitted_at") or (
                # Skip JSONL doesn't capture submitted_at directly;
                # default to as_of_date 21:00 UTC ≈ US close anchor
                # used elsewhere in the codebase.
                dt.datetime.combine(
                    target_date, dt.time(21, 0),
                    tzinfo=dt.timezone.utc,
                ).isoformat()
            ),
            "as_of_date": target_date.isoformat(),
            "portfolio_id": r.get("portfolio_id"),
            "portfolio_name": pf_by_id.get(r.get("portfolio_id")),
            "expected_fill_rule": "next_bar",
            "current_status": "pending_next_bar",
            "reason": "waiting for price_bar after submitted_at",
            "latest_price_bar_ts": (
                latest_ts.isoformat() if latest_ts else None
            ),
            "next_expected_bar_date": next_bar_date.isoformat(),
            "raw_exec_reason": (
                (r.get("detail") or {}).get("exec_reason")
            ),
        })

    return {
        "as_of_date": target_date.isoformat(),
        "next_expected_bar_date": next_bar_date.isoformat(),
        "count": len(items),
        "items": items,
        "notice": (
            "Pending next-bar fills. NOT executed trades. "
            "These will fill once a price_bar is ingested with "
            "ts > submitted_at."
        ),
    }


# ---------------------------------------------------------------------------
# /performance/paper/daily-suggestions
# ---------------------------------------------------------------------------
# Always-on ranked daily suggestions, even when zero trades execute.
# Pure read of `candidate_idea`, `recommendation`, paper_trade, and
# the skip JSONL. NO writes. NO trade execution.
#
# Suggestion statuses (vocabulary frozen):
#   * trade_ready          — accepted, action=Buy, would-execute when
#                            next-bar arrives (no pending JSONL row)
#   * pending_next_bar     — accepted, action=Buy, AND a JSONL skip row
#                            for fill-window currently exists
#   * watchlist_candidate  — accepted, action!=Buy (e.g. "Hold")
#   * blocked_by_gate      — rejected by an eligibility gate (regime,
#                            below_long_trend, extended, etc.)
#   * data_blocked         — rejected by a data-availability gate
#                            (insufficient_history, stale_data,
#                            execution_failure)

_SUGGESTION_STATUSES = (
    "trade_ready", "pending_next_bar", "watchlist_candidate",
    "blocked_by_gate", "data_blocked",
)
# Soft gates that exploratory mode can convert from rejection to a
# score penalty. Strict mode treats them as hard rejects.
_SOFT_GATES_RELAXABLE = (
    "extended_from_sma200", "idiosyncratic_vol_high",
    "topn_overflow", "high_vol_topn_overflow",
    "below_long_trend",
)
# Hard rejects — never relaxable. Mirror of the safety constraints
# the user listed for exploratory mode.
_HARD_GATES = (
    "regime_off", "insufficient_history", "stale_data",
    "liquidity_fail", "earnings_too_close",
    "duplicate_holding", "portfolio_full",
    "execution_failure",          # missing-price / no next bar
    "not_in_universe",
    "already_at_cap",
)
# Per-spec exploratory caps (additive — never relax strict).
_EXPL_MAX_BUYS_PER_DAY = 5
_EXPL_MAX_POSITION_PCT = 0.03


def _classify_status(status: str, action: str | None,
                     rejection_reason: str | None,
                     pending_asset_ids: set[str], asset_id: str,
                     ) -> str:
    """Map (status, action, rejection_reason) → suggestion status."""
    if status == "accepted":
        if action == "Buy":
            if asset_id in pending_asset_ids:
                return "pending_next_bar"
            return "trade_ready"
        return "watchlist_candidate"
    # rejected
    rr = rejection_reason or ""
    if rr in ("insufficient_history", "stale_data", "execution_failure"):
        return "data_blocked"
    return "blocked_by_gate"


def _next_step(suggestion_status: str, blocking_reason: str | None) -> str:
    if suggestion_status == "pending_next_bar":
        return "Wait for next trading-day price_bar; existing decision will fill."
    if suggestion_status == "trade_ready":
        return "Next safe-runner pass will submit through normal execution path."
    if suggestion_status == "watchlist_candidate":
        return "Monitor — engine emitted Hold action; no Buy decision."
    if suggestion_status == "data_blocked":
        return "Wait for ingest_prices_daily / compute_factor_snapshots to refresh."
    return f"Strict gate active: {blocking_reason or 'unknown'}; review eligibility."


def _pending_asset_ids_from_jsonl(target_date: dt.date) -> set[str]:
    """Read the per-day skip JSONL to find assets currently pending
    next-bar fill. Returns empty set if file missing or unreadable."""
    import json
    from pathlib import Path
    path = Path(_SKIPS_DIR) / f"{target_date.isoformat()}.jsonl"
    if not path.exists():
        return set()
    pending: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("reason") != _PENDING_FILL_REASON:
            continue
        detail = row.get("detail") or {}
        if _PENDING_FILL_MARKER.lower() in (
            detail.get("exec_reason") or ""
        ).lower():
            aid = row.get("asset_id")
            if aid:
                pending.add(aid)
    return pending


@router.get("/daily-suggestions")
def daily_suggestions(
    db: Session = Depends(get_session),
    as_of: str | None = Query(
        None, description="ISO date; defaults to latest candidate_idea date.",
    ),
    limit: int = Query(25, ge=1, le=200),
    mode: str = Query(
        "strict",
        description="strict (default) | exploratory — exploratory "
                    "ranks soft-gate rejects with a score penalty so "
                    "they appear alongside accepted candidates.",
    ),
) -> dict[str, Any]:
    """Ranked daily suggestions surfaced even when zero trades execute.

    Read-only. Does NOT write to any table. Does NOT execute trades.
    Exploratory mode here is a *visibility* mode: relaxable soft gates
    move into the suggestion stream with a -0.10 score penalty so the
    operator can see what WOULD be considered if exploratory execution
    were enabled. Execution path itself is unchanged (strict by
    construction)."""
    if mode not in ("strict", "exploratory"):
        return {"error": "mode must be 'strict' or 'exploratory'"}

    # Resolve target date.
    if as_of is not None:
        try:
            target = dt.date.fromisoformat(as_of)
        except ValueError:
            return {"error": "as_of must be ISO date YYYY-MM-DD"}
    else:
        latest = db.execute(text(
            "SELECT max(as_of_date) FROM candidate_idea"
        )).scalar()
        if latest is None:
            return {
                "as_of_date": None, "mode": mode, "count": 0,
                "items": [], "notice": "No candidate_idea rows yet.",
            }
        target = latest

    pending_assets = _pending_asset_ids_from_jsonl(target)

    # Pull all candidate_idea rows for the date with composite score.
    rows = db.execute(text("""
        SELECT
          c.id              AS candidate_id,
          c.asset_id        AS asset_id,
          a.symbol          AS symbol,
          c.status          AS status,
          c.action          AS action,
          c.rejection_reason AS rejection_reason,
          c.composite_score AS composite_score,
          c.confidence      AS confidence
        FROM candidate_idea c
        JOIN asset a ON a.id = c.asset_id
        WHERE c.as_of_date = :d
    """), {"d": target}).mappings().all()

    if not rows:
        return {
            "as_of_date": target.isoformat(),
            "mode": mode,
            "count": 0,
            "items": [],
            "notice": f"No candidates for {target.isoformat()}.",
        }

    # Build ranked list. Score = composite_score (or 0). Exploratory
    # adds back rows that strict would hide as soft-gate rejects with
    # a transparent -0.10 penalty so they sort behind accepted rows.
    items: list[dict[str, Any]] = []
    for r in rows:
        score = (
            float(r["composite_score"])
            if r["composite_score"] is not None else 0.0
        )
        suggestion_status = _classify_status(
            r["status"], r["action"], r["rejection_reason"],
            pending_assets, r["asset_id"],
        )
        # In strict mode, hide accepted+Hold and accepted+Buy with
        # full score; show all rejects only at the tail. In exploratory
        # mode, soft-gate rejects get re-injected with a small penalty
        # so the operator sees them as relaxed candidates.
        relaxed = False
        relaxed_from: str | None = None
        if (mode == "exploratory"
                and r["status"] == "rejected"
                and (r["rejection_reason"] in _SOFT_GATES_RELAXABLE)):
            score = max(score, 0.0) - 0.10
            relaxed = True
            relaxed_from = r["rejection_reason"]
            # Promote display status — still labeled clearly.
            suggestion_status = "watchlist_candidate"
        items.append({
            "symbol": r["symbol"],
            "asset_id": r["asset_id"],
            "action": r["action"],
            "suggestion_status": suggestion_status,
            "score": round(score, 6),
            "confidence": (
                float(r["confidence"])
                if r["confidence"] is not None else None
            ),
            "reason_summary": r["rejection_reason"] or "accepted",
            "blocking_reason": (
                r["rejection_reason"]
                if r["status"] == "rejected" else None
            ),
            "execution_status": (
                "pending_next_bar"
                if r["asset_id"] in pending_assets
                else r["status"]
            ),
            "next_step": _next_step(
                suggestion_status, r["rejection_reason"],
            ),
            "mode": mode,
            "relaxed_in_exploratory": relaxed,
            "relaxed_from": relaxed_from,
        })

    # Sort by score desc, tiebreak by symbol asc.
    items.sort(key=lambda x: (-x["score"], x["symbol"]))
    # Assign ranks AFTER sort.
    for i, it in enumerate(items, 1):
        it["rank"] = i

    # Always include pending + accepted Buys near the top regardless
    # of strict/exploratory: count them.
    counts = {
        s: sum(1 for it in items if it["suggestion_status"] == s)
        for s in _SUGGESTION_STATUSES
    }

    return {
        "as_of_date": target.isoformat(),
        "mode": mode,
        "count": min(limit, len(items)),
        "total_evaluated": len(items),
        "status_counts": counts,
        "items": items[:limit],
        "vocabulary": list(_SUGGESTION_STATUSES),
        "soft_gates_relaxable_in_exploratory": list(_SOFT_GATES_RELAXABLE),
        "hard_gates_never_relaxed": list(_HARD_GATES),
        "exploratory_caps": {
            "max_buys_per_day": _EXPL_MAX_BUYS_PER_DAY,
            "max_position_pct": _EXPL_MAX_POSITION_PCT,
        },
        "notice": (
            "Daily suggestions — read-only ranking. Strict mode is the "
            "default. Exploratory mode is a VISIBILITY toggle here; "
            "execution path remains strict in this phase."
        ),
    }


# ---------------------------------------------------------------------------
# /performance/paper/suggestion-quality
# ---------------------------------------------------------------------------
# Forward-return scoring of past daily suggestions. Pure read of
# `candidate_idea` + `price_bar`. NO writes. No outcome row inserts.
# Distinct from `recommendation_outcome` labels — this surface lets
# the operator see "was the suggestion actually good after 5d" without
# requiring the labeler job to fire.

_QUALITY_HORIZONS = (1, 3, 5, 10, 20)
# Outcome thresholds. Symmetric, conservative defaults — never tuned
# to make ML look better.
_QUALITY_GOOD_PCT = 0.02   # +2% over horizon → good
_QUALITY_BAD_PCT = -0.02   # -2% over horizon → bad


def _label_quality(fwd_return: float | None,
                   bars_seen: int, horizon: int) -> str:
    if fwd_return is None:
        return "pending" if bars_seen < horizon else "data_blocked"
    if bars_seen < horizon:
        # Some bars exist but not enough — still pending; never label
        # half-window as final.
        return "pending"
    if fwd_return >= _QUALITY_GOOD_PCT:
        return "good"
    if fwd_return <= _QUALITY_BAD_PCT:
        return "bad"
    return "neutral"


@router.get("/suggestion-quality")
def suggestion_quality(
    db: Session = Depends(get_session),
    as_of: str | None = Query(
        None, description="ISO date; defaults to latest candidate_idea.",
    ),
    horizon: str = Query(
        "5D",
        description="Horizon: 1D / 3D / 5D / 10D / 20D.",
    ),
    mode: str = Query(
        "strict",
        description="strict (default) | exploratory — exploratory "
                    "includes soft-gate rejects in the population.",
    ),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    """Read-only forward-return scoring of past daily suggestions.

    For each candidate_idea row on `as_of`, walk forward `horizon`
    trading days using `price_bar.close` (with `adjusted_close`
    fallback). Compute forward_return_pct, MFE, MAE, then label:
        good     forward_return >= +2%
        bad      forward_return <= -2%
        neutral  between thresholds
        pending  fewer than `horizon` future bars yet
        data_blocked  no entry price OR no forward window
    """
    # Parse horizon.
    if not horizon.upper().endswith("D") or not horizon[:-1].isdigit():
        return {"error": "horizon must be like '5D' (1D/3D/5D/10D/20D)"}
    h = int(horizon[:-1])
    if h not in _QUALITY_HORIZONS:
        return {
            "error": f"horizon {horizon} not supported; "
                     f"allowed: {_QUALITY_HORIZONS}",
        }
    if mode not in ("strict", "exploratory"):
        return {"error": "mode must be 'strict' or 'exploratory'"}

    # Resolve target date.
    if as_of is not None:
        try:
            target = dt.date.fromisoformat(as_of)
        except ValueError:
            return {"error": "as_of must be ISO date YYYY-MM-DD"}
    else:
        latest = db.execute(text(
            "SELECT max(as_of_date) FROM candidate_idea"
        )).scalar()
        if latest is None:
            return {
                "as_of_date": None, "horizon": horizon, "mode": mode,
                "summary": {}, "items": [],
                "notice": "No candidate_idea rows yet.",
            }
        target = latest

    # Pull candidate population. Strict: only accepted Buys. Exploratory:
    # also include rejected-by-soft-gate rows (those would execute under
    # exploratory). Drops hard-rejected always.
    soft_gates = list(_SOFT_GATES_RELAXABLE)
    if mode == "strict":
        cand_rows = db.execute(text("""
            SELECT
              c.asset_id, a.symbol,
              c.status, c.action, c.rejection_reason,
              c.composite_score
            FROM candidate_idea c
            JOIN asset a ON a.id = c.asset_id
            WHERE c.as_of_date = :d
              AND c.status = 'accepted'
        """), {"d": target}).mappings().all()
    else:
        cand_rows = db.execute(text("""
            SELECT
              c.asset_id, a.symbol,
              c.status, c.action, c.rejection_reason,
              c.composite_score
            FROM candidate_idea c
            JOIN asset a ON a.id = c.asset_id
            WHERE c.as_of_date = :d
              AND (
                c.status = 'accepted'
                OR (c.status = 'rejected'
                    AND c.rejection_reason = ANY(:soft))
              )
        """), {"d": target, "soft": soft_gates}).mappings().all()

    if not cand_rows:
        return {
            "as_of_date": target.isoformat(),
            "horizon": horizon, "mode": mode,
            "summary": _empty_quality_summary(),
            "items": [],
        }

    asset_ids = [r["asset_id"] for r in cand_rows]

    # Pull entry-day close + horizon-forward bars in one batch per asset.
    # Use the close of the bar whose ts::date == target (entry reference).
    # Forward window = next h trading-day bars after target.
    bars_rows = db.execute(text("""
        SELECT asset_id, ts::date AS bar_date,
               coalesce(adjusted_close, close)::float AS px,
               low::float AS lo, high::float AS hi
        FROM price_bar
        WHERE asset_id = ANY(:ids)
          AND timeframe = '1d'
          AND ts::date >= :d
        ORDER BY asset_id, ts ASC
    """), {"ids": asset_ids, "d": target}).all()
    bars_by_asset: dict[str, list[tuple[dt.date, float, float, float]]] = {}
    for asset_id, bar_date, px, lo, hi in bars_rows:
        bars_by_asset.setdefault(asset_id, []).append(
            (bar_date, px, lo, hi)
        )

    items: list[dict[str, Any]] = []
    for r in cand_rows:
        aid = r["asset_id"]
        bars = bars_by_asset.get(aid, [])
        if not bars or bars[0][0] != target:
            # No bar on the target date — entry reference unavailable.
            items.append({
                "symbol": r["symbol"],
                "asset_id": aid,
                "rank": None,
                "suggestion_status": (
                    "watchlist_candidate" if r["action"] != "Buy"
                    else "trade_ready"
                ),
                "score": (
                    float(r["composite_score"])
                    if r["composite_score"] is not None else 0.0
                ),
                "action": r["action"],
                "rejection_reason": r["rejection_reason"],
                "as_of_date": target.isoformat(),
                "horizon": horizon,
                "entry_reference_price": None,
                "exit_reference_price": None,
                "forward_return_pct": None,
                "mfe_pct": None,
                "mae_pct": None,
                "outcome_label": "data_blocked",
            })
            continue

        entry_price = bars[0][1]
        # Forward bars strictly after the as_of bar.
        forward = bars[1:]
        bars_seen = len(forward)
        if entry_price <= 0:
            items.append({
                "symbol": r["symbol"], "asset_id": aid, "rank": None,
                "suggestion_status": (
                    "watchlist_candidate" if r["action"] != "Buy"
                    else "trade_ready"
                ),
                "score": (
                    float(r["composite_score"])
                    if r["composite_score"] is not None else 0.0
                ),
                "action": r["action"],
                "rejection_reason": r["rejection_reason"],
                "as_of_date": target.isoformat(),
                "horizon": horizon,
                "entry_reference_price": None,
                "exit_reference_price": None,
                "forward_return_pct": None, "mfe_pct": None, "mae_pct": None,
                "outcome_label": "data_blocked",
            })
            continue

        # Trim forward window to horizon bars max.
        window = forward[:h]
        if window:
            highs = [b[3] for b in window]
            lows = [b[2] for b in window]
            mfe = max(highs) / entry_price - 1.0 if highs else None
            mae = min(lows) / entry_price - 1.0 if lows else None
        else:
            mfe = mae = None

        if len(forward) < h:
            forward_return = None
            exit_price = None
        else:
            exit_price = window[-1][1]
            forward_return = exit_price / entry_price - 1.0

        outcome_label = _label_quality(forward_return, len(forward), h)
        # Soft-gate rejected rows render as watchlist_candidate so the
        # mode-by-mode summary stays comparable.
        if r["status"] == "accepted" and r["action"] == "Buy":
            sug_status = "trade_ready"
        elif r["status"] == "accepted":
            sug_status = "watchlist_candidate"
        else:
            sug_status = "watchlist_candidate"

        items.append({
            "symbol": r["symbol"],
            "asset_id": aid,
            "rank": None,
            "suggestion_status": sug_status,
            "score": (
                float(r["composite_score"])
                if r["composite_score"] is not None else 0.0
            ),
            "action": r["action"],
            "rejection_reason": r["rejection_reason"],
            "as_of_date": target.isoformat(),
            "horizon": horizon,
            "entry_reference_price": float(entry_price),
            "exit_reference_price": (
                float(exit_price) if exit_price is not None else None
            ),
            "forward_return_pct": (
                float(forward_return) if forward_return is not None else None
            ),
            "mfe_pct": float(mfe) if mfe is not None else None,
            "mae_pct": float(mae) if mae is not None else None,
            "outcome_label": outcome_label,
        })

    # Rank by composite_score desc, tiebreak by symbol.
    items.sort(key=lambda x: (-x["score"], x["symbol"]))
    for i, it in enumerate(items, 1):
        it["rank"] = i

    # Summary.
    summary = _quality_summary(items)
    # Best / worst over rows with a forward_return.
    finalized = [it for it in items if it["forward_return_pct"] is not None]
    finalized.sort(
        key=lambda it: it["forward_return_pct"] or 0.0, reverse=True,
    )
    best = finalized[0] if finalized else None
    worst = finalized[-1] if finalized else None

    # Aggregations by suggestion_status and by blocking_reason.
    by_status: dict[str, dict[str, Any]] = {}
    for it in items:
        bucket = by_status.setdefault(
            it["suggestion_status"],
            {"n": 0, "n_finalized": 0, "sum_return": 0.0,
             "good": 0, "bad": 0, "neutral": 0,
             "pending": 0, "data_blocked": 0},
        )
        bucket["n"] += 1
        bucket[it["outcome_label"]] += 1
        if it["forward_return_pct"] is not None:
            bucket["n_finalized"] += 1
            bucket["sum_return"] += it["forward_return_pct"]
    for s, b in by_status.items():
        b["avg_forward_return_pct"] = (
            b["sum_return"] / b["n_finalized"]
            if b["n_finalized"] > 0 else None
        )

    by_reason: dict[str, dict[str, Any]] = {}
    for it in items:
        rr = it.get("rejection_reason") or "accepted"
        bucket = by_reason.setdefault(
            rr, {"n": 0, "n_finalized": 0, "sum_return": 0.0}
        )
        bucket["n"] += 1
        if it["forward_return_pct"] is not None:
            bucket["n_finalized"] += 1
            bucket["sum_return"] += it["forward_return_pct"]
    for rr, b in by_reason.items():
        b["avg_forward_return_pct"] = (
            b["sum_return"] / b["n_finalized"]
            if b["n_finalized"] > 0 else None
        )

    return {
        "as_of_date": target.isoformat(),
        "horizon": horizon,
        "mode": mode,
        "horizons_supported": list(_QUALITY_HORIZONS),
        "thresholds": {
            "good_pct": _QUALITY_GOOD_PCT,
            "bad_pct": _QUALITY_BAD_PCT,
        },
        "summary": summary,
        "best": (
            {"symbol": best["symbol"],
             "forward_return_pct": best["forward_return_pct"],
             "outcome_label": best["outcome_label"]}
            if best else None
        ),
        "worst": (
            {"symbol": worst["symbol"],
             "forward_return_pct": worst["forward_return_pct"],
             "outcome_label": worst["outcome_label"]}
            if worst else None
        ),
        "by_status": by_status,
        "by_blocking_reason": by_reason,
        "items": items[:limit],
        "notice": (
            "Forward-return labeling is read-only. Uses only future "
            "price_bar rows after as_of. Same-bar labeling is "
            "explicitly prevented; entry uses target-day close, exit "
            "uses target+h close. No outcome rows inserted."
        ),
    }


def _empty_quality_summary() -> dict[str, Any]:
    return {
        "total": 0, "good": 0, "neutral": 0, "bad": 0,
        "pending": 0, "data_blocked": 0,
        "n_finalized": 0,
        "hit_rate": None,
        "avg_forward_return_pct": None,
        "avg_mfe_pct": None,
        "avg_mae_pct": None,
    }


def _quality_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    s = _empty_quality_summary()
    s["total"] = len(items)
    finalized: list[dict[str, Any]] = []
    for it in items:
        s[it["outcome_label"]] = s.get(it["outcome_label"], 0) + 1
        if it["forward_return_pct"] is not None:
            finalized.append(it)
    s["n_finalized"] = len(finalized)
    if finalized:
        s["avg_forward_return_pct"] = (
            sum(it["forward_return_pct"] for it in finalized)
            / len(finalized)
        )
        s["avg_mfe_pct"] = (
            sum(it["mfe_pct"] for it in finalized
                if it["mfe_pct"] is not None)
            / sum(1 for it in finalized if it["mfe_pct"] is not None)
            if any(it["mfe_pct"] is not None for it in finalized) else None
        )
        s["avg_mae_pct"] = (
            sum(it["mae_pct"] for it in finalized
                if it["mae_pct"] is not None)
            / sum(1 for it in finalized if it["mae_pct"] is not None)
            if any(it["mae_pct"] is not None for it in finalized) else None
        )
        good = sum(1 for it in finalized if it["outcome_label"] == "good")
        s["hit_rate"] = good / len(finalized)
    return s


# ---------------------------------------------------------------------------
# /performance/options/daily-suggestions
# ---------------------------------------------------------------------------
# Read-only options shadow suggestions derived from
# `options_chain_snapshot` joined with the latest stock
# `candidate_idea` signal per underlying. Pure read. NO writes. NO
# `options_paper_trade` inserts. Liquidity filters mirror the existing
# `OPTIONS_SHADOW_*` thresholds.

# Liquidity thresholds — mirror the spec on shadow_evaluator without
# importing settings (keeps the endpoint module-light). If the
# evaluator later tightens these, both surfaces should move together.
_OPT_MIN_BID = 0.05
_OPT_MAX_RELATIVE_SPREAD = 0.20
_OPT_MIN_OPEN_INTEREST = 100
_OPT_MAX_QUOTE_AGE_SECONDS = 600

# Signal-to-options mapping thresholds.
_OPT_SIGNAL_BULLISH = 0.30   # composite_score >= → call candidates
_OPT_SIGNAL_BEARISH = -0.30  # composite_score <= → put candidates
_OPT_HIGH_IV_THRESHOLD = 0.45  # IV >= → volatility_play tag

_OPT_SUGGESTION_TYPES = (
    "directional_call",
    "directional_put",
    "volatility_play",
    "spread_candidate",
)
_OPT_STATUSES = (
    "shadow_candidate", "liquidity_blocked", "data_blocked",
)


def _opt_liquidity_score(bid, ask, mid, oi, quote_age) -> tuple[float, list[str]]:
    """Returns (0..1 score, list of failure reasons). Empty list = pass."""
    fails: list[str] = []
    bid_f = float(bid) if bid is not None else 0.0
    ask_f = float(ask) if ask is not None else 0.0
    mid_f = float(mid) if mid is not None else (
        (bid_f + ask_f) / 2.0 if (bid_f + ask_f) > 0 else 0.0
    )
    oi_i = int(oi) if oi is not None else 0
    age = int(quote_age) if quote_age is not None else 999_999

    if bid_f < _OPT_MIN_BID:
        fails.append("bid_below_floor")
    if ask_f <= bid_f:
        fails.append("ask_le_bid")
    rel = ((ask_f - bid_f) / mid_f) if mid_f > 0 else 1.0
    if rel > _OPT_MAX_RELATIVE_SPREAD:
        fails.append("spread_too_wide")
    if oi_i < _OPT_MIN_OPEN_INTEREST:
        fails.append("oi_below_floor")
    if age > _OPT_MAX_QUOTE_AGE_SECONDS:
        fails.append("quote_too_stale")

    # Score components (0..1):
    spread_score = max(0.0, 1.0 - (rel / _OPT_MAX_RELATIVE_SPREAD))
    oi_score = min(1.0, oi_i / max(1, _OPT_MIN_OPEN_INTEREST * 5))
    age_score = max(0.0, 1.0 - (age / _OPT_MAX_QUOTE_AGE_SECONDS))
    score = (spread_score * 0.5 + oi_score * 0.3 + age_score * 0.2)
    return round(score, 4), fails


def _classify_suggestion(
    option_type: str, signal_score: float | None, iv: float | None,
) -> str:
    """Map (option_type, stock signal, IV) → suggestion_type."""
    high_iv = iv is not None and iv >= _OPT_HIGH_IV_THRESHOLD
    if signal_score is not None:
        if option_type == "CALL" and signal_score >= _OPT_SIGNAL_BULLISH:
            return "directional_call"
        if option_type == "PUT" and signal_score <= _OPT_SIGNAL_BEARISH:
            return "directional_put"
    if high_iv:
        return "volatility_play"
    return "spread_candidate"


@options_router.get("/daily-suggestions")
def options_daily_suggestions(
    db: Session = Depends(get_session),
    as_of: str | None = Query(
        None,
        description="ISO date for the stock signal source. Defaults "
                    "to latest candidate_idea date.",
    ),
    limit: int = Query(50, ge=1, le=500),
    underlying: str | None = Query(
        None, description="Optional filter to one underlying."
    ),
) -> dict[str, Any]:
    """Read-only options shadow suggestions joined to stock signals.

    Source surfaces:
      * `options_chain_snapshot` — latest row per (underlying, expiry,
        strike, option_type) at most 24h old.
      * `candidate_idea` — latest stock signal for the corresponding
        underlying on `as_of`.

    Liquidity gates are applied; failures land in
    `status="liquidity_blocked"` so the operator sees them but they
    are not ranked into the shadow candidate set.
    """
    if as_of is not None:
        try:
            target = dt.date.fromisoformat(as_of)
        except ValueError:
            return {"error": "as_of must be ISO date YYYY-MM-DD"}
    else:
        latest = db.execute(text(
            "SELECT max(as_of_date) FROM candidate_idea"
        )).scalar()
        target = latest

    # Pull latest snapshot per (underlying, expiry, strike, option_type)
    # by taking the most recent snapshot_at_utc for each natural key.
    chain_rows = db.execute(text(f"""
        WITH latest AS (
            SELECT DISTINCT ON (underlying, expiry, strike, option_type)
                   underlying, expiry, strike, option_type,
                   option_symbol, bid, ask, mid, last,
                   volume, open_interest, delta, gamma, theta,
                   vega, iv, quote_age_seconds, snapshot_at_utc
            FROM options_chain_snapshot
            { "WHERE underlying = :u" if underlying else "" }
            ORDER BY underlying, expiry, strike, option_type,
                     snapshot_at_utc DESC
        )
        SELECT * FROM latest
        ORDER BY underlying, expiry, strike, option_type
    """), {"u": underlying} if underlying else {}).mappings().all()

    if not chain_rows:
        return {
            "as_of_date": target.isoformat() if target else None,
            "count": 0, "items": [],
            "reviewed_contracts": 0,
            "underlyings_covered": [],
            "notice": "No options_chain_snapshot rows yet.",
        }

    # Pull latest stock signal per underlying for `target`.
    underlyings = list({r["underlying"] for r in chain_rows})
    sig_rows = db.execute(text("""
        SELECT a.symbol AS underlying,
               c.composite_score AS score,
               c.status, c.action, c.rejection_reason
        FROM candidate_idea c
        JOIN asset a ON a.id = c.asset_id
        WHERE c.as_of_date = :d
          AND a.symbol = ANY(:syms)
    """), {"d": target, "syms": underlyings}).mappings().all()
    signal_by_underlying = {
        r["underlying"]: {
            "score": (
                float(r["score"]) if r["score"] is not None else None
            ),
            "status": r["status"],
            "action": r["action"],
            "rejection_reason": r["rejection_reason"],
        }
        for r in sig_rows
    }

    items: list[dict[str, Any]] = []
    liquidity_pass = 0
    liquidity_block = 0
    data_block = 0

    for r in chain_rows:
        underlying = r["underlying"]
        sig = signal_by_underlying.get(underlying)
        signal_score = sig["score"] if sig else None
        iv = float(r["iv"]) if r["iv"] is not None else None
        liq_score, liq_fails = _opt_liquidity_score(
            r["bid"], r["ask"], r["mid"],
            r["open_interest"], r["quote_age_seconds"],
        )
        if liq_fails:
            status = "liquidity_blocked"
            liquidity_block += 1
        elif sig is None:
            status = "data_blocked"
            data_block += 1
        else:
            status = "shadow_candidate"
            liquidity_pass += 1

        suggestion_type = _classify_suggestion(
            r["option_type"], signal_score, iv,
        )

        # Composite rank = liq * 0.4 + signal_alignment * 0.4 + iv_ctx * 0.2
        signal_alignment = 0.0
        if signal_score is not None:
            if r["option_type"] == "CALL" and signal_score > 0:
                signal_alignment = min(1.0, signal_score)
            elif r["option_type"] == "PUT" and signal_score < 0:
                signal_alignment = min(1.0, -signal_score)
        iv_ctx = 0.5
        if iv is not None:
            iv_ctx = 1.0 if iv >= _OPT_HIGH_IV_THRESHOLD else 0.5
        composite = (
            liq_score * 0.4
            + signal_alignment * 0.4
            + iv_ctx * 0.2
        )

        ask_f = float(r["ask"]) if r["ask"] is not None else None
        bid_f = float(r["bid"]) if r["bid"] is not None else None
        mid_f = float(r["mid"]) if r["mid"] is not None else None
        spread = (
            (ask_f - bid_f)
            if (ask_f is not None and bid_f is not None) else None
        )

        items.append({
            "underlying": underlying,
            "option_symbol": r["option_symbol"],
            "expiry": (
                r["expiry"].isoformat() if r["expiry"] else None
            ),
            "strike": float(r["strike"]) if r["strike"] is not None else None,
            "option_type": r["option_type"],
            "bid": bid_f, "ask": ask_f, "mid": mid_f,
            "spread": spread,
            "iv": iv,
            "open_interest": (
                int(r["open_interest"])
                if r["open_interest"] is not None else None
            ),
            "volume": (
                int(r["volume"]) if r["volume"] is not None else None
            ),
            "delta": (
                float(r["delta"]) if r["delta"] is not None else None
            ),
            "quote_age_seconds": int(r["quote_age_seconds"] or 0),
            "liquidity_score": liq_score,
            "liquidity_failures": liq_fails,
            "stock_signal": sig,
            "suggestion_type": suggestion_type,
            "status": status,
            "composite_rank_score": round(composite, 4),
        })

    items.sort(
        key=lambda it: (-it["composite_rank_score"],
                        it["underlying"], it["option_symbol"])
    )
    for i, it in enumerate(items, 1):
        it["rank"] = i

    # Aggregations
    by_underlying: dict[str, dict[str, int]] = {}
    by_type: dict[str, int] = {}
    for it in items:
        u = by_underlying.setdefault(
            it["underlying"], {"shadow_candidate": 0,
                                "liquidity_blocked": 0,
                                "data_blocked": 0, "total": 0},
        )
        u[it["status"]] += 1
        u["total"] += 1
        by_type[it["suggestion_type"]] = (
            by_type.get(it["suggestion_type"], 0) + 1
        )

    pass_rate = (
        liquidity_pass / len(items) if items else None
    )

    return {
        "as_of_date": target.isoformat() if target else None,
        "reviewed_contracts": len(items),
        "underlyings_covered": sorted(set(by_underlying.keys())),
        "count": min(limit, len(items)),
        "items": items[:limit],
        "summary": {
            "total": len(items),
            "shadow_candidate": liquidity_pass,
            "liquidity_blocked": liquidity_block,
            "data_blocked": data_block,
            "liquidity_pass_rate": pass_rate,
        },
        "by_underlying": by_underlying,
        "by_suggestion_type": by_type,
        "vocabulary": {
            "statuses": list(_OPT_STATUSES),
            "suggestion_types": list(_OPT_SUGGESTION_TYPES),
        },
        "thresholds": {
            "min_bid": _OPT_MIN_BID,
            "max_relative_spread": _OPT_MAX_RELATIVE_SPREAD,
            "min_open_interest": _OPT_MIN_OPEN_INTEREST,
            "max_quote_age_seconds": _OPT_MAX_QUOTE_AGE_SECONDS,
            "signal_bullish": _OPT_SIGNAL_BULLISH,
            "signal_bearish": _OPT_SIGNAL_BEARISH,
            "high_iv_threshold": _OPT_HIGH_IV_THRESHOLD,
        },
        "notice": (
            "Shadow-only diagnostics. NO options_paper_trade rows. "
            "NO live execution. Suggestion types are advisory; "
            "execution remains gated."
        ),
    }


# ---------------------------------------------------------------------------
# /performance/options/strategy-suggestions
# ---------------------------------------------------------------------------
# Strategy engine — maps stock signal + IV context → structured options
# strategy. Pure read of `options_chain_snapshot` + `candidate_idea` +
# `price_bar`. NO writes. NO `options_paper_trade` inserts. NO live
# execution path. Strategy vocabulary frozen.

_STRATEGY_NAMES = (
    "long_call", "long_put",
    "bull_call_spread", "bear_put_spread",
    "put_credit_spread", "call_credit_spread",
    "iron_condor",
)
# IV bucketing — never invents IV. Falls back to directional-only when
# IV missing.
_IV_LOW = 0.25
_IV_HIGH = 0.45
# OTM strike distance for spread legs. Conservative defaults.
_SPREAD_MIN_PCT = 0.03   # at least 3% from ATM
_SPREAD_MAX_PCT = 0.10   # at most 10% from ATM


def _iv_bucket(iv: float | None) -> str | None:
    if iv is None:
        return None
    if iv < _IV_LOW:
        return "low"
    if iv > _IV_HIGH:
        return "high"
    return "medium"


def _direction_from_score(score: float | None) -> str:
    """Strong Buy / Strong Sell / Neutral. Mirrors the same 0.30
    bullish / -0.30 bearish thresholds used in the daily-suggestions
    endpoint so directional treatment is consistent."""
    if score is None:
        return "neutral"
    if score >= _OPT_SIGNAL_BULLISH:
        return "strong_buy"
    if score <= _OPT_SIGNAL_BEARISH:
        return "strong_sell"
    return "neutral"


def _trend_from_regime(regime: dict[str, Any] | None) -> str:
    if not regime:
        return "unknown"
    mt = regime.get("market_trend") or "unknown"
    if mt in ("uptrend", "sideways", "downtrend"):
        return mt
    return "unknown"


def _pick_strategy(direction: str, iv_bucket: str | None,
                   trend: str) -> str | None:
    """Strategy mapping per spec. Returns None when no clean match.

    Directional path takes precedence over volatility play; sideways
    overlay only triggers when direction is neutral."""
    if direction == "strong_buy":
        if iv_bucket == "low":
            return "long_call"
        if iv_bucket == "medium":
            return "bull_call_spread"
        if iv_bucket == "high":
            return "put_credit_spread"
        return "long_call"  # IV missing → directional only
    if direction == "strong_sell":
        if iv_bucket == "low":
            return "long_put"
        if iv_bucket == "medium":
            return "bear_put_spread"
        if iv_bucket == "high":
            return "call_credit_spread"
        return "long_put"
    # neutral direction
    if trend == "sideways" and iv_bucket == "high":
        return "iron_condor"
    return None


def _select_atm(chain: list[dict[str, Any]], spot: float,
                option_type: str) -> dict[str, Any] | None:
    """Closest strike to spot for the given option_type."""
    candidates = [c for c in chain if c["option_type"] == option_type]
    if not candidates:
        return None
    return min(candidates, key=lambda c: abs(c["strike"] - spot))


def _select_otm(chain: list[dict[str, Any]], spot: float,
                option_type: str, *, above: bool) -> dict[str, Any] | None:
    """OTM leg within `[_SPREAD_MIN_PCT, _SPREAD_MAX_PCT]` distance.
    `above=True` for OTM call, False for OTM put."""
    if spot <= 0:
        return None
    lo = spot * (1 + _SPREAD_MIN_PCT) if above else spot * (1 - _SPREAD_MAX_PCT)
    hi = spot * (1 + _SPREAD_MAX_PCT) if above else spot * (1 - _SPREAD_MIN_PCT)
    candidates = [
        c for c in chain
        if c["option_type"] == option_type
        and lo <= c["strike"] <= hi
    ]
    if not candidates:
        return None
    # Pick the strike closest to the midpoint of the band.
    mid = (lo + hi) / 2
    return min(candidates, key=lambda c: abs(c["strike"] - mid))


def _build_legs(strategy: str, chain: list[dict[str, Any]],
                spot: float) -> list[dict[str, Any]] | None:
    """Pick contract legs for the strategy. Returns None if any
    required leg is unavailable in the chain."""
    if strategy == "long_call":
        leg = _select_atm(chain, spot, "CALL")
        return [_leg_dict(leg, "buy")] if leg else None
    if strategy == "long_put":
        leg = _select_atm(chain, spot, "PUT")
        return [_leg_dict(leg, "buy")] if leg else None
    if strategy == "bull_call_spread":
        buy = _select_atm(chain, spot, "CALL")
        sell = _select_otm(chain, spot, "CALL", above=True)
        if not buy or not sell or buy["strike"] >= sell["strike"]:
            return None
        return [_leg_dict(buy, "buy"), _leg_dict(sell, "sell")]
    if strategy == "bear_put_spread":
        buy = _select_atm(chain, spot, "PUT")
        sell = _select_otm(chain, spot, "PUT", above=False)
        if not buy or not sell or sell["strike"] >= buy["strike"]:
            return None
        return [_leg_dict(buy, "buy"), _leg_dict(sell, "sell")]
    if strategy == "put_credit_spread":
        sell = _select_otm(chain, spot, "PUT", above=False)
        # Buy a further OTM put for protection (closer to lo edge of band).
        further = [
            c for c in chain
            if c["option_type"] == "PUT"
            and c["strike"] < (sell["strike"] if sell else spot)
        ]
        if not sell or not further:
            return None
        buy = max(further, key=lambda c: c["strike"])
        return [_leg_dict(sell, "sell"), _leg_dict(buy, "buy")]
    if strategy == "call_credit_spread":
        sell = _select_otm(chain, spot, "CALL", above=True)
        further = [
            c for c in chain
            if c["option_type"] == "CALL"
            and c["strike"] > (sell["strike"] if sell else spot)
        ]
        if not sell or not further:
            return None
        buy = min(further, key=lambda c: c["strike"])
        return [_leg_dict(sell, "sell"), _leg_dict(buy, "buy")]
    if strategy == "iron_condor":
        # Two credit spreads bracketing spot.
        put_legs = _build_legs("put_credit_spread", chain, spot)
        call_legs = _build_legs("call_credit_spread", chain, spot)
        if not put_legs or not call_legs:
            return None
        return put_legs + call_legs
    return None


def _leg_dict(c: dict[str, Any], action: str) -> dict[str, Any]:
    return {
        "type": c["option_type"].lower(),
        "strike": c["strike"],
        "action": action,
        "option_symbol": c["option_symbol"],
        "expiry": c["expiry"].isoformat() if c["expiry"] else None,
        "bid": c["bid"], "ask": c["ask"], "mid": c["mid"],
        "open_interest": c["open_interest"],
        "iv": c["iv"],
        "liquidity_score": c["liquidity_score"],
    }


def _aggregate_liquidity(legs: list[dict[str, Any]]) -> float:
    """Average per-leg liquidity score. Strategy is only as liquid
    as its weakest leg, so we use min instead — but expose mean too."""
    scores = [
        l["liquidity_score"] for l in legs
        if l.get("liquidity_score") is not None
    ]
    return min(scores) if scores else 0.0


def _aggregate_spread_pct(legs: list[dict[str, Any]]) -> float | None:
    """Worst (widest) relative spread across legs."""
    spreads = []
    for l in legs:
        b = l.get("bid"); a = l.get("ask"); m = l.get("mid")
        if b is None or a is None or m is None or m <= 0:
            continue
        spreads.append((a - b) / m)
    return max(spreads) if spreads else None


@options_router.get("/strategy-suggestions")
def options_strategy_suggestions(
    db: Session = Depends(get_session),
    as_of: str | None = Query(
        None,
        description="ISO date for stock signal source. Defaults to "
                    "latest candidate_idea.",
    ),
    limit: int = Query(25, ge=1, le=200),
) -> dict[str, Any]:
    """Read-only options strategy suggestions derived from stock
    signal + chain liquidity + IV context. NO writes. NO execution."""
    if as_of is not None:
        try:
            target = dt.date.fromisoformat(as_of)
        except ValueError:
            return {"error": "as_of must be ISO date YYYY-MM-DD"}
    else:
        latest = db.execute(text(
            "SELECT max(as_of_date) FROM candidate_idea"
        )).scalar()
        target = latest

    # Pull latest options chain per (underlying, expiry, strike, option_type)
    # with liquidity scores precomputed inline.
    chain_rows = db.execute(text("""
        WITH latest AS (
            SELECT DISTINCT ON (underlying, expiry, strike, option_type)
                   underlying, expiry, strike, option_type,
                   option_symbol, bid, ask, mid,
                   open_interest, volume, iv, delta,
                   quote_age_seconds, snapshot_at_utc
            FROM options_chain_snapshot
            ORDER BY underlying, expiry, strike, option_type,
                     snapshot_at_utc DESC
        )
        SELECT * FROM latest
        ORDER BY underlying, expiry, strike, option_type
    """)).mappings().all()

    if not chain_rows:
        return {
            "as_of_date": target.isoformat() if target else None,
            "count": 0, "items": [],
            "underlyings_used": [],
            "contracts_reviewed": 0,
            "notice": "No options_chain_snapshot rows yet.",
        }

    # Bucket chain by underlying, then by expiry. Score liquidity once.
    by_underlying: dict[str, dict[Any, list[dict[str, Any]]]] = {}
    contracts_reviewed = 0
    contracts_passed_liquidity = 0
    for r in chain_rows:
        contracts_reviewed += 1
        liq_score, liq_fails = _opt_liquidity_score(
            r["bid"], r["ask"], r["mid"],
            r["open_interest"], r["quote_age_seconds"],
        )
        if liq_fails:
            continue  # never feed liquidity-blocked legs into a strategy
        contracts_passed_liquidity += 1
        entry = {
            "underlying": r["underlying"],
            "expiry": r["expiry"],
            "strike": float(r["strike"]),
            "option_type": r["option_type"],
            "option_symbol": r["option_symbol"],
            "bid": float(r["bid"]) if r["bid"] is not None else None,
            "ask": float(r["ask"]) if r["ask"] is not None else None,
            "mid": float(r["mid"]) if r["mid"] is not None else None,
            "open_interest": (
                int(r["open_interest"])
                if r["open_interest"] is not None else None
            ),
            "volume": int(r["volume"]) if r["volume"] is not None else None,
            "iv": float(r["iv"]) if r["iv"] is not None else None,
            "delta": (
                float(r["delta"]) if r["delta"] is not None else None
            ),
            "liquidity_score": liq_score,
        }
        by_underlying.setdefault(r["underlying"], {}) \
            .setdefault(r["expiry"], []).append(entry)

    # Pull stock signal per underlying.
    underlyings = list(by_underlying.keys())
    sig_rows = db.execute(text("""
        SELECT a.symbol AS underlying,
               c.composite_score AS score,
               c.status, c.action, c.rejection_reason,
               c.regime_snapshot AS regime
        FROM candidate_idea c
        JOIN asset a ON a.id = c.asset_id
        WHERE c.as_of_date = :d
          AND a.symbol = ANY(:syms)
    """), {"d": target, "syms": underlyings}).mappings().all()
    signal_by_underlying = {
        r["underlying"]: {
            "score": (
                float(r["score"]) if r["score"] is not None else None
            ),
            "status": r["status"], "action": r["action"],
            "rejection_reason": r["rejection_reason"],
            "regime": r["regime"] if isinstance(r["regime"], dict) else None,
        }
        for r in sig_rows
    }

    # Pull spot price per underlying for ATM/ITM/OTM selection.
    spot_rows = db.execute(text("""
        SELECT a.symbol AS underlying,
               max(pb.close)::float AS last_close
        FROM asset a
        JOIN price_bar pb ON pb.asset_id = a.id
        WHERE a.symbol = ANY(:syms)
        GROUP BY a.symbol
    """), {"syms": underlyings}).all()
    # Use most-recent close (deterministic). max(close) above is wrong
    # for "latest price". Re-query DISTINCT ON for accuracy.
    spot_rows2 = db.execute(text("""
        SELECT DISTINCT ON (a.symbol)
               a.symbol AS underlying, pb.close::float AS last_close
        FROM asset a
        JOIN price_bar pb ON pb.asset_id = a.id
        WHERE a.symbol = ANY(:syms)
        ORDER BY a.symbol, pb.ts DESC
    """), {"syms": underlyings}).all()
    spot_by_underlying = {u: float(c) for u, c in spot_rows2}

    items: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for underlying, by_exp in by_underlying.items():
        sig = signal_by_underlying.get(underlying)
        if sig is None:
            rejected.append({
                "underlying": underlying,
                "reason": "no_stock_signal",
            })
            continue
        spot = spot_by_underlying.get(underlying)
        if spot is None or spot <= 0:
            rejected.append({
                "underlying": underlying,
                "reason": "no_spot_price",
            })
            continue
        direction = _direction_from_score(sig["score"])
        trend = _trend_from_regime(sig.get("regime"))

        # Loop over expirations; produce one strategy suggestion per
        # expiry where legs can be assembled cleanly.
        for expiry, contracts in by_exp.items():
            # Median IV for this expiry's chain (used for IV bucket).
            iv_values = [
                c["iv"] for c in contracts if c["iv"] is not None
            ]
            median_iv = (
                sorted(iv_values)[len(iv_values) // 2]
                if iv_values else None
            )
            iv_b = _iv_bucket(median_iv)
            strategy = _pick_strategy(direction, iv_b, trend)
            if strategy is None:
                rejected.append({
                    "underlying": underlying,
                    "expiry": (
                        expiry.isoformat() if hasattr(expiry, "isoformat")
                        else str(expiry)
                    ),
                    "reason": (
                        f"no_strategy_match: dir={direction} iv={iv_b} "
                        f"trend={trend}"
                    ),
                })
                continue
            legs = _build_legs(strategy, contracts, spot)
            if not legs:
                rejected.append({
                    "underlying": underlying,
                    "expiry": (
                        expiry.isoformat() if hasattr(expiry, "isoformat")
                        else str(expiry)
                    ),
                    "strategy": strategy,
                    "reason": "leg_construction_failed",
                })
                continue

            liq_min = _aggregate_liquidity(legs)
            spread_pct = _aggregate_spread_pct(legs)
            sig_strength = abs(sig["score"]) if sig["score"] is not None else 0.0
            iv_fit = (
                1.0 if iv_b == "medium"  # spreads love medium IV
                else 0.7 if iv_b in ("low", "high")
                else 0.5
            )
            confidence = round(
                min(1.0, sig_strength) * 0.5
                + liq_min * 0.3
                + iv_fit * 0.2,
                4,
            )

            items.append({
                "underlying": underlying,
                "stock_signal": {
                    "score": sig["score"],
                    "action": sig["action"],
                    "status": sig["status"],
                    "direction": direction,
                },
                "trend": trend,
                "iv_context": iv_b or "unknown",
                "iv_median_for_expiry": median_iv,
                "strategy": strategy,
                "expiration": (
                    expiry.isoformat() if hasattr(expiry, "isoformat")
                    else str(expiry)
                ),
                "spot_price_reference": spot,
                "legs": [
                    {
                        "type": l["type"],
                        "strike": l["strike"],
                        "action": l["action"],
                        "option_symbol": l["option_symbol"],
                        "expiry": l["expiry"],
                        "bid": l["bid"], "ask": l["ask"], "mid": l["mid"],
                        "open_interest": l["open_interest"],
                        "iv": l["iv"],
                        "liquidity_score": l["liquidity_score"],
                    }
                    for l in legs
                ],
                "liquidity_score": liq_min,
                "spread_pct": spread_pct,
                "confidence": confidence,
                "reason_summary": (
                    f"{direction} stock signal (score="
                    f"{sig['score'] if sig['score'] is not None else 'na'}) "
                    f"+ IV {iv_b or 'unknown'} + trend={trend} "
                    f"→ {strategy}"
                ),
                "status": "shadow_candidate",
            })

    items.sort(key=lambda it: -it["confidence"])
    for i, it in enumerate(items, 1):
        it["rank"] = i

    distribution: dict[str, int] = {}
    for it in items:
        distribution[it["strategy"]] = distribution.get(it["strategy"], 0) + 1

    return {
        "as_of_date": target.isoformat() if target else None,
        "underlyings_used": sorted(by_underlying.keys()),
        "contracts_reviewed": contracts_reviewed,
        "contracts_passed_liquidity": contracts_passed_liquidity,
        "count": min(limit, len(items)),
        "items": items[:limit],
        "strategy_distribution": distribution,
        "rejected": rejected,
        "vocabulary": {
            "strategy_names": list(_STRATEGY_NAMES),
            "iv_buckets": ["low", "medium", "high", "unknown"],
            "directions": ["strong_buy", "neutral", "strong_sell"],
            "trends": ["uptrend", "sideways", "downtrend", "unknown"],
            "statuses": ["shadow_candidate"],
        },
        "thresholds": {
            "iv_low": _IV_LOW, "iv_high": _IV_HIGH,
            "signal_bullish": _OPT_SIGNAL_BULLISH,
            "signal_bearish": _OPT_SIGNAL_BEARISH,
            "spread_min_pct": _SPREAD_MIN_PCT,
            "spread_max_pct": _SPREAD_MAX_PCT,
        },
        "notice": (
            "Shadow-only strategy suggestions. NO options_paper_trade "
            "rows. NO live execution. Strategies are intelligence "
            "output; execution path is not wired."
        ),
    }


# ---------------------------------------------------------------------------
# /performance/options/strategy-quality (+ details)
# ---------------------------------------------------------------------------
# Read-only forward-return scoring of options strategy suggestions /
# paper trades. Reads the `options_strategy_outcome` table populated
# by `scripts.compute_options_strategy_outcomes`. NO writes here. NO
# fabrication. Same-bar entry forbidden by writer (entry uses first
# chain snapshot strictly after submitted_at::date).

_OPT_QUALITY_HORIZONS = ("1D", "3D", "5D", "10D", "20D")
_OPT_QUALITY_LABELS = (
    "good", "neutral", "bad", "pending", "data_blocked",
)
_OPT_QUALITY_MODES = ("strict", "exploratory", "options_exploratory")


def _opt_quality_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    s = {l: 0 for l in _OPT_QUALITY_LABELS}
    s["total"] = len(rows)
    finalized = [
        r for r in rows if r.get("forward_return_pct") is not None
    ]
    for r in rows:
        s[r["outcome_label"]] = s.get(r["outcome_label"], 0) + 1
    n_fin = len(finalized)
    s["n_finalized"] = n_fin
    if n_fin:
        s["avg_forward_return_pct"] = (
            sum(r["forward_return_pct"] for r in finalized) / n_fin
        )
        mfe_vals = [
            r["mfe_pct"] for r in finalized if r.get("mfe_pct") is not None
        ]
        mae_vals = [
            r["mae_pct"] for r in finalized if r.get("mae_pct") is not None
        ]
        s["avg_mfe_pct"] = sum(mfe_vals) / len(mfe_vals) if mfe_vals else None
        s["avg_mae_pct"] = sum(mae_vals) / len(mae_vals) if mae_vals else None
        good = sum(1 for r in finalized if r["outcome_label"] == "good")
        s["hit_rate"] = good / n_fin
    else:
        s["avg_forward_return_pct"] = None
        s["avg_mfe_pct"] = None
        s["avg_mae_pct"] = None
        s["hit_rate"] = None
    return s


@options_router.get("/strategy-quality")
def options_strategy_quality(
    db: Session = Depends(get_session),
    as_of: str | None = Query(
        None, description="ISO date; defaults to latest as_of in table.",
    ),
    horizon: str = Query(
        "5D",
        description=f"One of {_OPT_QUALITY_HORIZONS}.",
    ),
    mode: str = Query(
        "strict",
        description=f"One of {_OPT_QUALITY_MODES}.",
    ),
) -> dict[str, Any]:
    """Aggregate strategy-quality summary at the requested horizon."""
    if horizon not in _OPT_QUALITY_HORIZONS:
        return {"error": f"horizon must be one of {_OPT_QUALITY_HORIZONS}"}
    if mode not in _OPT_QUALITY_MODES:
        return {"error": f"mode must be one of {_OPT_QUALITY_MODES}"}

    if as_of is None:
        latest = db.execute(text(
            "SELECT max(as_of_date) FROM options_strategy_outcome"
        )).scalar()
        if latest is None:
            return {
                "as_of_date": None, "horizon": horizon, "mode": mode,
                "summary": _empty_quality_summary(),
                "by_strategy": {},
                "notice": "No options_strategy_outcome rows yet.",
            }
        target = latest
    else:
        try:
            target = dt.date.fromisoformat(as_of)
        except ValueError:
            return {"error": "as_of must be ISO date YYYY-MM-DD"}

    rows = db.execute(text("""
        SELECT
          underlying, strategy_name, source, mode, horizon,
          entry_reference, exit_reference, forward_return_pct,
          mfe_pct, mae_pct, outcome_label
        FROM options_strategy_outcome
        WHERE as_of_date = :d AND horizon = :h AND mode = :m
    """), {"d": target, "h": horizon, "m": mode}).mappings().all()

    items: list[dict[str, Any]] = []
    for r in rows:
        items.append({
            "underlying": r["underlying"],
            "strategy_name": r["strategy_name"],
            "source": r["source"], "mode": r["mode"], "horizon": r["horizon"],
            "entry_reference": (
                float(r["entry_reference"])
                if r["entry_reference"] is not None else None
            ),
            "exit_reference": (
                float(r["exit_reference"])
                if r["exit_reference"] is not None else None
            ),
            "forward_return_pct": (
                float(r["forward_return_pct"])
                if r["forward_return_pct"] is not None else None
            ),
            "mfe_pct": (
                float(r["mfe_pct"]) if r["mfe_pct"] is not None else None
            ),
            "mae_pct": (
                float(r["mae_pct"]) if r["mae_pct"] is not None else None
            ),
            "outcome_label": r["outcome_label"],
        })

    by_strategy: dict[str, dict[str, Any]] = {}
    for it in items:
        bucket = by_strategy.setdefault(
            it["strategy_name"], {"items": []},
        )
        bucket["items"].append(it)
    for sname, b in by_strategy.items():
        b.update(_opt_quality_summary(b["items"]))
        del b["items"]

    return {
        "as_of_date": target.isoformat(),
        "horizon": horizon,
        "mode": mode,
        "horizons_supported": list(_OPT_QUALITY_HORIZONS),
        "thresholds": {
            "good_pct": 0.01, "bad_pct": -0.01,
        },
        "summary": _opt_quality_summary(items),
        "by_strategy": by_strategy,
        "notice": (
            "Read-only forward scoring. Entry uses first chain "
            "snapshot strictly after submitted_at::date — no same-bar "
            "labeling. Exit uses snapshot at or after target date. "
            "All quotes are real chain rows; nothing fabricated."
        ),
    }


@options_router.get("/strategy-quality/details")
def options_strategy_quality_details(
    db: Session = Depends(get_session),
    as_of: str | None = Query(None),
    horizon: str = Query("5D"),
    mode: str = Query("strict"),
    limit: int = Query(25, ge=1, le=200),
) -> dict[str, Any]:
    """Per-row detail listing — top items by absolute forward_return."""
    if horizon not in _OPT_QUALITY_HORIZONS:
        return {"error": f"horizon must be one of {_OPT_QUALITY_HORIZONS}"}
    if mode not in _OPT_QUALITY_MODES:
        return {"error": f"mode must be one of {_OPT_QUALITY_MODES}"}
    if as_of is None:
        latest = db.execute(text(
            "SELECT max(as_of_date) FROM options_strategy_outcome"
        )).scalar()
        if latest is None:
            return {"as_of_date": None, "count": 0, "items": []}
        target = latest
    else:
        try:
            target = dt.date.fromisoformat(as_of)
        except ValueError:
            return {"error": "as_of must be ISO date YYYY-MM-DD"}

    rows = db.execute(text("""
        SELECT
          underlying, strategy_name, legs_json,
          submitted_at_utc, horizon, source, mode,
          entry_reference, exit_reference, forward_return_pct,
          mfe_pct, mae_pct, outcome_label
        FROM options_strategy_outcome
        WHERE as_of_date = :d AND horizon = :h AND mode = :m
        ORDER BY abs(coalesce(forward_return_pct, 0)) DESC,
                 underlying ASC
        LIMIT :limit
    """), {"d": target, "h": horizon, "m": mode, "limit": limit}).all()

    items = []
    for r in rows:
        items.append({
            "underlying": r[0],
            "strategy_name": r[1],
            "legs": r[2],
            "submitted_at_utc": (
                r[3].isoformat() if r[3] else None
            ),
            "horizon": r[4],
            "source": r[5],
            "mode": r[6],
            "entry_reference": (
                float(r[7]) if r[7] is not None else None
            ),
            "exit_reference": (
                float(r[8]) if r[8] is not None else None
            ),
            "forward_return_pct": (
                float(r[9]) if r[9] is not None else None
            ),
            "mfe_pct": float(r[10]) if r[10] is not None else None,
            "mae_pct": float(r[11]) if r[11] is not None else None,
            "outcome_label": r[12],
        })
    return {
        "as_of_date": target.isoformat(),
        "horizon": horizon, "mode": mode,
        "count": len(items),
        "items": items,
    }


# ---------------------------------------------------------------------------
# /performance/options/promotion-candidates  (read-only)
# ---------------------------------------------------------------------------
# Surfaces auto-promotion eligibility + tier + proposed size for
# paper-trading options strategies. Pure read of
# `options_strategy_outcome`. NO writes. NO env reads — env-gated
# enforcement happens in the operator script + paper exec runner.

@options_router.get("/promotion-candidates")
def options_promotion_candidates(
    db: Session = Depends(get_session),
    horizon: str = Query("5D", description="Outcome horizon."),
    unit: str = Query(
        "strategy_name",
        description=(
            "Promotion grouping unit. One of: strategy_name, "
            "underlying_strategy, iv_bucket_strategy, "
            "direction_strategy."
        ),
    ),
) -> dict[str, Any]:
    from apps.api.src.domain.options_quality.promotion import (
        VALID_HORIZONS as _VH, VALID_UNITS as _VU,
        evaluate_promotions, candidate_to_dict,
        PromotionThresholds, SizingConfig,
    )
    if horizon not in _VH:
        return {"error": f"horizon must be one of {_VH}"}
    if unit not in _VU:
        return {"error": f"unit must be one of {_VU}"}

    cands = evaluate_promotions(
        db, horizon=horizon, unit=unit,
        thresholds=PromotionThresholds(), sizing=SizingConfig(),
    )
    items = [candidate_to_dict(c) for c in cands]
    eligible_count = sum(1 for c in cands if c.eligible)
    return {
        "horizon": horizon,
        "unit": unit,
        "count": len(items),
        "eligible_count": eligible_count,
        "items": items,
        "thresholds": {
            "min_samples": 20,
            "min_window_trading_days": 10,
            "min_hit_rate": 0.55,
            "min_avg_forward_return_pct": 0.0,
            "max_avg_mae_pct": -0.10,
            "min_liquidity_pass_rate": 0.90,
            "max_data_blocked_rate": 0.30,
            "min_positive_horizons": 2,
        },
        "sizing": {
            "base_pct": 0.005, "min_pct": 0.0025, "max_pct": 0.02,
            "hard_max_per_strategy_pct": 0.02,
            "hard_max_total_options_exposure_pct": 0.05,
            "hard_max_per_underlying_pct": 0.02,
            "hard_max_daily_new_pct": 0.03,
        },
        "notice": (
            "Read-only promotion view. Promotion is GATED behind "
            "OPTIONS_STRATEGY_PROMOTION_ENABLED + "
            "OPTIONS_DYNAMIC_SIZING_ENABLED env flags (default false). "
            "Promotion can ONLY influence rank, sizing, and daily "
            "execution cap — never bypasses liquidity, next-bar, or "
            "quote-freshness gates."
        ),
    }


# ---------------------------------------------------------------------------
# /performance/paper/exit-analytics  (Phase D — closed-trade analytics)
# ---------------------------------------------------------------------------
# Read-only analytics over the SELL rows in `paper_trade` joined to
# their closed `paper_position`. Each SELL is one realized event.
# Categorisation is done by string-matching the operator's exit
# reason text (set by run_paper_exit_cycle): "take_profit",
# "stop_loss", "max_hold", else "other". NEVER fabricates win
# rates on tiny samples — surfaces a sample-size caveat instead.

_EXIT_TP_TOKEN = "take_profit"
_EXIT_SL_TOKEN = "stop_loss"
_EXIT_MAX_HOLD_TOKEN = "max_hold"
_EXIT_SMALL_SAMPLE_THRESHOLD = 30


def _classify_exit_reason(reason: str | None) -> str:
    if not reason:
        return "other"
    r = reason.lower()
    if _EXIT_TP_TOKEN in r:
        return "take_profit"
    if _EXIT_SL_TOKEN in r:
        return "stop_loss"
    if _EXIT_MAX_HOLD_TOKEN in r:
        return "max_hold"
    return "other"


def _trading_days_inclusive(a: dt.date, b: dt.date) -> int:
    if b < a:
        return 0
    n = 0
    cur = a
    while cur <= b:
        if cur.weekday() < 5:
            n += 1
        cur = cur + dt.timedelta(days=1)
    return n


@router.get("/exit-analytics")
def paper_exit_analytics(
    db: Session = Depends(get_session),
    include_replay: bool = Query(
        False,
        description=(
            "Include replay-recovered rows. Default false to keep "
            "live-only headline."
        ),
    ),
    limit: int = Query(500, ge=1, le=2000),
) -> dict[str, Any]:
    """Read-only closed-trade analytics. Each SELL row is one
    realized event. Categories: take_profit / stop_loss /
    max_hold / other (string match on `paper_trade.reason`).

    NEVER fabricates a denominator. When `n_closed=0` the win
    rate is null and the response includes
    `note='no_closed_outcomes_yet'`. When n_closed is below the
    small-sample threshold the response surfaces
    `small_sample_warning` so the frontend can render the
    caveat verbatim.
    """
    excl = ""
    if not include_replay:
        excl = (
            " AND NOT EXISTS ("
            "  SELECT 1 FROM replay_recovery_manifest m"
            "  WHERE m.entity_type = 'paper_trade'"
            "    AND m.entity_id = pt.id::text"
            "    AND m.source IN ('replay','test')"
            ")"
        )
    rows = db.execute(text(f"""
        SELECT
          pt.id, a.symbol, pt.fill_ts, pt.fill_price,
          pt.realized_pnl, pt.reason,
          pt.portfolio_id, pp.opened_at AS pos_opened_at,
          pp.avg_cost AS pos_avg_cost,
          pp.quantity AS pos_quantity
        FROM paper_trade pt
        JOIN asset a ON a.id = pt.asset_id
        LEFT JOIN paper_position pp
               ON pp.portfolio_id = pt.portfolio_id
              AND pp.asset_id = pt.asset_id
        WHERE pt.side = 'sell'
          AND pt.realized_pnl IS NOT NULL
          {excl}
        ORDER BY pt.fill_ts DESC
        LIMIT :n
    """), {"n": limit}).mappings().all()

    n_closed = len(rows)
    if n_closed == 0:
        return {
            "notice": (
                "Read-only closed-trade analytics. No closed "
                "trades yet — denominator-free zero state."
            ),
            "include_replay": include_replay,
            "n_closed": 0,
            "n_winners": 0,
            "n_losers": 0,
            "win_rate": None,
            "note": "no_closed_outcomes_yet",
            "realized_pnl_total": 0.0,
            "avg_win_dollars": None,
            "avg_loss_dollars": None,
            "avg_hold_days": None,
            "best_exit": None,
            "worst_exit": None,
            "by_category": [],
            "exit_reason_raw_breakdown": [],
            "tp_sl_effectiveness": {
                "tp_count": 0, "sl_count": 0,
                "tp_total_pnl": 0.0, "sl_total_pnl": 0.0,
                "tp_avg_pnl": None, "sl_avg_pnl": None,
            },
            "small_sample_warning": None,
            "small_sample_threshold": _EXIT_SMALL_SAMPLE_THRESHOLD,
            "trades": [],
        }

    wins: list[float] = []
    losses: list[float] = []
    by_cat: dict[str, dict[str, Any]] = {
        "take_profit": {"n": 0, "wins": 0, "total_pnl": 0.0},
        "stop_loss":   {"n": 0, "wins": 0, "total_pnl": 0.0},
        "max_hold":    {"n": 0, "wins": 0, "total_pnl": 0.0},
        "other":       {"n": 0, "wins": 0, "total_pnl": 0.0},
    }
    raw_reasons: dict[str, int] = {}
    hold_days: list[int] = []
    trades: list[dict[str, Any]] = []
    pnl_total = 0.0
    best_row: dict[str, Any] | None = None
    worst_row: dict[str, Any] | None = None

    for r in rows:
        pnl = float(r["realized_pnl"])
        pnl_total += pnl
        if pnl > 0:
            wins.append(pnl)
        elif pnl < 0:
            losses.append(pnl)
        cat = _classify_exit_reason(r["reason"])
        by_cat[cat]["n"] += 1
        by_cat[cat]["total_pnl"] += pnl
        if pnl > 0:
            by_cat[cat]["wins"] += 1
        raw = r["reason"] or "(none)"
        raw_reasons[raw] = raw_reasons.get(raw, 0) + 1
        if r["pos_opened_at"] and r["fill_ts"]:
            hd = _trading_days_inclusive(
                r["pos_opened_at"].date(), r["fill_ts"].date(),
            )
            hold_days.append(hd)
        else:
            hd = None
        item = {
            "trade_id": str(r["id"]),
            "symbol": r["symbol"],
            "exit_ts": r["fill_ts"].isoformat() if r["fill_ts"] else None,
            "exit_price": float(r["fill_price"]),
            "realized_pnl": pnl,
            "reason": r["reason"],
            "category": cat,
            "held_days": hd,
        }
        trades.append(item)
        if best_row is None or pnl > best_row["realized_pnl"]:
            best_row = item
        if worst_row is None or pnl < worst_row["realized_pnl"]:
            worst_row = item

    win_rate = (
        len(wins) / n_closed if n_closed > 0 else None
    )
    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = sum(losses) / len(losses) if losses else None
    avg_hold = (
        sum(hold_days) / len(hold_days) if hold_days else None
    )

    by_category = [
        {
            "category": cat,
            "n": v["n"],
            "win_rate": (
                v["wins"] / v["n"] if v["n"] > 0 else None
            ),
            "total_pnl": v["total_pnl"],
            "avg_pnl": (
                v["total_pnl"] / v["n"] if v["n"] > 0 else None
            ),
        }
        for cat, v in by_cat.items()
    ]
    raw_breakdown = sorted(
        [{"reason": k, "n": v} for k, v in raw_reasons.items()],
        key=lambda x: -x["n"],
    )
    tp = by_cat["take_profit"]
    sl = by_cat["stop_loss"]
    tp_sl = {
        "tp_count": tp["n"],
        "tp_total_pnl": tp["total_pnl"],
        "tp_avg_pnl": (
            tp["total_pnl"] / tp["n"] if tp["n"] > 0 else None
        ),
        "tp_win_rate": (
            tp["wins"] / tp["n"] if tp["n"] > 0 else None
        ),
        "sl_count": sl["n"],
        "sl_total_pnl": sl["total_pnl"],
        "sl_avg_pnl": (
            sl["total_pnl"] / sl["n"] if sl["n"] > 0 else None
        ),
        "sl_win_rate": (
            sl["wins"] / sl["n"] if sl["n"] > 0 else None
        ),
    }
    small_sample = (
        f"Only {n_closed} closed "
        f"trade{'s' if n_closed != 1 else ''} so far — "
        f"statistics are directional, not reliable."
        if n_closed < _EXIT_SMALL_SAMPLE_THRESHOLD else None
    )
    return {
        "notice": (
            "Read-only closed-trade analytics. SELL rows are "
            "the realized events; buys never appear here."
        ),
        "include_replay": include_replay,
        "n_closed": n_closed,
        "n_winners": len(wins),
        "n_losers": len(losses),
        "win_rate": win_rate,
        "realized_pnl_total": pnl_total,
        "avg_win_dollars": avg_win,
        "avg_loss_dollars": avg_loss,
        "avg_hold_days": avg_hold,
        "best_exit": best_row,
        "worst_exit": worst_row,
        "by_category": by_category,
        "exit_reason_raw_breakdown": raw_breakdown,
        "tp_sl_effectiveness": tp_sl,
        "small_sample_warning": small_sample,
        "small_sample_threshold": _EXIT_SMALL_SAMPLE_THRESHOLD,
        "trades": trades,
    }


# ---------------------------------------------------------------------------
# /performance/paper/risk-dashboard  (Phase C — read-only risk rollup)
# ---------------------------------------------------------------------------
# Aggregate paper-trading risk view sourced exclusively from
# already-correct truth tables. Never recomputes exposure off
# nullable selector-path fields (that was the $0-exposure bug
# the post-exit phase fixed). Uses paper_equity_snapshot for
# NAV / cash / positions_value / unrealized P&L; latest price_bar
# for per-symbol mark; surfaces "mark unavailable" explicitly when
# the snapshot lacks positions_value.

@router.get("/risk-dashboard")
def paper_risk_dashboard(
    db: Session = Depends(get_session),
    include_replay: bool = Query(
        False,
        description=(
            "Include replay-recovered rows. Default false to keep "
            "live-only headline."
        ),
    ),
    top_n: int = Query(
        5, ge=1, le=50,
        description="Top-N rows for concentration tables.",
    ),
) -> dict[str, Any]:
    """Operator risk dashboard. NEVER reintroduces the $0-exposure
    bug — exposure value is read from
    `paper_equity_snapshot.positions_value` (mark-to-market sum
    of open positions). When that field is NULL on any active
    portfolio's latest snapshot the response surfaces
    `mark_unavailable=true` and `exposure_value=null` instead of
    fabricating a zero.

    Read-only. No execution surface."""
    excl_pos = _excl(include_replay, "paper_position", "pp")
    excl_pt = _excl(include_replay, "paper_trade", "pt")

    # 1. Latest snapshot per active portfolio -------------------------
    snap_rows = db.execute(text("""
        SELECT DISTINCT ON (s.portfolio_id)
               s.portfolio_id, p.name AS portfolio_name,
               s.snapshot_date, s.total_equity, s.cash,
               s.positions_value, s.unrealized_pnl,
               s.realized_pnl_cumulative
        FROM paper_equity_snapshot s
        JOIN paper_portfolio p ON p.id = s.portfolio_id
        WHERE p.is_active = TRUE
        ORDER BY s.portfolio_id, s.snapshot_date DESC
    """)).mappings().all()

    has_snapshots = bool(snap_rows)
    mark_unavailable = (
        not has_snapshots
        or any(r["positions_value"] is None for r in snap_rows)
    )
    nav = (
        sum(float(r["total_equity"]) for r in snap_rows)
        if has_snapshots else None
    )
    cash = (
        sum(float(r["cash"]) for r in snap_rows)
        if has_snapshots else None
    )
    positions_value = (
        sum(float(r["positions_value"]) for r in snap_rows)
        if has_snapshots and not mark_unavailable else None
    )
    unrealized_pnl = (
        sum(float(r["unrealized_pnl"] or 0) for r in snap_rows)
        if has_snapshots else None
    )
    if positions_value is not None and nav and nav > 0:
        exposure_pct = positions_value / nav
    else:
        exposure_pct = None
    snapshot_date = (
        max(r["snapshot_date"] for r in snap_rows).isoformat()
        if has_snapshots else None
    )

    # 2. Open positions count --------------------------------------
    open_positions_count = db.execute(text(
        f"SELECT count(*) FROM paper_position pp "
        f"WHERE pp.is_open = TRUE {excl_pos}"
    )).scalar() or 0

    # 3. Realized P&L (sum across all sells) -----------------------
    realized_pnl_total = db.execute(text(
        f"SELECT coalesce(sum(pt.realized_pnl), 0) FROM paper_trade pt "
        f"WHERE pt.realized_pnl IS NOT NULL {excl_pt}"
    )).scalar() or 0

    # 4. Concentration by symbol (top_n by notional) ---------------
    sym_rows = db.execute(text(f"""
        WITH last_px AS (
            SELECT DISTINCT ON (asset_id) asset_id, close
            FROM price_bar WHERE timeframe = '1d'
            ORDER BY asset_id, ts DESC
        )
        SELECT
          a.symbol,
          count(*)::int AS n_open,
          sum(pp.quantity)::numeric AS total_qty,
          sum(pp.quantity * coalesce(last_px.close, pp.avg_cost))
            ::numeric AS notional_usd,
          sum((coalesce(last_px.close, pp.avg_cost) - pp.avg_cost)
               * pp.quantity)::numeric AS unrealized,
          (count(*) FILTER (WHERE last_px.close IS NULL) > 0)::bool
            AS any_mark_missing
        FROM paper_position pp
        JOIN asset a ON a.id = pp.asset_id
        LEFT JOIN last_px ON last_px.asset_id = pp.asset_id
        WHERE pp.is_open = TRUE {excl_pos}
        GROUP BY a.symbol
        ORDER BY notional_usd DESC NULLS LAST
        LIMIT :n
    """), {"n": top_n}).mappings().all()
    concentration_by_symbol = [
        {
            "symbol": r["symbol"],
            "n_open": int(r["n_open"]),
            "total_qty": _f(r["total_qty"]),
            "notional_usd": _f(r["notional_usd"]),
            "unrealized_pnl": _f(r["unrealized"]),
            "mark_unavailable": bool(r["any_mark_missing"]),
        }
        for r in sym_rows
    ]
    top_5_notional = concentration_by_symbol[:5]

    # 5. Concentration by portfolio (every active portfolio) -------
    pf_rows = db.execute(text(f"""
        WITH last_px AS (
            SELECT DISTINCT ON (asset_id) asset_id, close
            FROM price_bar WHERE timeframe = '1d'
            ORDER BY asset_id, ts DESC
        )
        SELECT
          p.id AS portfolio_id, p.name AS portfolio_name,
          count(*) FILTER (WHERE pp.is_open = TRUE)::int AS n_open,
          sum(
            CASE WHEN pp.is_open
              THEN pp.quantity * coalesce(last_px.close, pp.avg_cost)
              ELSE 0 END
          )::numeric AS notional_usd
        FROM paper_portfolio p
        LEFT JOIN paper_position pp
          ON pp.portfolio_id = p.id
        LEFT JOIN last_px ON last_px.asset_id = pp.asset_id
        WHERE p.is_active = TRUE
        GROUP BY p.id, p.name
        ORDER BY notional_usd DESC NULLS LAST
    """)).mappings().all()
    concentration_by_portfolio = [
        {
            "portfolio_id": str(r["portfolio_id"]),
            "portfolio_name": r["portfolio_name"],
            "n_open": int(r["n_open"]),
            "notional_usd": _f(r["notional_usd"]),
        }
        for r in pf_rows
    ]

    # 6. Max drawdown from total daily equity -----------------------
    dd_row = db.execute(text("""
        WITH series AS (
            SELECT s.snapshot_date::date AS d,
                   sum(s.total_equity) AS equity
            FROM paper_equity_snapshot s
            JOIN paper_portfolio p ON p.id = s.portfolio_id
            WHERE p.is_active = TRUE
            GROUP BY s.snapshot_date::date
            ORDER BY 1
        ),
        runmax AS (
            SELECT d, equity,
                   max(equity) OVER (
                     ORDER BY d ROWS UNBOUNDED PRECEDING
                   ) AS peak
            FROM series
        )
        SELECT min((equity - peak) / peak)::numeric AS max_dd
        FROM runmax WHERE peak > 0
    """)).first()
    max_drawdown_pct = (
        _f(dd_row[0]) if dd_row and dd_row[0] is not None else None
    )

    # 7. Pending next-bar count (skip JSONL for stocks) -------------
    pending_next_bar_count = 0
    pending_note: str | None = None
    try:
        from pathlib import Path
        import json as _json
        skips_dir = Path(_SKIPS_DIR)
        latest = max(
            (p for p in skips_dir.glob("*.jsonl")),
            default=None,
            key=lambda p: p.name,
        )
        if latest:
            for line in latest.read_text().splitlines():
                try:
                    item = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                if item.get("status") == "pending_next_bar":
                    pending_next_bar_count += 1
        else:
            pending_note = "no skip-jsonl on disk"
    except Exception as exc:  # noqa: BLE001
        pending_note = f"pending-fills probe error: {exc}"

    # 8. Replay vs live trade split (always-on) ---------------------
    live_trades = db.execute(text("""
        SELECT count(*) FROM paper_trade pt
        WHERE NOT EXISTS (
          SELECT 1 FROM replay_recovery_manifest m
          WHERE m.entity_type = 'paper_trade'
            AND m.entity_id = pt.id::text
            AND m.source IN ('replay','test')
        )
    """)).scalar() or 0
    replay_trades = db.execute(text("""
        SELECT count(*) FROM paper_trade pt
        WHERE EXISTS (
          SELECT 1 FROM replay_recovery_manifest m
          WHERE m.entity_type = 'paper_trade'
            AND m.entity_id = pt.id::text
            AND m.source IN ('replay','test')
        )
    """)).scalar() or 0

    # Per-portfolio NAV / cash / positions_value / unrealized
    portfolios = [
        {
            "portfolio_id": str(r["portfolio_id"]),
            "portfolio_name": r["portfolio_name"],
            "snapshot_date": r["snapshot_date"].isoformat(),
            "nav": _f(r["total_equity"]),
            "cash": _f(r["cash"]),
            "positions_value": _f(r["positions_value"]),
            "unrealized_pnl": _f(r["unrealized_pnl"]),
            "realized_pnl_cumulative": _f(
                r["realized_pnl_cumulative"]
            ),
        }
        for r in snap_rows
    ]

    return {
        "notice": (
            "Read-only risk rollup. No execution controls; no "
            "order surface. Mark-to-market sourced from "
            "paper_equity_snapshot.positions_value."
        ),
        "include_replay": include_replay,
        "snapshot_date": snapshot_date,
        "mark_unavailable": mark_unavailable,
        "nav": nav,
        "cash": cash,
        "exposure_value": positions_value,
        "exposure_pct": exposure_pct,
        "open_positions_count": int(open_positions_count),
        "unrealized_pnl": unrealized_pnl,
        "realized_pnl_total": _f(realized_pnl_total),
        "max_drawdown_pct": max_drawdown_pct,
        "pending_next_bar_count": int(pending_next_bar_count),
        "pending_next_bar_note": pending_note,
        "live_trades_count": int(live_trades),
        "replay_trades_count": int(replay_trades),
        "concentration_by_symbol": concentration_by_symbol,
        "concentration_by_portfolio": concentration_by_portfolio,
        "top_5_notional": top_5_notional,
        "portfolios": portfolios,
    }


# ---------------------------------------------------------------------------
# /performance/paper/trade-quality  (Phase B — pre-ML diagnostic)
# ---------------------------------------------------------------------------
# Read-only quality scoring layer over existing paper_trade /
# paper_position / paper_equity_snapshot / price_bar rows.
# Deterministic, transparent, never participates in execution.

@router.get("/trade-quality")
def paper_trade_quality(
    db: Session = Depends(get_session),
    include_replay: bool = Query(
        False,
        description=(
            "Include replay-recovered rows. Default false to keep "
            "live-only headline."
        ),
    ),
    limit: int = Query(200, ge=1, le=500),
    max_hold_days: int = Query(
        10, ge=1, le=120,
        description=(
            "Hold-discipline budget (days). Mirrors "
            "PAPER_MAX_HOLD_DAYS env default."
        ),
    ),
) -> dict[str, Any]:
    """Pre-ML diagnostic. Returns a 0-100 score, A/B/C/D/F grade,
    thesis status enum, reason bullets, and a data completeness
    flag for each eligible paper-trade row.

    Eligibility mirrors `/paper/trades` dedup: SELL rows always
    appear, BUY rows only when the position is currently open.
    NEVER fabricates inputs — missing data drops completeness and
    the affected component to 0 points.

    The frontend MUST label any rendering of this output as a
    pre-ML diagnostic. It is not a recommendation, signal, or
    expected return. The score is internal review context only.
    """
    from apps.api.src.domain.paper_quality.service import (
        assemble_quality_report,
    )
    return assemble_quality_report(
        db,
        include_replay=include_replay,
        limit=limit,
        max_hold_days=max_hold_days,
    )


# ---------------------------------------------------------------------------
# Discord formatter (pure helper — no I/O)
# ---------------------------------------------------------------------------
def format_pending_fill_discord(item: dict[str, Any]) -> str:
    """Pure formatter for a single pending-fill payload. Caller chooses
    whether/how to send. Never auto-dispatched. Never claims success."""
    return (
        "🟡 Paper Trade Pending Fill\n"
        f"Symbol: {item.get('symbol', '?')}\n"
        f"Action: {item.get('action', 'Buy')}\n"
        f"Portfolio: {item.get('portfolio_id', '?')}\n"
        f"Submitted: {item.get('submitted_at', '?')}\n"
        f"Fill Rule: Next available price bar\n"
        f"Status: Waiting for next bar\n"
        f"Latest Bar: {item.get('latest_price_bar_ts', '—')}\n"
        f"Expected Fill Window: "
        f"{item.get('next_expected_bar_date', '?')}\n"
        "\n"
        "No trade has been filled yet. This is pending next-bar "
        "execution."
    )
