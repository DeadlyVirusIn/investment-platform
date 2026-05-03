"""Code-level gate inventory + diagnostic.

Single source of truth — every UI label and engine arming check reads from
`GATE_DEFS`. Keeps hero count + selector count in lockstep.

Gates come from `context_values` written by the daily paper pipeline's
selector (`apps/api/src/data/strategy/selector.py`). This module only
EXPOSES them; it does not re-derive them to avoid silent divergence.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class GateDef:
    gate_id: str
    name: str
    input_field: str                 # key inside context_values
    plain_english: str
    what_makes_pass: str
    source: str


GATE_DEFS: list[GateDef] = [
    GateDef(
        gate_id="rates_calm",
        name="Rates environment",
        input_field="rates_calm",
        plain_english="Interest-rate conditions are not spiking.",
        what_makes_pass="10Y yield 5-day change below stress threshold.",
        source="context_daily (FRED DGS10)",
    ),
    GateDef(
        gate_id="vrp_supportive",
        name="Volatility premium",
        input_field="vrp_supportive",
        plain_english="Implied vs realized vol spread is constructive.",
        what_makes_pass="VIX minus 20d realized vol above threshold.",
        source="context_daily (VIX / realized)",
    ),
    GateDef(
        gate_id="credit_stable",
        name="Credit spreads",
        input_field="credit_stable",
        plain_english="Corporate credit market showing no stress.",
        what_makes_pass="HY OAS below stress level or HYG trend stable.",
        source="context_daily (BAMLH0A0HYM2 / HYG)",
    ),
    GateDef(
        gate_id="liquidity_expanding",
        name="Market liquidity",
        input_field="liquidity_expanding",
        plain_english="Bank reserves / liquidity proxies rising.",
        what_makes_pass="WALCL 20d change above threshold.",
        source="context_daily (FRED WALCL)",
    ),
]


@dataclass
class GateStatus:
    gate_id: str
    name: str
    status: str                      # pass | fail | unknown | stale
    current_value: Any
    required: str
    source: str
    last_updated: str | None
    reason: str
    plain_english: str
    what_would_make_it_pass: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "name": self.name,
            "status": self.status,
            "current_value": self.current_value,
            "required": self.required,
            "source": self.source,
            "last_updated": self.last_updated,
            "reason": self.reason,
            "plain_english": self.plain_english,
            "what_would_make_it_pass": self.what_would_make_it_pass,
        }


@dataclass
class EngineArmingStatus:
    engine: str
    status: str                      # armed | not_armed | disabled
    missing_gates: list[str]
    plain_english: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "status": self.status,
            "missing_gates": list(self.missing_gates),
            "plain_english": self.plain_english,
        }


def build_gate_status(session: Session) -> dict[str, Any]:
    """Compose full gate diagnostic payload for /api/gates/status."""
    # stress_regime/directional_regime/fire all live inside context_values
    # jsonb on decision_log — never stored as dedicated columns.
    row = session.execute(text("""
        SELECT as_of_date, context_values, decision_ts, engine,
               (action = 'enter_long') AS fire,
               reason
        FROM decision_log
        ORDER BY decision_ts DESC
        LIMIT 1
    """)).mappings().first()
    if row is None:
        return _empty_payload()

    ctx = row.get("context_values") or {}
    # Hydrate regime flags from context_values so downstream code can
    # keep reading row[...] unchanged.
    row = dict(row)
    row["stress_regime"]      = bool(ctx.get("stress_regime"))
    row["directional_regime"] = bool(ctx.get("directional_regime"))
    as_of = row["as_of_date"].isoformat() if row.get("as_of_date") else None
    last_updated = (
        row["decision_ts"].isoformat() if row.get("decision_ts") else None
    )
    stale = _is_stale(row.get("decision_ts"))

    gates: list[GateStatus] = []
    passing = 0
    failing = 0
    for g in GATE_DEFS:
        val = ctx.get(g.input_field)
        if val is None:
            status = "unknown"
            reason = "value missing from context_values"
        elif stale:
            status = "stale"
            reason = f"last updated {last_updated} — treat as unknown"
        elif bool(val):
            status = "pass"
            reason = "condition aligned"
            passing += 1
        else:
            status = "fail"
            reason = "condition not aligned"
            failing += 1
        gates.append(GateStatus(
            gate_id=g.gate_id, name=g.name,
            status=status, current_value=val,
            required="true",
            source=g.source,
            last_updated=last_updated,
            reason=reason,
            plain_english=g.plain_english,
            what_would_make_it_pass=g.what_makes_pass,
        ))

    engine_state = "firing" if row.get("fire") else "none_armed"
    next_action = _next_action(ctx, row)

    arming = _engine_arming(ctx, row)

    return {
        "as_of": as_of,
        "last_updated": last_updated,
        "summary": {
            "passing": passing,
            "failing": failing,
            "total":   len(GATE_DEFS),
            "engine_state": engine_state,
            "next_action":  next_action,
        },
        "gates":         [g.to_dict() for g in gates],
        "engine_arming": [e.to_dict() for e in arming],
    }


# ---------------------------------------------------------------------------

def _is_stale(ts: dt.datetime | None, *, tolerance_hours: int = 48) -> bool:
    if ts is None:
        return True
    now = dt.datetime.now(dt.timezone.utc)
    age_hrs = (now - ts).total_seconds() / 3600.0
    return age_hrs > tolerance_hours


def _next_action(ctx: dict[str, Any], row: dict[str, Any]) -> str:
    missing = [g.gate_id for g in GATE_DEFS if ctx.get(g.input_field) is False]
    if not missing:
        return "conditions_aligned"
    return "await_" + "_".join(missing[:2])


def _engine_arming(
    ctx: dict[str, Any], row: dict[str, Any],
) -> list[EngineArmingStatus]:
    credit_ok = ctx.get("credit_stable") is True
    rates_ok  = ctx.get("rates_calm") is True
    vrp_ok    = ctx.get("vrp_supportive") is True
    liq_ok    = ctx.get("liquidity_expanding") is True
    stress    = bool(row.get("stress_regime"))
    directional = bool(row.get("directional_regime"))

    # Engine A — stress-regime mean reversion
    a_missing: list[str] = []
    if not stress:
        a_missing.append("stress_regime")
    a_status = (
        "armed" if stress and row.get("engine") == "A" and row.get("fire")
        else "not_armed"
    )
    a = EngineArmingStatus(
        engine="Engine A",
        status=a_status,
        missing_gates=a_missing,
        plain_english=(
            "Engine A is armed." if a_status == "armed"
            else "Engine A waits for stress regime + oversold setup."
        ),
    )

    # Engine B — directional + credit + rates
    b_missing: list[str] = []
    if not directional:       b_missing.append("directional_regime")
    if not credit_ok:         b_missing.append("credit_stable")
    if not rates_ok:          b_missing.append("rates_calm")
    b_status = (
        "armed" if not b_missing and row.get("engine") == "B"
                   and row.get("fire")
        else "not_armed"
    )
    if b_missing:
        parts = []
        if "credit_stable" in b_missing: parts.append("credit")
        if "rates_calm"    in b_missing: parts.append("rates")
        if "directional_regime" in b_missing:
            parts.append("a directional regime")
        plain_b = "Engine B is waiting for " + " + ".join(parts) + "."
    else:
        plain_b = "Engine B is armed." if b_status == "armed" \
                  else "Engine B conditions aligned but not yet fired."
    b = EngineArmingStatus(
        engine="Engine B",
        status=b_status,
        missing_gates=b_missing,
        plain_english=plain_b,
    )

    # Engine C — ML candidate
    c = EngineArmingStatus(
        engine="Engine C",
        status="disabled",
        missing_gates=["insufficient_ml_data"],
        plain_english="Engine C disabled until enough data is collected.",
    )
    return [a, b, c]


def _empty_payload() -> dict[str, Any]:
    return {
        "as_of": None,
        "last_updated": None,
        "summary": {
            "passing": 0, "failing": 0, "total": len(GATE_DEFS),
            "engine_state": "unknown",
            "next_action": "await_first_pipeline_run",
        },
        "gates": [{
            "gate_id": g.gate_id, "name": g.name, "status": "unknown",
            "current_value": None, "required": "true",
            "source": g.source, "last_updated": None,
            "reason": "no decision_log rows yet",
            "plain_english": g.plain_english,
            "what_would_make_it_pass": g.what_makes_pass,
        } for g in GATE_DEFS],
        "engine_arming": [],
    }
