"""Compact share-friendly summary text for Slack / email / issues."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from apps.api.src.domain.dashboard.summary import build_summary
from apps.api.src.domain.pnl.engine import portfolio_pnl, resolve_portfolio


def _d(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return v if isinstance(v, Decimal) else Decimal(str(v))
    except Exception:  # noqa: BLE001
        return None


def _fmt_money(v: Decimal | None) -> str:
    if v is None:
        return "—"
    sign = "-" if v < 0 else ""
    amt = abs(v)
    return f"{sign}${amt:,.2f}"


def _fmt_pct(v: Decimal | None) -> str:
    if v is None:
        return "—"
    return f"{v*100:.2f}%"


def build_share_payload(
    session: Session,
    *,
    portfolio_id: str | None = None,
    as_of: dt.date | None = None,
) -> dict[str, Any]:
    summary = build_summary(session, portfolio_id=portfolio_id, as_of=as_of)
    portfolio = resolve_portfolio(session, portfolio_id)
    pnl = portfolio_pnl(session, portfolio) if portfolio is not None else None

    top_positions: list[dict[str, Any]] = []
    if summary.get("portfolio"):
        for p in summary["portfolio"].get("top_positions", [])[:5]:
            top_positions.append({
                "symbol": p.get("symbol"),
                "weight": p.get("weight"),
                "unrealized_pnl": p.get("unrealized_pnl"),
                "unrealized_pct": p.get("unrealized_pct"),
            })

    return {
        "as_of_date": summary.get("as_of_date"),
        "regime": {
            "market_trend": summary.get("regime", {}).get("market_trend") if summary.get("regime") else None,
            "vol_regime": summary.get("regime", {}).get("vol_regime") if summary.get("regime") else None,
        },
        "candidates": summary.get("candidates", {}),
        "blocked_alpha_count": summary.get("blocked_alpha", {}).get("count"),
        "portfolio": {
            "portfolio_id": pnl.portfolio_id if pnl else None,
            "nav": str(pnl.nav) if pnl else None,
            "cash": str(pnl.cash) if pnl else None,
            "daily_pnl": str(pnl.daily_pnl) if pnl and pnl.daily_pnl is not None else None,
            "cumulative_pnl": str(pnl.cumulative_pnl) if pnl else None,
            "realized_pnl": str(pnl.realized_pnl) if pnl else None,
            "unrealized_pnl": str(pnl.unrealized_pnl) if pnl else None,
            "open_positions": pnl.open_positions_count if pnl else None,
        },
        "top_positions": top_positions,
        "top_buys": summary.get("top_buys", []),
        "alerts": summary.get("alerts", []),
    }


def render_share_text(payload: dict[str, Any]) -> str:
    """Plain-text render for copy/paste."""
    lines: list[str] = []
    as_of = payload.get("as_of_date") or "—"
    regime = payload.get("regime") or {}
    trend = regime.get("market_trend") or "—"
    vol = regime.get("vol_regime") or "—"
    lines.append(f"Investment Platform — {as_of}")
    lines.append(f"Regime: trend={trend}  vol={vol}")

    c = payload.get("candidates") or {}
    lines.append(
        f"Candidates: evaluated={c.get('total_evaluated', 0)} "
        f"accepted={c.get('accepted_total', 0)} "
        f"buys={c.get('accepted_buys', 0)} "
        f"rejected={c.get('rejected_total', 0)} "
        f"blocked_alpha={payload.get('blocked_alpha_count', 0)}"
    )

    p = payload.get("portfolio") or {}
    nav = _d(p.get("nav"))
    cash = _d(p.get("cash"))
    daily = _d(p.get("daily_pnl"))
    cum = _d(p.get("cumulative_pnl"))
    realized = _d(p.get("realized_pnl"))
    unrealized = _d(p.get("unrealized_pnl"))
    lines.append(
        f"Portfolio: NAV={_fmt_money(nav)}  "
        f"Cash={_fmt_money(cash)}  "
        f"DailyPnL={_fmt_money(daily)}  "
        f"CumPnL={_fmt_money(cum)}  "
        f"Realized={_fmt_money(realized)}  "
        f"Unrealized={_fmt_money(unrealized)}  "
        f"OpenPos={p.get('open_positions') or 0}"
    )

    top = payload.get("top_positions") or []
    if top:
        lines.append("Top positions:")
        for tp in top:
            sym = tp.get("symbol") or "—"
            wt = _d(tp.get("weight"))
            upl = _d(tp.get("unrealized_pnl"))
            uppct = _d(tp.get("unrealized_pct"))
            lines.append(
                f"  - {sym}: weight={_fmt_pct(wt)} "
                f"uPnL={_fmt_money(upl)} ({_fmt_pct(uppct)})"
            )

    buys = payload.get("top_buys") or []
    if buys:
        lines.append("Top Buy candidates:")
        for b in buys[:5]:
            sym = b.get("symbol") or "—"
            score = b.get("composite_score") or "—"
            conf = b.get("confidence") or "—"
            lines.append(f"  - {sym}: composite={score} conf={conf}")

    alerts = payload.get("alerts") or []
    if alerts:
        lines.append("Alerts:")
        for a in alerts:
            sev = (a.get("severity") or "info").upper()
            lines.append(f"  [{sev}] {a.get('code')}: {a.get('message')}")
    else:
        lines.append("Alerts: none")

    return "\n".join(lines) + "\n"
