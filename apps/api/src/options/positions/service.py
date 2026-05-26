"""Phase C — Position Intelligence computation service.

Per open paper trade, compute the canonical AI-trade-management
payload. Read-only against:
  * options_paper_trade        (trade-level: status, breakevens, max-risk)
  * options_paper_trade_leg    (per-leg: strikes, entry quote, qty)
  * options_chain_snapshot     (current quote per leg)
  * options_trade_lifecycle_event (latest event → stage)
  * market_event_calendar      (catalyst inside remaining DTE)

Returns a list of `PositionIntelligence` dataclasses with explainable
guidance — not a brokerage greeks dump. Every signal is grounded in
a single named metric so the UI can show "WHY" alongside "WHAT".
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session


# -- guidance tiers (locked) -------------------------------------------------
# Conservative defaults aligned with the paper exit-cycle rules
# (TP 8% / SL 4% / MaxHold 10d) but tuned to options' larger pnl swings.

TAKE_PROFIT_PCT  = 0.50   # +50% of max profit captured → exit
STOP_LOSS_PCT    = -0.50  # -50% of max loss tolerated → exit
ROLL_DTE_FLOOR   = 7      # DTE <= 7 with positive pnl → roll candidate
EXPIRY_FLAG_DTE  = 3      # DTE <= 3 → flag for expiration handling
CATALYST_NEAR_DAYS = 5    # catalyst within N days → flag


GuidanceAction = Literal[
    "hold", "take_profit", "stop_loss", "roll",
    "expiring", "catalyst_caution", "review",
]


@dataclass
class PositionLeg:
    leg_index: int
    option_symbol: str
    underlying: str
    expiry: dt.date
    strike: float
    option_type: str
    side: str
    qty: int
    entry_mid: float | None
    entry_iv: float | None
    entry_delta: float | None
    entry_theta: float | None
    entry_vega: float | None
    current_mid: float | None
    current_iv: float | None
    current_delta: float | None
    current_theta: float | None
    current_vega: float | None
    quote_age_seconds: int | None


@dataclass
class CatalystOverlay:
    event_type: str
    event_date: dt.date
    days_away: int
    importance: str
    title: str
    explanation: str


@dataclass
class PositionIntelligence:
    trade_id: int
    underlying: str
    strategy_name: str
    status: str
    lifecycle_stage: str             # PROPOSED / FILLED / CLOSED / EXPIRED / …

    opened_at: dt.datetime | None
    days_held: int

    legs: list[PositionLeg]
    min_dte: int                      # smallest DTE across legs

    # P&L
    entry_credit_dollars: float | None
    current_value_dollars: float | None
    max_loss_dollars: float
    max_profit_dollars: float
    unrealized_pnl_dollars: float | None
    unrealized_pnl_pct_vs_max: float | None  # % captured of max profit
    fees_total_dollars: float

    # Breakevens + profit zone
    breakeven_lower: float | None
    breakeven_upper: float | None
    spot_price: float | None
    distance_to_breakeven_pct: float | None

    # Greek aggregates (sum across legs, qty-weighted)
    theta_per_day_dollars: float | None
    iv_change_pct: float | None       # current_iv − entry_iv (raw %)
    iv_change_label: str               # expanded / compressed / unchanged / unknown
    delta_net: float | None

    # Catalyst overlay (None when no event in remaining DTE)
    catalyst: CatalystOverlay | None

    # Guidance signal
    guidance_action: GuidanceAction
    guidance_label: str
    guidance_reason: str
    thesis_health: str                 # healthy / pressured / broken / unknown

    # Explainability blocks (UI uses these verbatim)
    thesis_health_reason: str | None = None
    theta_impact_reason: str | None = None
    iv_impact_reason: str | None = None
    breakeven_reason: str | None = None
    catalyst_reason: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_float(v: Any) -> float | None:
    if v is None: return None
    if isinstance(v, Decimal): return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _classify_iv_change(pct: float | None) -> tuple[str, str]:
    if pct is None:
        return "unknown", "IV change not measurable — entry/current quote missing."
    if pct >= 0.05:
        return "expanded", (
            f"Implied vol expanded by {pct * 100:.1f}% since entry — "
            "long-vega positions benefit; short-vega positions face MTM headwind."
        )
    if pct <= -0.05:
        return "compressed", (
            f"Implied vol compressed by {abs(pct) * 100:.1f}% since entry — "
            "long-vega positions face MTM headwind; short-vega positions benefit."
        )
    return "unchanged", (
        f"IV roughly unchanged ({pct * 100:+.1f}%). Decay drives P&L."
    )


def _thesis_health(
    pnl_pct: float | None,
    spot_within_zone: bool | None,
    delta_drift: float | None,
) -> tuple[str, str]:
    """Single qualitative read. Pull from the three strongest signals."""
    if pnl_pct is None:
        return "unknown", "P&L not measurable from current quotes."
    if pnl_pct <= -0.50:
        return "broken", (
            f"Unrealized P&L is {pnl_pct * 100:.0f}% of max-loss. "
            "Thesis materially impaired."
        )
    if pnl_pct >= 0.50:
        return "healthy", (
            f"Captured {pnl_pct * 100:.0f}% of max profit. "
            "Thesis playing out — consider locking in."
        )
    if spot_within_zone is False:
        return "pressured", (
            "Spot is outside the profit zone. Thesis under pressure but "
            "not broken — monitor breakeven distance + theta carry."
        )
    return "healthy", "Position is within the original profit envelope."


def _build_guidance(
    *, days_held: int, min_dte: int,
    pnl_pct_vs_max: float | None,
    catalyst: CatalystOverlay | None,
) -> tuple[GuidanceAction, str, str]:
    """Priority-ordered guidance. First matching rule wins.

    Order: stop_loss > take_profit > expiring > catalyst_caution > roll > hold
    """
    if pnl_pct_vs_max is not None and pnl_pct_vs_max <= STOP_LOSS_PCT:
        return (
            "stop_loss", "Take loss",
            f"Down {abs(pnl_pct_vs_max) * 100:.0f}% vs max-loss — "
            "close to preserve remaining capital.",
        )
    if pnl_pct_vs_max is not None and pnl_pct_vs_max >= TAKE_PROFIT_PCT:
        return (
            "take_profit", "Take profit",
            f"Captured {pnl_pct_vs_max * 100:.0f}% of max profit — "
            "exit risk asymmetric from here.",
        )
    if min_dte <= EXPIRY_FLAG_DTE:
        return (
            "expiring", "Expiring soon",
            f"DTE = {min_dte} day{'s' if min_dte != 1 else ''}. "
            "Pin-risk and gamma-decay accelerating; plan exit before expiry.",
        )
    if catalyst is not None and catalyst.days_away <= CATALYST_NEAR_DAYS \
            and catalyst.importance == "high":
        return (
            "catalyst_caution", "Catalyst ahead",
            f"{catalyst.event_type} on {catalyst.event_date.isoformat()} "
            f"(T-{catalyst.days_away}d). "
            "Premium will likely re-price; size accordingly.",
        )
    if min_dte <= ROLL_DTE_FLOOR \
            and pnl_pct_vs_max is not None and pnl_pct_vs_max > 0:
        return (
            "roll", "Roll candidate",
            f"DTE = {min_dte}. Position is in profit; rolling out captures "
            "remaining edge without taking gamma into final week.",
        )
    return ("hold", "Hold",
            "No action signal. Theta + breakeven distance carry the thesis.")


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


def fetch_open_trades(session: Session) -> list[int]:
    """Return ids of every paper trade currently in an open lifecycle."""
    rows = session.execute(text("""
        SELECT id FROM options_paper_trade
        WHERE status IN ('PROPOSED', 'FILLED', 'OPEN')
          AND paper_only = TRUE
        ORDER BY opened_at DESC NULLS LAST, id ASC
    """)).all()
    return [int(r[0]) for r in rows]


def _latest_lifecycle_event(session: Session, trade_id: int) -> str:
    row = session.execute(text("""
        SELECT event_type FROM options_trade_lifecycle_event
        WHERE trade_id = :tid
        ORDER BY event_at_utc DESC LIMIT 1
    """), {"tid": trade_id}).first()
    if row is None: return "NO_EVENT"
    return str(row[0])


def _legs_with_current_quotes(
    session: Session, trade_id: int,
) -> list[PositionLeg]:
    rows = session.execute(text("""
        SELECT
          l.leg_index, l.option_symbol, l.underlying, l.expiry,
          l.strike, l.option_type, l.side, l.qty,
          l.entry_mid, l.entry_iv, l.entry_delta, l.entry_theta,
          l.entry_vega,
          c.mid AS current_mid, c.iv AS current_iv,
          c.delta AS current_delta, c.theta AS current_theta,
          c.vega AS current_vega, c.quote_age_seconds
        FROM options_paper_trade_leg l
        LEFT JOIN LATERAL (
          SELECT mid, iv, delta, theta, vega, quote_age_seconds
          FROM options_chain_snapshot
          WHERE option_symbol = l.option_symbol
          ORDER BY snapshot_at_utc DESC LIMIT 1
        ) c ON TRUE
        WHERE l.trade_id = :tid
        ORDER BY l.leg_index ASC
    """), {"tid": trade_id}).mappings().all()
    out: list[PositionLeg] = []
    for r in rows:
        out.append(PositionLeg(
            leg_index=int(r["leg_index"]),
            option_symbol=str(r["option_symbol"]),
            underlying=str(r["underlying"]),
            expiry=r["expiry"],
            strike=_to_float(r["strike"]) or 0.0,
            option_type=str(r["option_type"]),
            side=str(r["side"]),
            qty=int(r["qty"]),
            entry_mid=_to_float(r["entry_mid"]),
            entry_iv=_to_float(r["entry_iv"]),
            entry_delta=_to_float(r["entry_delta"]),
            entry_theta=_to_float(r["entry_theta"]),
            entry_vega=_to_float(r["entry_vega"]),
            current_mid=_to_float(r["current_mid"]),
            current_iv=_to_float(r["current_iv"]),
            current_delta=_to_float(r["current_delta"]),
            current_theta=_to_float(r["current_theta"]),
            current_vega=_to_float(r["current_vega"]),
            quote_age_seconds=(
                int(r["quote_age_seconds"])
                if r["quote_age_seconds"] is not None else None
            ),
        ))
    return out


def _latest_underlying_spot(
    session: Session, underlying: str,
) -> float | None:
    row = session.execute(text("""
        SELECT close FROM price_bar
        WHERE asset_id IN (
          SELECT id FROM asset WHERE symbol = :u LIMIT 1
        ) AND timeframe = '1d'
        ORDER BY ts DESC LIMIT 1
    """), {"u": underlying}).first()
    if row is None: return None
    return _to_float(row[0])


def _catalyst_in_window(
    session: Session, underlying: str,
    *, today: dt.date, expiry: dt.date,
) -> CatalystOverlay | None:
    if expiry <= today:
        return None
    row = session.execute(text("""
        SELECT event_type, event_date, importance, title, explanation
        FROM market_event_calendar
        WHERE event_date > :today
          AND event_date <= :expiry
          AND :u = ANY(affected_symbols)
        ORDER BY event_date ASC, importance DESC, id ASC
        LIMIT 1
    """), {"today": today, "expiry": expiry, "u": underlying}).mappings().first()
    if row is None: return None
    return CatalystOverlay(
        event_type=str(row["event_type"]),
        event_date=row["event_date"],
        days_away=(row["event_date"] - today).days,
        importance=str(row["importance"]),
        title=str(row["title"]),
        explanation=str(row["explanation"]),
    )


def compute_intelligence_for_trade(
    session: Session, trade_id: int,
    *, today: dt.date | None = None,
) -> PositionIntelligence | None:
    """Compose one PositionIntelligence row. Returns None if trade
    not found or has no legs."""
    today = today or dt.date.today()
    trade = session.execute(text("""
        SELECT id, underlying, strategy_name, status,
               opened_at, entry_credit_dollars, max_loss_dollars,
               max_profit_dollars, fees_total_dollars,
               breakeven_lower, breakeven_upper
        FROM options_paper_trade WHERE id = :tid
    """), {"tid": trade_id}).mappings().first()
    if trade is None: return None

    legs = _legs_with_current_quotes(session, trade_id)
    if not legs: return None

    lifecycle = _latest_lifecycle_event(session, trade_id)
    spot = _latest_underlying_spot(session, str(trade["underlying"]))

    # ---- aggregates -----------------------------------------------------
    min_dte = min((leg.expiry - today).days for leg in legs)
    days_held = (
        (today - trade["opened_at"].date()).days
        if trade["opened_at"] else 0
    )

    # Sign convention: cost basis paid = positive, credit received = negative.
    # Engine stores entry_credit_dollars positive for credit spreads;
    # current_value mirrors that semantic. We compute generic per-leg PV.
    current_value = 0.0
    iv_change_sum = 0.0
    iv_change_n = 0
    theta_dollars = 0.0
    delta_net = 0.0
    for leg in legs:
        sign = 1 if leg.side.lower() == "buy" else -1
        if leg.current_mid is not None:
            current_value += sign * leg.qty * leg.current_mid * 100.0
        if leg.current_theta is not None:
            theta_dollars += sign * leg.qty * leg.current_theta * 100.0
        if leg.current_delta is not None:
            delta_net += sign * leg.qty * leg.current_delta
        if leg.entry_iv is not None and leg.current_iv is not None:
            iv_change_sum += (leg.current_iv - leg.entry_iv)
            iv_change_n += 1
    iv_change_pct = iv_change_sum / iv_change_n if iv_change_n else None
    iv_label, iv_reason = _classify_iv_change(iv_change_pct)

    entry_credit = _to_float(trade["entry_credit_dollars"])
    max_loss = _to_float(trade["max_loss_dollars"]) or 0.0
    max_profit = _to_float(trade["max_profit_dollars"]) or 0.0
    fees = _to_float(trade["fees_total_dollars"]) or 0.0

    # Unrealized = current_value (signed) - entry_credit (signed)
    # Engine semantic: entry_credit positive when credit collected.
    # We approximate unrealized as (current_value - entry_basis) - fees.
    unrealized = None
    if current_value is not None and entry_credit is not None:
        unrealized = (current_value - (-entry_credit)) - fees
        # entry_credit positive means we received credit so basis = -credit.
        # If entry_credit not stored (debit position), engine may use 0 with
        # max_loss covering the cost. Treat None branch defensively below.

    # Express unrealized as % of max_profit when positive, % of max_loss when
    # negative. Single ratio for guidance + UI.
    pnl_pct_vs_max = None
    if unrealized is not None:
        ref = max_profit if unrealized >= 0 else max_loss
        if ref and ref > 0:
            pnl_pct_vs_max = unrealized / ref
            # Clamp to sane range so UI never shows 1000%.
            pnl_pct_vs_max = max(-2.0, min(2.0, pnl_pct_vs_max))

    # Spot vs profit zone
    be_low = _to_float(trade["breakeven_lower"])
    be_high = _to_float(trade["breakeven_upper"])
    spot_within_zone = None
    distance_pct = None
    if spot is not None:
        if be_low is not None and be_high is not None:
            spot_within_zone = (be_low <= spot <= be_high)
        elif be_low is not None:
            spot_within_zone = (spot >= be_low)
        elif be_high is not None:
            spot_within_zone = (spot <= be_high)
        # Distance to nearest breakeven
        candidates = [b for b in (be_low, be_high) if b is not None]
        if candidates and spot:
            nearest = min(candidates, key=lambda b: abs(b - spot))
            distance_pct = (nearest - spot) / spot

    catalyst = _catalyst_in_window(
        session, str(trade["underlying"]),
        today=today,
        expiry=max(leg.expiry for leg in legs),
    )

    thesis_health, thesis_reason = _thesis_health(
        pnl_pct_vs_max, spot_within_zone,
        delta_net if delta_net is not None else None,
    )
    action, label, reason = _build_guidance(
        days_held=days_held, min_dte=min_dte,
        pnl_pct_vs_max=pnl_pct_vs_max, catalyst=catalyst,
    )

    theta_reason = (
        f"Net theta carry: {theta_dollars:+.2f} $/day. "
        f"Time decay {'works for' if theta_dollars > 0 else 'against' if theta_dollars < 0 else 'is neutral on'} "
        "this position."
        if theta_dollars is not None and theta_dollars != 0
        else "Theta carry not measurable — current greeks missing."
    )
    breakeven_reason = (
        f"Spot {spot:.2f} {'inside' if spot_within_zone else 'outside'} profit zone"
        + (f"; nearest breakeven {distance_pct * 100:+.1f}% away."
           if distance_pct is not None else ".")
        if spot is not None and (be_low or be_high)
        else "Breakeven distance not measurable — spot or breakevens missing."
    )
    catalyst_reason = (
        f"{catalyst.event_type} on {catalyst.event_date} "
        f"(T-{catalyst.days_away}d): {catalyst.explanation}"
        if catalyst else None
    )

    return PositionIntelligence(
        trade_id=int(trade["id"]),
        underlying=str(trade["underlying"]),
        strategy_name=str(trade["strategy_name"]),
        status=str(trade["status"]),
        lifecycle_stage=lifecycle,
        opened_at=trade["opened_at"],
        days_held=days_held,
        legs=legs,
        min_dte=min_dte,
        entry_credit_dollars=entry_credit,
        current_value_dollars=current_value,
        max_loss_dollars=max_loss,
        max_profit_dollars=max_profit,
        unrealized_pnl_dollars=unrealized,
        unrealized_pnl_pct_vs_max=pnl_pct_vs_max,
        fees_total_dollars=fees,
        breakeven_lower=be_low,
        breakeven_upper=be_high,
        spot_price=spot,
        distance_to_breakeven_pct=distance_pct,
        theta_per_day_dollars=theta_dollars if theta_dollars != 0 else None,
        iv_change_pct=iv_change_pct,
        iv_change_label=iv_label,
        delta_net=delta_net if delta_net != 0 else None,
        catalyst=catalyst,
        guidance_action=action,
        guidance_label=label,
        guidance_reason=reason,
        thesis_health=thesis_health,
        thesis_health_reason=thesis_reason,
        theta_impact_reason=theta_reason,
        iv_impact_reason=iv_reason,
        breakeven_reason=breakeven_reason,
        catalyst_reason=catalyst_reason,
        diagnostics={
            "leg_count": len(legs),
            "spot_within_zone": spot_within_zone,
        },
    )


def compute_intelligence_all(
    session: Session, *, today: dt.date | None = None,
) -> list[PositionIntelligence]:
    today = today or dt.date.today()
    out: list[PositionIntelligence] = []
    for tid in fetch_open_trades(session):
        item = compute_intelligence_for_trade(session, tid, today=today)
        if item is not None:
            out.append(item)
    return out


def intelligence_to_dict(item: PositionIntelligence) -> dict[str, Any]:
    return {
        "trade_id":           item.trade_id,
        "underlying":         item.underlying,
        "strategy_name":      item.strategy_name,
        "status":             item.status,
        "lifecycle_stage":    item.lifecycle_stage,
        "opened_at":          item.opened_at.isoformat() if item.opened_at else None,
        "days_held":          item.days_held,
        "min_dte":            item.min_dte,
        "legs": [
            {
                "leg_index": l.leg_index,
                "option_symbol": l.option_symbol,
                "expiry": l.expiry.isoformat() if l.expiry else None,
                "strike": l.strike,
                "option_type": l.option_type,
                "side": l.side,
                "qty": l.qty,
                "entry_mid": l.entry_mid,
                "current_mid": l.current_mid,
                "entry_iv": l.entry_iv,
                "current_iv": l.current_iv,
                "current_delta": l.current_delta,
                "current_theta": l.current_theta,
                "current_vega": l.current_vega,
                "quote_age_seconds": l.quote_age_seconds,
            }
            for l in item.legs
        ],
        "entry_credit_dollars":      item.entry_credit_dollars,
        "current_value_dollars":     item.current_value_dollars,
        "max_loss_dollars":          item.max_loss_dollars,
        "max_profit_dollars":        item.max_profit_dollars,
        "unrealized_pnl_dollars":    item.unrealized_pnl_dollars,
        "unrealized_pnl_pct_vs_max": item.unrealized_pnl_pct_vs_max,
        "fees_total_dollars":        item.fees_total_dollars,
        "breakeven_lower":           item.breakeven_lower,
        "breakeven_upper":           item.breakeven_upper,
        "spot_price":                item.spot_price,
        "distance_to_breakeven_pct": item.distance_to_breakeven_pct,
        "theta_per_day_dollars":     item.theta_per_day_dollars,
        "iv_change_pct":             item.iv_change_pct,
        "iv_change_label":           item.iv_change_label,
        "delta_net":                 item.delta_net,
        "catalyst": (
            {
                "event_type":  item.catalyst.event_type,
                "event_date":  item.catalyst.event_date.isoformat(),
                "days_away":   item.catalyst.days_away,
                "importance":  item.catalyst.importance,
                "title":       item.catalyst.title,
                "explanation": item.catalyst.explanation,
            } if item.catalyst else None
        ),
        "guidance": {
            "action": item.guidance_action,
            "label":  item.guidance_label,
            "reason": item.guidance_reason,
        },
        "thesis_health":         item.thesis_health,
        "thesis_health_reason":  item.thesis_health_reason,
        "theta_impact_reason":   item.theta_impact_reason,
        "iv_impact_reason":      item.iv_impact_reason,
        "breakeven_reason":      item.breakeven_reason,
        "catalyst_reason":       item.catalyst_reason,
        "diagnostics":           item.diagnostics,
    }
