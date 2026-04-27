"""Read-only service layer for the Options WebUI (Phase 11F).

Pure SELECT-only functions. NEVER writes. NEVER imports V2 / equity /
governance / ML / execution modules. NEVER triggers worker jobs.

The router (`routes_readonly.py`) consumes these functions and shapes
JSON responses. Keeping the data-access layer pure keeps the boundary
between read and write paths bright + greppable.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.options.paper.expiration import (
    FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
    FLAG_MISSING_SETTLEMENT,
    FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
)


# Frozen v1 universe — keep in sync with chain_ingest.DEFAULT_UNIVERSE.
# The router consumes this when no chain_snapshot rows exist yet.
DEFAULT_UNIVERSE: tuple[str, ...] = ("SPY", "QQQ", "IWM", "GLD", "TLT")


# Tokens re-exported so the route layer can carry them in DTOs without
# pulling expiration internals.
KNOWN_FLAGS = (
    FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
    FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
    FLAG_MISSING_SETTLEMENT,
)


# ---------------------------------------------------------------------------
# Symbols / expiries
# ---------------------------------------------------------------------------

def list_symbols(session: Session) -> list[str]:
    """Distinct underlyings present in options_chain_snapshot.
    Falls back to DEFAULT_UNIVERSE when the table is empty so the UI
    has something to render in dev environments.
    """
    rows = session.execute(text(
        "SELECT DISTINCT underlying FROM options_chain_snapshot "
        "ORDER BY underlying"
    )).all()
    found = [r.underlying for r in rows]
    return found if found else list(DEFAULT_UNIVERSE)


def list_expiries(session: Session, *, symbol: str) -> list[str]:
    """Distinct expiries (ISO date strings) present for `symbol` —
    sorted ascending.
    """
    rows = session.execute(text(
        "SELECT DISTINCT expiry FROM options_chain_snapshot "
        "WHERE underlying = :symbol "
        "ORDER BY expiry"
    ), {"symbol": symbol}).all()
    return [r.expiry.isoformat() for r in rows]


# ---------------------------------------------------------------------------
# Chain
# ---------------------------------------------------------------------------

def get_chain(
    session: Session, *, symbol: str, expiry: str | datetime.date,
) -> dict[str, Any]:
    """Latest snapshot per (strike, option_type) for symbol + expiry.

    Returns dict with `calls`, `puts`, `as_of_utc`, plus per-row
    `data_quality_flags` derived from missing greeks/iv.
    """
    if isinstance(expiry, str):
        try:
            expiry_d = datetime.date.fromisoformat(expiry)
        except ValueError:
            return {
                "symbol": symbol, "expiry": expiry,
                "as_of_utc": None, "calls": [], "puts": [],
            }
    else:
        expiry_d = expiry

    rows = session.execute(text(
        """
        SELECT DISTINCT ON (strike, option_type)
            snapshot_at_utc, underlying, expiry, strike, option_type,
            option_symbol, bid, ask, mid, last,
            volume, open_interest,
            delta, gamma, theta, vega, iv,
            quote_age_seconds, provider, provider_version
        FROM options_chain_snapshot
        WHERE underlying = :symbol AND expiry = :expiry
        ORDER BY strike, option_type, snapshot_at_utc DESC
        """
    ), {"symbol": symbol, "expiry": expiry_d}).all()

    calls: list[dict[str, Any]] = []
    puts:  list[dict[str, Any]] = []
    as_of: datetime.datetime | None = None
    for r in rows:
        if as_of is None or (r.snapshot_at_utc and r.snapshot_at_utc > as_of):
            as_of = r.snapshot_at_utc
        item = _chain_row_to_dto(r)
        if r.option_type == "CALL":
            calls.append(item)
        elif r.option_type == "PUT":
            puts.append(item)

    return {
        "symbol": symbol,
        "expiry": expiry_d.isoformat(),
        "as_of_utc": as_of.isoformat() if as_of else None,
        "calls": calls,
        "puts": puts,
    }


def _chain_row_to_dto(r) -> dict[str, Any]:
    spread: Decimal | None = None
    if r.bid is not None and r.ask is not None:
        spread = r.ask - r.bid
    flags: list[str] = []
    if r.iv is None:
        flags.append("MISSING_IV")
    if any(g is None for g in (r.delta, r.gamma, r.theta, r.vega)):
        flags.append("MISSING_GREEKS")
    return {
        "option_symbol": r.option_symbol,
        "strike": _dec(r.strike),
        "option_type": r.option_type,
        "bid": _dec(r.bid),
        "ask": _dec(r.ask),
        "mid": _dec(r.mid),
        "spread": _dec(spread),
        # `last` is informational only — UI never uses it for fills,
        # but exposes the value for parity with provider data.
        "last": _dec(r.last),
        "volume": r.volume,
        "open_interest": r.open_interest,
        "iv": _dec(r.iv),
        "delta": _dec(r.delta),
        "gamma": _dec(r.gamma),
        "theta": _dec(r.theta),
        "vega": _dec(r.vega),
        "quote_age_seconds": r.quote_age_seconds,
        "provider": r.provider,
        "data_quality_flags": flags,
    }


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------

def get_latest_features(
    session: Session, *, symbol: str,
) -> dict[str, Any] | None:
    """Latest feature row for symbol; None if not yet computed."""
    row = session.execute(text(
        """
        SELECT
            as_of_date, underlying, atm_iv,
            iv_rank_252d, iv_percentile_252d,
            realized_vol_20d, vrp_30d,
            skew_25d, term_structure_30_90,
            put_call_volume_ratio, put_call_oi_ratio,
            unusual_call_volume_z, unusual_put_volume_z,
            gamma_exposure_proxy, call_wall_strike, put_wall_strike,
            data_quality_flags
        FROM options_feature_daily
        WHERE underlying = :symbol
        ORDER BY as_of_date DESC
        LIMIT 1
        """
    ), {"symbol": symbol}).first()
    if row is None:
        return None
    return {
        "as_of_date": row.as_of_date.isoformat(),
        "symbol": row.underlying,
        "atm_iv": _dec(row.atm_iv),
        "iv_rank_252d": _dec(row.iv_rank_252d),
        "iv_percentile_252d": _dec(row.iv_percentile_252d),
        "realized_vol_20d": _dec(row.realized_vol_20d),
        "vrp_30d": _dec(row.vrp_30d),
        "skew_25d": _dec(row.skew_25d),
        "term_structure_30_90": _dec(row.term_structure_30_90),
        "put_call_volume_ratio": _dec(row.put_call_volume_ratio),
        "put_call_oi_ratio": _dec(row.put_call_oi_ratio),
        "unusual_call_volume_z": _dec(row.unusual_call_volume_z),
        "unusual_put_volume_z": _dec(row.unusual_put_volume_z),
        "gamma_exposure_proxy": _dec(row.gamma_exposure_proxy),
        "call_wall_strike": _dec(row.call_wall_strike),
        "put_wall_strike": _dec(row.put_wall_strike),
        "data_quality_flags": list(row.data_quality_flags or []),
    }


# ---------------------------------------------------------------------------
# Paper trades
# ---------------------------------------------------------------------------

def list_paper_trades(
    session: Session,
    *,
    status: str | None = None,
    underlying: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List paper trade headers, newest first."""
    where = []
    params: dict[str, Any] = {"limit": int(limit)}
    if status is not None:
        where.append("status = :status")
        params["status"] = status.upper()
    if underlying is not None:
        where.append("underlying = :underlying")
        params["underlying"] = underlying
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    rows = session.execute(text(
        f"""
        SELECT id, underlying, strategy_name, strategy_version, status,
               opened_at, closed_at,
               entry_credit_dollars, exit_debit_dollars, realized_pnl_dollars,
               fees_total_dollars, max_loss_dollars, max_profit_dollars,
               breakeven_lower, breakeven_upper,
               fill_model_version, paper_only
        FROM options_paper_trade
        {where_sql}
        ORDER BY COALESCE(closed_at, opened_at) DESC NULLS LAST
        LIMIT :limit
        """
    ), params).all()
    return [_trade_header_to_dto(r) for r in rows] + []  # always a list


