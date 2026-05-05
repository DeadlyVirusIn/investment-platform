"""Options strategy outcome scoring — pure functions + writer.

Reads `options_chain_snapshot` only. NEVER fabricates a quote, NEVER
backfills with stock proxies, NEVER uses same-bar fills.

Entry reference (next-bar rule):
  First chain snapshot with `snapshot_at_utc::date > submitted_at::date`
  for each leg's option_symbol.

Exit reference (per horizon):
  First chain snapshot whose `snapshot_at_utc::date >=
  submitted_at::date + horizon_days` for each leg.
  If no such snapshot exists → outcome_label='pending'.
  If entry exists but no qualifying exit → 'pending'.
  If neither side has any future snapshot → 'data_blocked'.

Strategy → "price" mapping for forward returns:
  long_call         → leg[0].mid (buy premium)
  bull_call_spread  → buy.mid − sell.mid (net debit)
  long_put          → leg[0].mid
  bear_put_spread   → buy.mid − sell.mid (net debit)
  call_credit_spread/put_credit_spread/iron_condor →
    sum(side_sign * mid) where SELL contributes positive credit.

Forward return = (exit_ref − entry_ref) / abs(entry_ref).
For debit strategies (positive entry), this is straightforward.
For credit strategies (negative or near-zero entry), abs() keeps the
ratio defined; sign reflects whether the position MTM moved in
operator's favor.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session


HORIZONS: tuple[str, ...] = ("1D", "3D", "5D", "10D", "20D")
HORIZON_DAYS: dict[str, int] = {
    "1D": 1, "3D": 3, "5D": 5, "10D": 10, "20D": 20,
}

# Outcome thresholds — symmetric, conservative defaults.
OUTCOME_GOOD_PCT = 0.01   # +1% net move → good
OUTCOME_BAD_PCT = -0.01

VALID_LABELS = ("good", "neutral", "bad", "pending", "data_blocked")
VALID_SOURCES = ("suggestion", "paper_trade")
VALID_MODES = ("strict", "exploratory", "options_exploratory")


@dataclass
class StrategyInput:
    """One scoring task — a strategy + its leg list at submit time."""
    underlying: str
    strategy_name: str          # uppercase DB enum (LONG_CALL, etc.)
    legs: list[dict[str, Any]]  # [{option_symbol, action, type, strike,
                                #   expiry, bid, ask, mid}]
    as_of_date: dt.date
    submitted_at_utc: dt.datetime
    source: str                 # 'suggestion' | 'paper_trade'
    mode: str                   # 'strict' | 'exploratory' | 'options_exploratory'


@dataclass
class StrategyOutcome:
    underlying: str
    strategy_name: str
    legs_json: list[dict[str, Any]]
    as_of_date: dt.date
    submitted_at_utc: dt.datetime
    horizon: str
    entry_reference: float | None
    exit_reference: float | None
    forward_return_pct: float | None
    mfe_pct: float | None
    mae_pct: float | None
    outcome_label: str
    source: str
    mode: str


def _label_outcome(forward_return: float | None) -> str:
    if forward_return is None:
        return "pending"
    if forward_return >= OUTCOME_GOOD_PCT:
        return "good"
    if forward_return <= OUTCOME_BAD_PCT:
        return "bad"
    return "neutral"


def _strategy_price_from_legs(
    strategy_name: str, leg_quotes: list[dict[str, float]],
) -> float | None:
    """Compute net strategy 'price' from per-leg mid prices.

    Convention:
      * BUY contributes +mid (you paid).
      * SELL contributes -mid (you received).
    Net positive = debit; net negative = credit.

    Returns None if any required leg is missing a mid quote.
    """
    if not leg_quotes:
        return None
    total = 0.0
    for q in leg_quotes:
        mid = q.get("mid")
        if mid is None:
            return None
        side = q.get("side", "BUY").upper()
        if side == "BUY":
            total += float(mid)
        else:
            total -= float(mid)
    return total


def _first_future_snapshot(
    session: Session, option_symbol: str,
    after_date: dt.date,
) -> tuple[dt.datetime, float, float, float] | None:
    """Earliest chain snapshot for `option_symbol` whose
    `snapshot_at_utc::date > after_date`. Returns
    (ts, bid, ask, mid) or None."""
    row = session.execute(text("""
        SELECT snapshot_at_utc, bid, ask, mid
        FROM options_chain_snapshot
        WHERE option_symbol = :s
          AND snapshot_at_utc::date > :d
        ORDER BY snapshot_at_utc ASC
        LIMIT 1
    """), {"s": option_symbol, "d": after_date}).first()
    if row is None or row[1] is None or row[2] is None:
        return None
    bid = float(row[1]); ask = float(row[2])
    mid = (
        float(row[3]) if row[3] is not None else (bid + ask) / 2.0
    )
    return row[0], bid, ask, mid


def _snapshot_at_or_after(
    session: Session, option_symbol: str,
    target_date: dt.date,
) -> tuple[dt.datetime, float, float, float] | None:
    """Earliest chain snapshot for `option_symbol` whose
    `snapshot_at_utc::date >= target_date`. None if missing."""
    row = session.execute(text("""
        SELECT snapshot_at_utc, bid, ask, mid
        FROM options_chain_snapshot
        WHERE option_symbol = :s
          AND snapshot_at_utc::date >= :d
        ORDER BY snapshot_at_utc ASC
        LIMIT 1
    """), {"s": option_symbol, "d": target_date}).first()
    if row is None or row[1] is None or row[2] is None:
        return None
    bid = float(row[1]); ask = float(row[2])
    mid = (
        float(row[3]) if row[3] is not None else (bid + ask) / 2.0
    )
    return row[0], bid, ask, mid


def _scan_window_extremes(
    session: Session, option_symbol: str,
    start_date: dt.date, end_date: dt.date,
    side: str,
) -> tuple[float, float] | None:
    """Min/max mid across snapshots in [start_date, end_date].
    Returns (min_mid, max_mid) or None if window has no rows."""
    rows = session.execute(text("""
        SELECT mid, bid, ask
        FROM options_chain_snapshot
        WHERE option_symbol = :s
          AND snapshot_at_utc::date >= :a
          AND snapshot_at_utc::date <= :b
    """), {"s": option_symbol, "a": start_date, "b": end_date}).all()
    if not rows:
        return None
    mids: list[float] = []
    for r in rows:
        m = r[0]; bid = r[1]; ask = r[2]
        if m is not None:
            mids.append(float(m))
        elif bid is not None and ask is not None:
            mids.append((float(bid) + float(ask)) / 2.0)
    if not mids:
        return None
    return min(mids), max(mids)


def compute_strategy_outcomes(
    session: Session, inputs: Iterable[StrategyInput],
    horizons: tuple[str, ...] = HORIZONS,
    *,
    good_pct: float = OUTCOME_GOOD_PCT,
    bad_pct: float = OUTCOME_BAD_PCT,
) -> list[StrategyOutcome]:
    """Compute outcomes per (strategy_input × horizon)."""
    out: list[StrategyOutcome] = []
    for inp in inputs:
        # Per-leg next-bar entry quote.
        entry_legs: list[dict[str, float]] = []
        any_entry_missing = False
        for leg in inp.legs:
            sym = leg["option_symbol"]
            side = leg["action"].upper()  # 'BUY'/'SELL'
            entry = _first_future_snapshot(
                session, sym, inp.submitted_at_utc.date(),
            )
            if entry is None:
                any_entry_missing = True
                continue
            ts, bid, ask, mid = entry
            entry_legs.append({
                "option_symbol": sym,
                "side": side,
                "mid": mid,
                "ts": ts.isoformat(),
            })
        entry_price = (
            _strategy_price_from_legs(inp.strategy_name, entry_legs)
            if not any_entry_missing else None
        )

        for h in horizons:
            target = inp.submitted_at_utc.date() + dt.timedelta(
                days=HORIZON_DAYS[h]
            )
            exit_legs: list[dict[str, float]] = []
            any_exit_missing = False
            for leg in inp.legs:
                sym = leg["option_symbol"]
                side = leg["action"].upper()
                exit_ = _snapshot_at_or_after(session, sym, target)
                if exit_ is None:
                    any_exit_missing = True
                    continue
                _, bid, ask, mid = exit_
                exit_legs.append({
                    "option_symbol": sym, "side": side, "mid": mid,
                })
            exit_price = (
                _strategy_price_from_legs(inp.strategy_name, exit_legs)
                if not any_exit_missing else None
            )

            # Window MFE/MAE: scan per-leg snapshots between entry and
            # exit dates, recompute strategy net at each timestamp,
            # take min/max of net-vs-entry. Cheap approximation: take
            # min/max of each leg independently then bound the net by
            # the worst-leg-min and best-leg-max combo. Conservative
            # enough; never invents values.
            mfe_pct = None
            mae_pct = None
            if entry_price is not None and entry_price != 0:
                # Per-leg min/max in window.
                mins: list[float] = []
                maxs: list[float] = []
                window_ok = True
                for leg in inp.legs:
                    sym = leg["option_symbol"]
                    side = leg["action"].upper()
                    extremes = _scan_window_extremes(
                        session, sym,
                        inp.submitted_at_utc.date(), target,
                        side,
                    )
                    if extremes is None:
                        window_ok = False
                        break
                    lo, hi = extremes
                    if side == "BUY":
                        mins.append(lo)   # worst is lower premium
                        maxs.append(hi)   # best is higher premium
                    else:
                        # SELL contributes -mid → leg "min" = -hi (bad
                        # for the position when premium rises);
                        # leg "max" = -lo (good when premium falls).
                        mins.append(-hi)
                        maxs.append(-lo)
                if window_ok:
                    worst_net = sum(mins)
                    best_net = sum(maxs)
                    denom = abs(entry_price)
                    if denom > 0:
                        mae_pct = (worst_net - entry_price) / denom
                        mfe_pct = (best_net - entry_price) / denom

            forward_return = None
            if (entry_price is not None and exit_price is not None
                    and entry_price != 0):
                forward_return = (
                    (exit_price - entry_price) / abs(entry_price)
                )

            if entry_price is None and exit_price is None:
                label = "data_blocked"
            elif forward_return is None:
                label = "pending"
            else:
                if forward_return >= good_pct:
                    label = "good"
                elif forward_return <= bad_pct:
                    label = "bad"
                else:
                    label = "neutral"

            out.append(StrategyOutcome(
                underlying=inp.underlying,
                strategy_name=inp.strategy_name,
                legs_json=inp.legs,
                as_of_date=inp.as_of_date,
                submitted_at_utc=inp.submitted_at_utc,
                horizon=h,
                entry_reference=entry_price,
                exit_reference=exit_price,
                forward_return_pct=forward_return,
                mfe_pct=mfe_pct,
                mae_pct=mae_pct,
                outcome_label=label,
                source=inp.source,
                mode=inp.mode,
            ))
    return out


def upsert_outcomes(
    session: Session, outcomes: list[StrategyOutcome],
) -> dict[str, int]:
    """Upsert by natural key (underlying, strategy_name,
    submitted_at_utc, horizon, source). On conflict, recompute fields
    so re-running with fresh future snapshots updates pending rows."""
    inserted = 0
    updated = 0
    for o in outcomes:
        if o.outcome_label not in VALID_LABELS:
            continue
        if o.source not in VALID_SOURCES:
            continue
        if o.mode not in VALID_MODES:
            continue
        res = session.execute(text("""
            INSERT INTO options_strategy_outcome (
                underlying, strategy_name, legs_json,
                as_of_date, submitted_at_utc, horizon,
                entry_reference, exit_reference, forward_return_pct,
                mfe_pct, mae_pct, outcome_label, source, mode
            )
            VALUES (
                :u, :s, CAST(:legs AS jsonb),
                :asof, :sub, :h,
                :er, :xr, :fr, :mfe, :mae, :lbl, :src, :mode
            )
            ON CONFLICT ON CONSTRAINT ux_options_strategy_outcome_natural_key
            DO UPDATE SET
                entry_reference     = EXCLUDED.entry_reference,
                exit_reference      = EXCLUDED.exit_reference,
                forward_return_pct  = EXCLUDED.forward_return_pct,
                mfe_pct             = EXCLUDED.mfe_pct,
                mae_pct             = EXCLUDED.mae_pct,
                outcome_label       = EXCLUDED.outcome_label,
                computed_at_utc     = now()
            RETURNING (xmax = 0) AS was_insert
        """), {
            "u": o.underlying, "s": o.strategy_name,
            "legs": json.dumps(o.legs_json),
            "asof": o.as_of_date, "sub": o.submitted_at_utc,
            "h": o.horizon,
            "er": o.entry_reference, "xr": o.exit_reference,
            "fr": o.forward_return_pct,
            "mfe": o.mfe_pct, "mae": o.mae_pct,
            "lbl": o.outcome_label,
            "src": o.source, "mode": o.mode,
        }).first()
        if res and res[0]:
            inserted += 1
        else:
            updated += 1
    session.commit()
    return {"inserted": inserted, "updated": updated}
