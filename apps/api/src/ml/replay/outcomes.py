"""Forward-only label generation for replay decisions."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.ml.replay.point_in_time import PointInTimeDataAccessor

DEFAULT_HORIZONS = (1, 3, 5, 10)


@dataclass
class OutcomeRow:
    replay_decision_id: str
    label_horizon: int
    entry_price: float | None
    exit_price:  float | None
    forward_return: float | None
    max_adverse:   float | None
    max_favorable: float | None
    win_label: bool | None
    label_start_date: dt.date | None
    label_end_date:   dt.date | None


def label_outcomes_for_run(
    session: Session,
    run_id: str,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    persist: bool = True,
    bar_symbol_map: dict[str, str] | None = None,
) -> list[OutcomeRow]:
    """Compute + persist forward labels for all decisions in a replay run."""
    decisions = session.execute(text("""
        SELECT id::text AS id, as_of_date, symbol
        FROM ml_replay_decision
        WHERE replay_run_id = :run
        ORDER BY as_of_date ASC
    """), {"run": run_id}).mappings().all()
    if not decisions:
        return []

    pit = PointInTimeDataAccessor(session, bar_symbol_map=bar_symbol_map)
    out: list[OutcomeRow] = []
    for d in decisions:
        rows = _labels_for_decision(
            pit=pit, decision_id=d["id"],
            symbol=d["symbol"], as_of=d["as_of_date"],
            horizons=horizons,
        )
        out.extend(rows)
        if persist:
            for r in rows:
                session.execute(text("""
                    INSERT INTO ml_replay_outcome
                      (replay_decision_id, label_horizon, entry_price,
                       exit_price, forward_return, max_adverse,
                       max_favorable, win_label, label_start_date,
                       label_end_date)
                    VALUES
                      (:did, :h, :ent, :ex, :ret, :mae, :mfe, :win,
                       :sd, :ed)
                """), {
                    "did": r.replay_decision_id,
                    "h":   r.label_horizon,
                    "ent": r.entry_price,
                    "ex":  r.exit_price,
                    "ret": r.forward_return,
                    "mae": r.max_adverse,
                    "mfe": r.max_favorable,
                    "win": r.win_label,
                    "sd":  r.label_start_date,
                    "ed":  r.label_end_date,
                })
    if persist:
        session.commit()
    return out


def _labels_for_decision(
    *, pit: PointInTimeDataAccessor,
    decision_id: str, symbol: str, as_of: dt.date,
    horizons: tuple[int, ...],
) -> list[OutcomeRow]:
    out: list[OutcomeRow] = []
    # Entry close = close on as_of_date (or most recent prior bar)
    entry_bar = pit.get_bar_on_or_before(symbol, as_of=as_of)
    if entry_bar is None or entry_bar.close is None:
        for h in horizons:
            out.append(_empty_row(decision_id, h))
        return out
    max_h = max(horizons)
    forward = pit.get_forward_bars(
        symbol, after=as_of, horizon_days=max_h,
    )
    for h in horizons:
        if forward is None or forward.empty or len(forward) < h:
            out.append(_empty_row(decision_id, h, entry_price=entry_bar.close))
            continue
        window = forward.iloc[:h]
        exit_close = _float(window["close"].iloc[-1])
        fwd_ret = (
            (exit_close / entry_bar.close) - 1.0
            if exit_close and entry_bar.close else None
        )
        lows = pd.to_numeric(window["low"], errors="coerce").dropna()
        highs = pd.to_numeric(window["high"], errors="coerce").dropna()
        mae = ((lows.min() / entry_bar.close) - 1.0
               if not lows.empty and entry_bar.close else None)
        mfe = ((highs.max() / entry_bar.close) - 1.0
               if not highs.empty and entry_bar.close else None)
        out.append(OutcomeRow(
            replay_decision_id=decision_id,
            label_horizon=h,
            entry_price=entry_bar.close,
            exit_price=exit_close,
            forward_return=fwd_ret,
            max_adverse=float(mae) if mae is not None else None,
            max_favorable=float(mfe) if mfe is not None else None,
            win_label=(fwd_ret > 0.0) if fwd_ret is not None else None,
            label_start_date=window["date"].iloc[0],
            label_end_date=window["date"].iloc[-1],
        ))
    return out


def _empty_row(
    decision_id: str, horizon: int,
    entry_price: float | None = None,
) -> OutcomeRow:
    return OutcomeRow(
        replay_decision_id=decision_id,
        label_horizon=horizon,
        entry_price=entry_price,
        exit_price=None, forward_return=None,
        max_adverse=None, max_favorable=None,
        win_label=None,
        label_start_date=None, label_end_date=None,
    )


def _float(v: Any) -> float | None:
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None
