"""Phase E — Journal timeline composer.

Pulls events from 5 source tables into a single ordered timeline.
Each entry carries linkage IDs (trade_id / candidate_id /
observation_id / underlying) so the UI can route the operator to
the matching Research / Positions / Opportunities surface.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


# Canonical entry types — the UI keys color + icon off these.
ENTRY_TYPES = (
    "shadow_observation",       # would_trade=true on a contract
    "candidate_emitted",        # AI interpretation produced
    "trade_proposed",           # paper_trade row created
    "lifecycle_filled",
    "lifecycle_mtm",
    "lifecycle_expiring_flagged",
    "lifecycle_pin_risk",
    "lifecycle_early_assign_risk",
    "lifecycle_closed",
    "lifecycle_expired",
    "lifecycle_assigned",
    "lifecycle_force_closed",
    "assignment_event",
    "expiration_event",
)


def _to_float(v: Any) -> float | None:
    if v is None: return None
    if isinstance(v, Decimal): return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@dataclass
class TimelineEntry:
    entry_id: str               # composite "source:row_id"
    entry_type: str
    entry_at_utc: dt.datetime
    underlying: str
    title: str
    summary: str
    importance: str             # high / medium / low
    # Linkage IDs (any may be None depending on source)
    trade_id: int | None = None
    candidate_id: int | None = None
    observation_id: int | None = None
    strategy_name: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _row_to_entry(*, source: str, row_id: Any, **kwargs) -> TimelineEntry:
    return TimelineEntry(
        entry_id=f"{source}:{row_id}",
        **kwargs,
    )


def _fetch_shadow_observations(
    session: Session, *, since: dt.datetime, limit: int,
) -> list[TimelineEntry]:
    rows = session.execute(text("""
        SELECT id, created_at, underlying_symbol, option_symbol,
               strategy_name, strike, option_type, expiration, score
        FROM options_shadow_decision_log
        WHERE created_at >= :since
          AND would_trade = TRUE
        ORDER BY created_at DESC
        LIMIT :n
    """), {"since": since, "n": limit}).mappings().all()
    out: list[TimelineEntry] = []
    for r in rows:
        out.append(_row_to_entry(
            source="shadow",
            row_id=int(r["id"]),
            entry_type="shadow_observation",
            entry_at_utc=r["created_at"],
            underlying=str(r["underlying_symbol"]),
            title=f"AI saw setup on {r['underlying_symbol']}",
            summary=(
                f"{str(r['option_type']).upper()} @ ${r['strike']} "
                f"exp {r['expiration']} passed all filter gates."
            ),
            importance="medium",
            observation_id=int(r["id"]),
            strategy_name=str(r["strategy_name"]),
            diagnostics={
                "option_symbol": str(r["option_symbol"]),
                "score":         _to_float(r["score"]),
            },
        ))
    return out


def _fetch_candidates(
    session: Session, *, since: dt.datetime, limit: int,
) -> list[TimelineEntry]:
    rows = session.execute(text("""
        SELECT c.id, c.created_at, c.underlying, c.rule_id,
               c.bias, c.composite_score, c.why_emitted,
               c.triggering_rule, c.shadow_observation_id,
               c.earliest_event_type, c.earliest_event_date,
               c.event_days_away
        FROM options_strategy_candidate c
        WHERE c.created_at >= :since
        ORDER BY c.created_at DESC, c.composite_score DESC NULLS LAST
        LIMIT :n
    """), {"since": since, "n": limit}).mappings().all()
    out: list[TimelineEntry] = []
    for r in rows:
        comp = _to_float(r["composite_score"]) or 0.0
        out.append(_row_to_entry(
            source="candidate",
            row_id=int(r["id"]),
            entry_type="candidate_emitted",
            entry_at_utc=r["created_at"],
            underlying=str(r["underlying"]),
            title=f"AI proposed {str(r['rule_id']).replace('_', ' ').lower()} on {r['underlying']}",
            summary=str(r["why_emitted"]),
            importance="high" if comp >= 0.78 else "medium",
            candidate_id=int(r["id"]),
            observation_id=int(r["shadow_observation_id"]),
            strategy_name=str(r["rule_id"]),
            diagnostics={
                "bias":            str(r["bias"]),
                "composite_score": comp,
                "triggering_rule": str(r["triggering_rule"]),
                "earliest_event_type": (
                    str(r["earliest_event_type"])
                    if r["earliest_event_type"] else None
                ),
                "earliest_event_date": (
                    r["earliest_event_date"].isoformat()
                    if r["earliest_event_date"] else None
                ),
                "event_days_away": r["event_days_away"],
            },
        ))
    return out


def _fetch_trades(
    session: Session, *, since: dt.datetime, limit: int,
) -> list[TimelineEntry]:
    rows = session.execute(text("""
        SELECT id, created_at, opened_at, closed_at,
               underlying, strategy_name, status,
               entry_credit_dollars, realized_pnl_dollars,
               max_loss_dollars, max_profit_dollars
        FROM options_paper_trade
        WHERE created_at >= :since
        ORDER BY created_at DESC
        LIMIT :n
    """), {"since": since, "n": limit}).mappings().all()
    out: list[TimelineEntry] = []
    for r in rows:
        out.append(_row_to_entry(
            source="trade",
            row_id=int(r["id"]),
            entry_type="trade_proposed",
            entry_at_utc=r["created_at"],
            underlying=str(r["underlying"]),
            title=f"{str(r['strategy_name']).replace('_', ' ').lower().title()} proposed on {r['underlying']}",
            summary=(
                f"Status {r['status']}. Max profit "
                f"${_to_float(r['max_profit_dollars']) or 0:.0f}, "
                f"max loss ${_to_float(r['max_loss_dollars']) or 0:.0f}."
            ),
            importance="medium",
            trade_id=int(r["id"]),
            strategy_name=str(r["strategy_name"]),
            diagnostics={
                "status":               str(r["status"]),
                "entry_credit_dollars": _to_float(r["entry_credit_dollars"]),
                "realized_pnl_dollars": _to_float(r["realized_pnl_dollars"]),
                "max_loss_dollars":     _to_float(r["max_loss_dollars"]),
                "max_profit_dollars":   _to_float(r["max_profit_dollars"]),
            },
        ))
    return out


LIFECYCLE_TITLE: dict[str, str] = {
    "PROPOSED":           "Trade proposed",
    "FILLED":             "Trade filled",
    "MTM":                "Mark-to-market update",
    "EXPIRING_FLAGGED":   "Expiration flag",
    "PIN_RISK_FLAGGED":   "Pin-risk flag",
    "EARLY_ASSIGN_RISK":  "Early-assignment risk flag",
    "CLOSED":             "Trade closed",
    "EXPIRED":            "Trade expired",
    "ASSIGNED":           "Trade assigned",
    "FORCE_CLOSED":       "Force-closed by operator",
}

LIFECYCLE_TYPE: dict[str, str] = {
    "PROPOSED":           "trade_proposed",
    "FILLED":             "lifecycle_filled",
    "MTM":                "lifecycle_mtm",
    "EXPIRING_FLAGGED":   "lifecycle_expiring_flagged",
    "PIN_RISK_FLAGGED":   "lifecycle_pin_risk",
    "EARLY_ASSIGN_RISK":  "lifecycle_early_assign_risk",
    "CLOSED":             "lifecycle_closed",
    "EXPIRED":            "lifecycle_expired",
    "ASSIGNED":           "lifecycle_assigned",
    "FORCE_CLOSED":       "lifecycle_force_closed",
}

LIFECYCLE_IMPORTANCE: dict[str, str] = {
    "PROPOSED":           "medium",
    "FILLED":             "high",
    "MTM":                "low",
    "EXPIRING_FLAGGED":   "high",
    "PIN_RISK_FLAGGED":   "high",
    "EARLY_ASSIGN_RISK":  "high",
    "CLOSED":             "high",
    "EXPIRED":            "high",
    "ASSIGNED":           "high",
    "FORCE_CLOSED":       "high",
}


def _fetch_lifecycle(
    session: Session, *, since: dt.datetime, limit: int,
) -> list[TimelineEntry]:
    rows = session.execute(text("""
        SELECT e.id, e.event_at_utc, e.event_type, e.triggered_by,
               e.payload_json, e.trade_id,
               t.underlying, t.strategy_name
        FROM options_trade_lifecycle_event e
        LEFT JOIN options_paper_trade t ON t.id = e.trade_id
        WHERE e.event_at_utc >= :since
        ORDER BY e.event_at_utc DESC
        LIMIT :n
    """), {"since": since, "n": limit}).mappings().all()
    out: list[TimelineEntry] = []
    for r in rows:
        ev = str(r["event_type"])
        title = LIFECYCLE_TITLE.get(ev, ev.replace("_", " ").lower().title())
        out.append(_row_to_entry(
            source="lifecycle",
            row_id=int(r["id"]),
            entry_type=LIFECYCLE_TYPE.get(ev, "lifecycle_mtm"),
            entry_at_utc=r["event_at_utc"],
            underlying=str(r["underlying"]) if r["underlying"] else "",
            title=f"{title} · {r['underlying'] or ''}".strip(" ·"),
            summary=f"Triggered by {r['triggered_by']}.",
            importance=LIFECYCLE_IMPORTANCE.get(ev, "low"),
            trade_id=int(r["trade_id"]) if r["trade_id"] else None,
            strategy_name=(
                str(r["strategy_name"]) if r["strategy_name"] else None
            ),
            diagnostics={
                "event_type":   ev,
                "triggered_by": str(r["triggered_by"]),
                "payload":      r["payload_json"] or {},
            },
        ))
    return out


def fetch_timeline(
    session: Session, *,
    lookback_days: int = 14,
    underlying: str | None = None,
    entry_types: list[str] | None = None,
    limit: int = 200,
) -> list[TimelineEntry]:
    """Compose the unified DESC-ordered journal timeline.

    `entry_types` filter is applied AFTER merging, so the per-source
    SQL stays simple and cacheable.
    """
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=lookback_days)
    per_source = max(20, limit)

    all_entries: list[TimelineEntry] = []
    all_entries.extend(_fetch_shadow_observations(session, since=since, limit=per_source))
    all_entries.extend(_fetch_candidates(session, since=since, limit=per_source))
    all_entries.extend(_fetch_trades(session, since=since, limit=per_source))
    all_entries.extend(_fetch_lifecycle(session, since=since, limit=per_source))

    # Filters
    if underlying:
        u = underlying.upper()
        all_entries = [e for e in all_entries if e.underlying.upper() == u]
    if entry_types:
        tset = set(entry_types)
        all_entries = [e for e in all_entries if e.entry_type in tset]

    # Sort DESC by entry_at_utc, secondary by importance.
    importance_rank = {"high": 0, "medium": 1, "low": 2}
    all_entries.sort(
        key=lambda e: (-e.entry_at_utc.timestamp(),
                       importance_rank.get(e.importance, 3)),
    )
    return all_entries[:limit]


def timeline_entry_to_dict(e: TimelineEntry) -> dict[str, Any]:
    return {
        "entry_id":       e.entry_id,
        "entry_type":     e.entry_type,
        "entry_at_utc":   e.entry_at_utc.isoformat() if e.entry_at_utc else None,
        "underlying":     e.underlying,
        "title":          e.title,
        "summary":        e.summary,
        "importance":     e.importance,
        "trade_id":       e.trade_id,
        "candidate_id":   e.candidate_id,
        "observation_id": e.observation_id,
        "strategy_name":  e.strategy_name,
        "diagnostics":    e.diagnostics,
    }


# ---------------------------------------------------------------------------
# Per-trade thesis evolution
# ---------------------------------------------------------------------------


def trade_evolution(
    session: Session, trade_id: int,
) -> dict[str, Any] | None:
    """Per-trade narrative: candidates that proposed this trade,
    lifecycle history, current state, related catalyst."""
    trade = session.execute(text("""
        SELECT id, underlying, strategy_name, status,
               opened_at, closed_at,
               entry_credit_dollars, realized_pnl_dollars,
               max_loss_dollars, max_profit_dollars,
               breakeven_lower, breakeven_upper, proposal_hash
        FROM options_paper_trade WHERE id = :tid
    """), {"tid": trade_id}).mappings().first()
    if trade is None:
        return None

    # Related candidates (best-effort by underlying + strategy)
    related_candidates = session.execute(text("""
        SELECT id, rule_id, bias, composite_score,
               why_emitted, triggering_rule, run_date,
               earliest_event_type, earliest_event_date, event_days_away,
               strategy_fit_reason
        FROM options_strategy_candidate
        WHERE underlying = :u AND rule_id = :s
          AND run_date >= (
            CASE WHEN :opened IS NOT NULL THEN (:opened)::date - 3
                 ELSE CURRENT_DATE - 7 END
          )
        ORDER BY run_date DESC, composite_score DESC NULLS LAST
        LIMIT 5
    """), {
        "u": str(trade["underlying"]),
        "s": str(trade["strategy_name"]),
        "opened": trade["opened_at"],
    }).mappings().all()

    # Full lifecycle event history
    events = session.execute(text("""
        SELECT id, event_at_utc, event_type, triggered_by, payload_json
        FROM options_trade_lifecycle_event
        WHERE trade_id = :tid
        ORDER BY event_at_utc ASC
    """), {"tid": trade_id}).mappings().all()

    return {
        "trade": {
            "trade_id":             int(trade["id"]),
            "underlying":           str(trade["underlying"]),
            "strategy_name":        str(trade["strategy_name"]),
            "status":               str(trade["status"]),
            "opened_at":            trade["opened_at"].isoformat() if trade["opened_at"] else None,
            "closed_at":            trade["closed_at"].isoformat() if trade["closed_at"] else None,
            "entry_credit_dollars": _to_float(trade["entry_credit_dollars"]),
            "realized_pnl_dollars": _to_float(trade["realized_pnl_dollars"]),
            "max_loss_dollars":     _to_float(trade["max_loss_dollars"]),
            "max_profit_dollars":   _to_float(trade["max_profit_dollars"]),
            "breakeven_lower":      _to_float(trade["breakeven_lower"]),
            "breakeven_upper":      _to_float(trade["breakeven_upper"]),
            "proposal_hash":        (
                str(trade["proposal_hash"])
                if trade["proposal_hash"] else None
            ),
        },
        "originating_candidates": [
            {
                "candidate_id":      int(c["id"]),
                "rule_id":           str(c["rule_id"]),
                "bias":              str(c["bias"]),
                "composite_score":   _to_float(c["composite_score"]),
                "why_emitted":       str(c["why_emitted"]),
                "triggering_rule":   str(c["triggering_rule"]),
                "run_date":          c["run_date"].isoformat() if c["run_date"] else None,
                "strategy_fit_reason": (
                    str(c["strategy_fit_reason"])
                    if c["strategy_fit_reason"] else None
                ),
                "earliest_event_type": (
                    str(c["earliest_event_type"])
                    if c["earliest_event_type"] else None
                ),
                "earliest_event_date": (
                    c["earliest_event_date"].isoformat()
                    if c["earliest_event_date"] else None
                ),
                "event_days_away":   c["event_days_away"],
            } for c in related_candidates
        ],
        "lifecycle_events": [
            {
                "event_id":     int(e["id"]),
                "event_at_utc": e["event_at_utc"].isoformat(),
                "event_type":   str(e["event_type"]),
                "triggered_by": str(e["triggered_by"]),
                "payload":      e["payload_json"] or {},
            } for e in events
        ],
        "summary": {
            "candidates_seen": len(related_candidates),
            "lifecycle_steps": len(events),
            "current_status":  str(trade["status"]),
        },
    }
