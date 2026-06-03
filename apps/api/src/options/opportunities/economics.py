"""Phase C Stage 2B — read-side economics derivation from persisted legs.

Reads `options_candidate_leg` (the EXACT legs the generator selected in
Stage 2A) and runs them through the existing pure risk calculator
(`apps.api.src.options.paper.strategies.compute_risk`). Produces a per-
candidate economics object: max_profit, max_risk, capital_at_risk,
breakeven(s), net_credit/debit, priced_as_of.

Discipline:
  * READ-ONLY. No reconstruction, no leg re-selection, no candidate
    mutation, no generator/threshold/ranking change.
  * economics is None when legs are missing, incomplete (wrong count for
    the structure), unpriced, or the metric computation raises.
  * POP stays reserved (null).
  * Reuses compute_risk verbatim — no new risk math here.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.options.opportunities.assignment import assess_assignment_risk
from apps.api.src.options.paper.strategies import (
    LegSpec,
    compute_risk,
    net_credit_dollars,
    STRATEGY_SHORT_PUT_CREDIT_SPREAD,
    STRATEGY_SHORT_CALL_CREDIT_SPREAD,
    STRATEGY_IRON_CONDOR,
)

# Required leg count per engine-executable structure. Anything else (or a
# mismatch) → incomplete → economics None.
EXPECTED_LEGS: dict[str, int] = {
    STRATEGY_SHORT_PUT_CREDIT_SPREAD: 2,
    STRATEGY_SHORT_CALL_CREDIT_SPREAD: 2,
    STRATEGY_IRON_CONDOR: 4,
}


def fetch_legs_by_candidate(
    session: Session, candidate_ids: list[int],
) -> dict[int, list[dict]]:
    """Batch-load persisted legs for the given candidates. Read-only."""
    ids = [int(c) for c in {*candidate_ids} if c]
    if not ids:
        return {}
    rows = session.execute(text(
        """
        SELECT candidate_id, role, side, option_type, strike, expiry,
               option_symbol, entry_mid, delta, priced_as_of
        FROM options_candidate_leg
        WHERE candidate_id = ANY(:ids)
        ORDER BY candidate_id, role
        """
    ), {"ids": ids}).mappings().all()
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(int(r["candidate_id"]), []).append(dict(r))
    return out


def _dec(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def compute_economics(strategy_name: str, legs: list[dict]) -> dict | None:
    """Derive the economics object from persisted legs, or None when it
    cannot be computed truthfully. Never raises."""
    expected = EXPECTED_LEGS.get(strategy_name)
    if expected is None:
        return None                       # not engine-executable
    if not legs or len(legs) != expected:
        return None                       # missing / incomplete
    try:
        leg_specs: list[LegSpec] = []
        fills: list[Decimal] = []
        priced: list[Any] = []
        for lg in legs:
            mid = _dec(lg.get("entry_mid"))
            strike = _dec(lg.get("strike"))
            if mid is None or strike is None:
                return None               # unpriced leg → cannot compute
            leg_specs.append(LegSpec(
                side=str(lg["side"]),
                option_type=str(lg["option_type"]),
                strike=strike,
                expiry=lg["expiry"],
                qty=1,
                option_symbol=str(lg.get("option_symbol") or ""),
            ))
            fills.append(mid)
            if lg.get("priced_as_of") is not None:
                priced.append(lg["priced_as_of"])

        rm = compute_risk(strategy_name, leg_specs, fills)
        net = net_credit_dollars(leg_specs, fills)   # >0 credit, <0 debit
        paf = max(priced) if priced else None
        return {
            "max_profit": float(rm.max_profit_dollars),
            "max_risk": float(rm.max_loss_dollars),
            "capital_at_risk": float(rm.max_loss_dollars),
            "breakeven_lower": (
                float(rm.breakeven_lower) if rm.breakeven_lower is not None else None
            ),
            "breakeven_upper": (
                float(rm.breakeven_upper) if rm.breakeven_upper is not None else None
            ),
            "net_credit": float(net) if net >= 0 else None,
            "net_debit": float(-net) if net < 0 else None,
            "priced_as_of": paf.isoformat() if hasattr(paf, "isoformat") else (
                str(paf) if paf is not None else None
            ),
            "pop": None,                  # reserved — Stage 2C+ probability model
            "basis": "per_contract",
            "legs_complete": True,
        }
    except Exception:  # noqa: BLE001 — any compute failure → omit, never fake
        return None


def _iso(v: Any) -> str | None:
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def project_legs(legs: list[dict]) -> list[dict]:
    """JSON-safe projection of persisted legs for display (read-only). Sorted
    by option_type then strike. Only persisted fields — nothing fabricated."""
    out: list[dict] = []
    for lg in sorted(
        legs,
        key=lambda x: ((x.get("option_type") or ""), float(x.get("strike") or 0)),
    ):
        strike = _dec(lg.get("strike"))
        mid = _dec(lg.get("entry_mid"))
        delta = _dec(lg.get("delta"))
        out.append({
            "role": lg.get("role"),
            "side": lg.get("side"),
            "option_type": lg.get("option_type"),
            "strike": float(strike) if strike is not None else None,
            "expiry": _iso(lg.get("expiry")),
            "entry_mid": float(mid) if mid is not None else None,
            "delta": float(delta) if delta is not None else None,
            "priced_as_of": _iso(lg.get("priced_as_of")),
        })
    return out


def attach_economics(session: Session, items: list) -> None:
    """Set `item.economics` and `item.legs` for each opportunity item, in
    place. economics None when legs absent/incomplete/uncomputable; legs is
    the persisted-leg projection (empty list when none)."""
    if not items:
        return
    legs_by = fetch_legs_by_candidate(
        session, [getattr(it, "candidate_id", 0) for it in items],
    )
    for it in items:
        raw = legs_by.get(getattr(it, "candidate_id", 0), [])
        it.economics = compute_economics(it.rule_id, raw)
        it.legs = project_legs(raw)
        # Phase F1 — assignment risk from the persisted short-leg delta + DTE.
        it.assignment_risk = assess_assignment_risk(raw, getattr(it, "dte", None))
