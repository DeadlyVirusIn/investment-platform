"""Phase C Stage 2A — candidate leg materialization + persistence.

Resolves the COMPLETE set of concrete option legs for the three
engine-executable defined-risk structures, priced from a single chain
snapshot, and writes them to `options_candidate_leg`.

  SHORT_PUT_CREDIT_SPREAD  → short put (the engine's accepted strike) +
                             long put at the next listed strike below.
  SHORT_CALL_CREDIT_SPREAD → short call (accepted strike) + long call at
                             the next listed strike above.
  IRON_CONDOR              → the engine's accepted short leg on its side
                             (anchored strike) + the opposite-side short
                             at the existing ~0.30 delta target + 1-strike
                             wings either side.

Discipline (Phase C decisions):
  * Uses ONLY existing selection parameters — the accepted short strike,
    the existing IC short-delta target, the existing 1-strike wing width.
    No new thresholds, no ranking/qualification influence, no wing-width
    change.
  * Pure persistence: returns [] (incomplete) when any required strike is
    not quoted in the snapshot. NEVER raises into the emission path; the
    candidate is emitted/scored upstream regardless.
  * Single snapshot per candidate → consistent `priced_as_of`.

Reads `options_chain_snapshot` (read-only). Writes `options_candidate_leg`
only. No reconstruction is ever used for economics — economics (Stage 2B)
reads exactly these persisted legs.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


RULE_SHORT_PUT_CREDIT_SPREAD = "SHORT_PUT_CREDIT_SPREAD"
RULE_SHORT_CALL_CREDIT_SPREAD = "SHORT_CALL_CREDIT_SPREAD"
RULE_IRON_CONDOR = "IRON_CONDOR"

# Existing IC short-strike target (mirrors generator/service anchor logic).
# This is NOT a new threshold — it is the same ~0.30 delta the IC anchor
# already uses; materialization only makes the contralateral short concrete.
IC_SHORT_DELTA_TARGET = 0.30


@dataclass
class CandidateLeg:
    role: str          # short_put | long_put | short_call | long_call
    side: str          # SELL | BUY
    option_type: str   # PUT | CALL
    strike: float
    expiry: dt.date
    option_symbol: str | None
    entry_bid: float | None
    entry_ask: float | None
    entry_mid: float | None
    delta: float | None
    priced_as_of: dt.datetime


@dataclass
class _Row:
    strike: float
    option_symbol: str | None
    bid: float | None
    ask: float | None
    mid: float | None
    delta: float | None
    priced_as_of: dt.datetime


def _fetch_ladder(
    session: Session, underlying: str, expiry: dt.date, option_type: str,
) -> list[_Row]:
    """Latest-snapshot strike ladder for one underlying/expiry/type,
    ascending by strike. Only rows with a usable mid are returned."""
    rows = session.execute(text(
        """
        SELECT strike, option_symbol, bid, ask, mid, delta, snapshot_at_utc
        FROM options_chain_snapshot
        WHERE underlying = :u AND expiry = :e AND option_type = :ot
          AND snapshot_at_utc = (
            SELECT MAX(snapshot_at_utc) FROM options_chain_snapshot
            WHERE underlying = :u AND expiry = :e AND option_type = :ot)
        ORDER BY strike
        """
    ), {"u": underlying, "e": expiry, "ot": option_type}).mappings().all()
    out: list[_Row] = []
    for r in rows:
        if r["mid"] is None:
            continue
        out.append(_Row(
            strike=float(r["strike"]),
            option_symbol=r["option_symbol"],
            bid=float(r["bid"]) if r["bid"] is not None else None,
            ask=float(r["ask"]) if r["ask"] is not None else None,
            mid=float(r["mid"]) if r["mid"] is not None else None,
            delta=float(r["delta"]) if r["delta"] is not None else None,
            priced_as_of=r["snapshot_at_utc"],
        ))
    return out


def _ladder(
    session: Session, cache: dict, underlying: str, expiry: dt.date,
    option_type: str,
) -> list[_Row]:
    key = (underlying, str(expiry), option_type)
    if key not in cache:
        cache[key] = _fetch_ladder(session, underlying, expiry, option_type)
    return cache[key]


def _leg(row: _Row, role: str, side: str, option_type: str, expiry: dt.date) -> CandidateLeg:
    return CandidateLeg(
        role=role, side=side, option_type=option_type,
        strike=row.strike, expiry=expiry, option_symbol=row.option_symbol,
        entry_bid=row.bid, entry_ask=row.ask, entry_mid=row.mid,
        delta=row.delta, priced_as_of=row.priced_as_of,
    )


def _index_of_strike(ladder: list[_Row], strike: float) -> int:
    for i, r in enumerate(ladder):
        if abs(r.strike - strike) < 1e-9:
            return i
    return -1


def _index_closest_delta(ladder: list[_Row], target: float) -> int:
    best, best_d = -1, None
    for i, r in enumerate(ladder):
        if r.delta is None:
            continue
        d = abs(abs(r.delta) - target)
        if best_d is None or d < best_d:
            best, best_d = i, d
    return best


def _credit_legs(
    session: Session, cache: dict, obs: Any, option_type: str,
) -> list[CandidateLeg]:
    """Short = the engine's accepted strike; long = next listed strike on
    the protective side (1-strike wide). PUT spread protects below; CALL
    spread protects above."""
    ladder = _ladder(session, cache, obs.underlying, obs.expiration, option_type)
    if not ladder:
        return []
    i = _index_of_strike(ladder, float(obs.strike))
    if i < 0:
        return []
    if option_type == "PUT":
        if i - 1 < 0:
            return []
        return [
            _leg(ladder[i], "short_put", "SELL", "PUT", obs.expiration),
            _leg(ladder[i - 1], "long_put", "BUY", "PUT", obs.expiration),
        ]
    # CALL
    if i + 1 >= len(ladder):
        return []
    return [
        _leg(ladder[i], "short_call", "SELL", "CALL", obs.expiration),
        _leg(ladder[i + 1], "long_call", "BUY", "CALL", obs.expiration),
    ]


def _iron_condor_legs(
    session: Session, cache: dict, obs: Any,
) -> list[CandidateLeg]:
    """Anchored short on the accepted side (obs.strike); opposite-side
    short at the existing ~0.30 delta target; 1-strike wings either side."""
    underlying, expiry = obs.underlying, obs.expiration
    anchor_type = (obs.option_type or "").upper()  # 'PUT' | 'CALL'
    puts = _ladder(session, cache, underlying, expiry, "PUT")
    calls = _ladder(session, cache, underlying, expiry, "CALL")
    if not puts or not calls:
        return []

    if anchor_type == "PUT":
        pi = _index_of_strike(puts, float(obs.strike))
        ci = _index_closest_delta(calls, IC_SHORT_DELTA_TARGET)
    elif anchor_type == "CALL":
        ci = _index_of_strike(calls, float(obs.strike))
        pi = _index_closest_delta(puts, IC_SHORT_DELTA_TARGET)
    else:
        pi = _index_closest_delta(puts, IC_SHORT_DELTA_TARGET)
        ci = _index_closest_delta(calls, IC_SHORT_DELTA_TARGET)

    if pi < 0 or ci < 0:
        return []
    if pi - 1 < 0:            # need a put wing below the short put
        return []
    if ci + 1 >= len(calls):  # need a call wing above the short call
        return []

    return [
        _leg(puts[pi], "short_put", "SELL", "PUT", expiry),
        _leg(puts[pi - 1], "long_put", "BUY", "PUT", expiry),
        _leg(calls[ci], "short_call", "SELL", "CALL", expiry),
        _leg(calls[ci + 1], "long_call", "BUY", "CALL", expiry),
    ]


def materialize_legs(
    session: Session, obs: Any, candidate: Any, cache: dict,
) -> list[CandidateLeg]:
    """Resolve the concrete legs for an engine-executable candidate.
    Returns [] for research structures and whenever a required strike is
    not quoted (the candidate is unaffected)."""
    rid = candidate.rule_id
    if rid == RULE_SHORT_PUT_CREDIT_SPREAD:
        return _credit_legs(session, cache, obs, "PUT")
    if rid == RULE_SHORT_CALL_CREDIT_SPREAD:
        return _credit_legs(session, cache, obs, "CALL")
    if rid == RULE_IRON_CONDOR:
        return _iron_condor_legs(session, cache, obs)
    return []


_INSERT_LEG_SQL = text(
    """
    INSERT INTO options_candidate_leg
      (candidate_id, role, side, option_type, strike, expiry,
       option_symbol, entry_bid, entry_ask, entry_mid, delta, priced_as_of)
    VALUES
      (:cid, :role, :side, :otype, :strike, :expiry,
       :osym, :bid, :ask, :mid, :delta, :paf)
    ON CONFLICT ON CONSTRAINT ux_candidate_leg_candidate_role DO NOTHING
    """
)


def insert_legs(session: Session, candidate_id: int, legs: list[CandidateLeg]) -> int:
    """Insert legs for one candidate (same transaction as the candidate).
    Idempotent via UNIQUE(candidate_id, role). Returns rows attempted."""
    for lg in legs:
        session.execute(_INSERT_LEG_SQL, {
            "cid": candidate_id,
            "role": lg.role, "side": lg.side, "otype": lg.option_type,
            "strike": lg.strike, "expiry": lg.expiry,
            "osym": lg.option_symbol,
            "bid": lg.entry_bid, "ask": lg.entry_ask, "mid": lg.entry_mid,
            "delta": lg.delta, "paf": lg.priced_as_of,
        })
    return len(legs)