def _trade_header_to_dto(r) -> dict[str, Any]:
    return {
        "id": int(r.id),
        "underlying": r.underlying,
        "strategy_name": r.strategy_name,
        "strategy_version": r.strategy_version,
        "status": r.status,
        "opened_at": r.opened_at.isoformat() if r.opened_at else None,
        "closed_at": r.closed_at.isoformat() if r.closed_at else None,
        "entry_credit_dollars": _dec(r.entry_credit_dollars),
        "exit_debit_dollars": _dec(r.exit_debit_dollars),
        "realized_pnl_dollars": _dec(r.realized_pnl_dollars),
        "fees_total_dollars": _dec(r.fees_total_dollars),
        "max_loss_dollars": _dec(r.max_loss_dollars),
        "max_profit_dollars": _dec(r.max_profit_dollars),
        "breakeven_lower": _dec(r.breakeven_lower),
        "breakeven_upper": _dec(r.breakeven_upper),
        "fill_model_version": r.fill_model_version,
        "paper_only": bool(r.paper_only),
    }


def get_trade_detail(
    session: Session, *, trade_id: int,
) -> dict[str, Any] | None:
    """Trade header + legs + lifecycle/expiration/assignment events.
    Returns None if the trade does not exist.
    """
    head_row = session.execute(text(
        """
        SELECT id, underlying, strategy_name, strategy_version, status,
               opened_at, closed_at,
               entry_credit_dollars, exit_debit_dollars, realized_pnl_dollars,
               fees_total_dollars, max_loss_dollars, max_profit_dollars,
               breakeven_lower, breakeven_upper,
               fill_model_version, paper_only
        FROM options_paper_trade WHERE id = :id
        """
    ), {"id": trade_id}).first()
    if head_row is None:
        return None

    leg_rows = session.execute(text(
        """
        SELECT leg_index, option_symbol, underlying, expiry, strike,
               option_type, side, qty,
               entry_quote_at_utc, entry_bid, entry_ask, entry_mid,
               entry_iv, entry_delta, entry_gamma, entry_theta, entry_vega,
               entry_fill_price,
               exit_quote_at_utc, exit_bid, exit_ask, exit_mid,
               exit_iv, exit_delta, exit_gamma, exit_theta, exit_vega,
               exit_fill_price, exit_reason
        FROM options_paper_trade_leg
        WHERE trade_id = :id
        ORDER BY leg_index
        """
    ), {"id": trade_id}).all()

    lifecycle = session.execute(text(
        """
        SELECT id, event_type, event_at_utc, triggered_by, payload_json
        FROM options_trade_lifecycle_event
        WHERE trade_id = :id
        ORDER BY event_at_utc, id
        """
    ), {"id": trade_id}).all()

    expirations = session.execute(text(
        """
        SELECT leg_index, expiry_date, underlying_settlement, classification,
               intrinsic_value_dollars, realized_pnl_dollars, event_at_utc
        FROM options_expiration_event
        WHERE trade_id = :id
        ORDER BY leg_index
        """
    ), {"id": trade_id}).all()

    assignments = session.execute(text(
        """
        SELECT leg_index, event_type, risk_level, ex_div_date, ex_div_amount,
               intrinsic_value_dollars, realized_pnl_dollars,
               event_at_utc, notes
        FROM options_assignment_event
        WHERE trade_id = :id
        ORDER BY event_at_utc, id
        """
    ), {"id": trade_id}).all()

    flags = _aggregate_trade_flags(lifecycle, expirations, assignments)

    return {
        **_trade_header_to_dto(head_row),
        "data_quality_flags": flags,
        "legs": [_leg_to_dto(r) for r in leg_rows],
        "lifecycle_events": [_lifecycle_to_dto(r) for r in lifecycle],
        "expiration_events": [_expiration_to_dto(r) for r in expirations],
        "assignment_events": [_assignment_to_dto(r) for r in assignments],
    }


def _leg_to_dto(r) -> dict[str, Any]:
    return {
        "leg_index": int(r.leg_index),
        "option_symbol": r.option_symbol,
        "underlying": r.underlying,
        "expiry": r.expiry.isoformat(),
        "strike": _dec(r.strike),
        "option_type": r.option_type,
        "side": r.side, "qty": int(r.qty),
        "entry": {
            "quote_at_utc": r.entry_quote_at_utc.isoformat() if r.entry_quote_at_utc else None,
            "bid": _dec(r.entry_bid), "ask": _dec(r.entry_ask),
            "mid": _dec(r.entry_mid),
            "iv": _dec(r.entry_iv),
            "delta": _dec(r.entry_delta), "gamma": _dec(r.entry_gamma),
            "theta": _dec(r.entry_theta), "vega":  _dec(r.entry_vega),
            "fill_price": _dec(r.entry_fill_price),
        },
        "exit": {
            "quote_at_utc": r.exit_quote_at_utc.isoformat() if r.exit_quote_at_utc else None,
            "bid": _dec(r.exit_bid), "ask": _dec(r.exit_ask),
            "mid": _dec(r.exit_mid),
            "iv": _dec(r.exit_iv),
            "delta": _dec(r.exit_delta), "gamma": _dec(r.exit_gamma),
            "theta": _dec(r.exit_theta), "vega":  _dec(r.exit_vega),
            "fill_price": _dec(r.exit_fill_price),
            "reason": r.exit_reason,
        },
    }


def _lifecycle_to_dto(r) -> dict[str, Any]:
    return {
        "id": int(r.id),
        "event_type": r.event_type,
        "event_at_utc": r.event_at_utc.isoformat() if r.event_at_utc else None,
        "triggered_by": r.triggered_by,
        "payload": dict(r.payload_json or {}),
    }


def _expiration_to_dto(r) -> dict[str, Any]:
    return {
        "leg_index": int(r.leg_index),
        "expiry_date": r.expiry_date.isoformat(),
        "underlying_settlement": _dec(r.underlying_settlement),
        "classification": r.classification,
        "intrinsic_value_dollars": _dec(r.intrinsic_value_dollars),
        "realized_pnl_dollars": _dec(r.realized_pnl_dollars),
        "event_at_utc": r.event_at_utc.isoformat() if r.event_at_utc else None,
    }


def _assignment_to_dto(r) -> dict[str, Any]:
    return {
        "leg_index": int(r.leg_index),
        "event_type": r.event_type,
        "risk_level": r.risk_level,
        "ex_div_date": r.ex_div_date.isoformat() if r.ex_div_date else None,
        "ex_div_amount": _dec(r.ex_div_amount),
        "intrinsic_value_dollars": _dec(r.intrinsic_value_dollars),
        "realized_pnl_dollars": _dec(r.realized_pnl_dollars),
        "event_at_utc": r.event_at_utc.isoformat() if r.event_at_utc else None,
        "notes": r.notes,
    }


def _aggregate_trade_flags(
    lifecycle, expirations, assignments,
) -> list[str]:
    """Pull surfaceable flags from event payloads + classifications.
    Returns dedup'd ordered list (matches engine convention)."""
    out: list[str] = []
    for ev in lifecycle:
        payload = ev.payload_json or {}
        for f in payload.get("flags", []) or []:
            if f and f not in out:
                out.append(f)
    for ev in expirations:
        if ev.classification == "PIN_RISK" and FLAG_PIN_RISK_UNCERTAIN_OUTCOME not in out:
            out.append(FLAG_PIN_RISK_UNCERTAIN_OUTCOME)
        if ev.classification == "MISSING_DATA" and FLAG_MISSING_SETTLEMENT not in out:
            out.append(FLAG_MISSING_SETTLEMENT)
    if assignments and FLAG_ASSIGNMENT_SIMPLIFIED_EXIT not in out:
        out.append(FLAG_ASSIGNMENT_SIMPLIFIED_EXIT)
    return out


# ---------------------------------------------------------------------------
# Risk summary
# ---------------------------------------------------------------------------

def get_risk_summary(
    session: Session,
) -> dict[str, Any]:
    """Aggregate risk view across OPEN paper trades.

    All values are SUMS over OPEN trades only; closed/expired/assigned
    are excluded so the dashboard reflects current at-risk capital.

    Greeks aggregation requires per-leg Greeks at entry — used as a
    proxy. NOT a live risk number; surfaced with the
    `Naive entry-time Greeks proxy` label downstream.
    """
    open_trades = session.execute(text(
        """
        SELECT id, underlying, max_loss_dollars
        FROM options_paper_trade
        WHERE status = 'OPEN' AND paper_only = TRUE
        """
    )).all()

    expiry_concentration = session.execute(text(
        """
        SELECT l.expiry, COUNT(DISTINCT t.id) AS n_trades,
               SUM(t.max_loss_dollars) AS max_loss_at_expiry
        FROM options_paper_trade t
        JOIN options_paper_trade_leg l ON l.trade_id = t.id
        WHERE t.status = 'OPEN' AND t.paper_only = TRUE
        GROUP BY l.expiry
        ORDER BY l.expiry
        """
    )).all()

    greeks = session.execute(text(
        """
        SELECT
            SUM(CASE WHEN l.side='BUY'  THEN  l.entry_delta * l.qty
                     WHEN l.side='SELL' THEN -l.entry_delta * l.qty END) AS net_delta,
            SUM(CASE WHEN l.side='BUY'  THEN  l.entry_gamma * l.qty
                     WHEN l.side='SELL' THEN -l.entry_gamma * l.qty END) AS net_gamma,
            SUM(CASE WHEN l.side='BUY'  THEN  l.entry_theta * l.qty
                     WHEN l.side='SELL' THEN -l.entry_theta * l.qty END) AS net_theta,
            SUM(CASE WHEN l.side='BUY'  THEN  l.entry_vega  * l.qty
                     WHEN l.side='SELL' THEN -l.entry_vega  * l.qty END) AS net_vega
        FROM options_paper_trade t
        JOIN options_paper_trade_leg l ON l.trade_id = t.id
        WHERE t.status = 'OPEN' AND t.paper_only = TRUE
        """
    )).first()

    n_assignment_events = session.execute(text(
        "SELECT COUNT(*) FROM options_assignment_event"
    )).scalar_one()

    n_pin_risk = session.execute(text(
        "SELECT COUNT(*) FROM options_expiration_event "
        "WHERE classification = 'PIN_RISK'"
    )).scalar_one()

    n_missing = session.execute(text(
        "SELECT COUNT(*) FROM options_expiration_event "
        "WHERE classification = 'MISSING_DATA'"
    )).scalar_one()

    flags: list[str] = []
    if n_assignment_events > 0:
        flags.append(FLAG_ASSIGNMENT_SIMPLIFIED_EXIT)
    if n_pin_risk > 0:
        flags.append(FLAG_PIN_RISK_UNCERTAIN_OUTCOME)
    if n_missing > 0:
        flags.append(FLAG_MISSING_SETTLEMENT)

    return {
        "n_open_trades": len(open_trades),
        "max_loss_exposure_dollars": _dec(
            sum((Decimal(str(t.max_loss_dollars or 0)) for t in open_trades),
                start=Decimal("0"))
        ),
        "net_delta": _dec(greeks.net_delta) if greeks else None,
        "net_gamma": _dec(greeks.net_gamma) if greeks else None,
        "net_theta": _dec(greeks.net_theta) if greeks else None,
        "net_vega":  _dec(greeks.net_vega)  if greeks else None,
        "expiry_concentration": [
            {
                "expiry": r.expiry.isoformat(),
                "n_trades": int(r.n_trades),
                "max_loss_at_expiry_dollars": _dec(r.max_loss_at_expiry),
            }
            for r in expiry_concentration
        ],
        "n_assignment_events": int(n_assignment_events),
        "n_pin_risk_events": int(n_pin_risk),
        "n_missing_settlement_events": int(n_missing),
        "data_quality_flags": flags,
        "greeks_source_label": (
            "Naive entry-time Greeks proxy — not live mark-to-market"
        ),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dec(v) -> str | None:
    """Decimal/float → string for JSON. None passes through.

    NEVER returns 0 for None — caller layer must show 'Insufficient
    data' or 'Unavailable' instead.
    """
    if v is None:
        return None
    return str(v)
