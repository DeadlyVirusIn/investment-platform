"""Replay ↔ real decision comparator.

Joins replay decisions with real decision_log rows on (as_of_date, symbol,
engine-optional). Quantifies agreement across actions, engines, regime,
confidence, catalyst availability, feature confidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class ComparisonResult:
    run_id: str
    comparable_decisions: int
    unmatched_real: int
    unmatched_replay: int
    action_agreement_rate: float
    engine_agreement_rate: float
    avg_confidence_delta: float
    regime_agreement_rate: float
    catalyst_presence_agreement_rate: float
    feature_confidence_delta: float
    replay_missing_rate: float
    real_missing_rate: float
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "comparable_decisions": self.comparable_decisions,
            "unmatched_real_decisions": self.unmatched_real,
            "unmatched_replay_decisions": self.unmatched_replay,
            "action_agreement_rate": _r(self.action_agreement_rate),
            "engine_agreement_rate": _r(self.engine_agreement_rate),
            "avg_confidence_delta":  _r(self.avg_confidence_delta, 6),
            "regime_agreement_rate": _r(self.regime_agreement_rate),
            "catalyst_presence_agreement_rate":
                _r(self.catalyst_presence_agreement_rate),
            "feature_confidence_delta": _r(self.feature_confidence_delta, 6),
            "replay_missing_rate": _r(self.replay_missing_rate),
            "real_missing_rate": _r(self.real_missing_rate),
            "warnings": list(self.warnings),
        }


def compare_replay_to_real(
    session: Session, run_id: str,
) -> ComparisonResult:
    """Build per-decision comparison between replay + real logs."""
    replay = _load_replay(session, run_id)
    if replay.empty:
        return ComparisonResult(
            run_id=run_id,
            comparable_decisions=0,
            unmatched_real=0, unmatched_replay=0,
            action_agreement_rate=0.0,
            engine_agreement_rate=0.0,
            avg_confidence_delta=0.0,
            regime_agreement_rate=0.0,
            catalyst_presence_agreement_rate=0.0,
            feature_confidence_delta=0.0,
            replay_missing_rate=0.0,
            real_missing_rate=1.0,
            warnings=["no replay decisions in this run"],
        )
    asofs = replay["as_of_date"].unique().tolist()
    syms = replay["symbol"].unique().tolist()
    real = _load_real(session, asofs=asofs, symbols=syms)

    # Left join replay on real; also compute unmatched reals (reverse)
    merged = replay.merge(
        real, how="outer",
        left_on=["as_of_date", "symbol"],
        right_on=["as_of_date", "instrument"],
        suffixes=("_replay", "_real"),
        indicator=True,
    )
    only_replay = merged["_merge"] == "left_only"
    only_real   = merged["_merge"] == "right_only"
    matched     = merged["_merge"] == "both"

    unmatched_real   = int(only_real.sum())
    unmatched_replay = int(only_replay.sum())
    comparable = int(matched.sum())

    m = merged[matched]

    action_agree = (
        (m["decision_replay"] == m["action"]).mean()
        if comparable else 0.0
    )
    engine_agree = (
        (m["engine_replay"] == m["engine_real"]).mean()
        if comparable else 0.0
    )
    conf_delta = (
        float((m["confidence_replay"].astype(float)
               - m["feature_confidence"].astype(float)).abs().mean())
        if comparable else 0.0
    )
    regime_agree = _regime_agreement_series(m) if comparable else 0.0
    catalyst_agree = _catalyst_presence_series(m) if comparable else 0.0
    fc_delta = (
        float((m["data_conf_replay"].astype(float)
               - m["feature_confidence"].astype(float)).abs().mean())
        if comparable else 0.0
    )
    replay_missing = (
        float((m["data_conf_replay"].astype(float) < 0.3).mean())
        if comparable else 0.0
    )
    real_missing = (
        float((m["feature_confidence"].astype(float) < 0.3).mean())
        if comparable else 0.0
    )

    warnings: list[str] = []
    if comparable < 100:
        warnings.append(
            f"only {comparable} comparable decisions (< 100 preferred)"
        )
    if action_agree < 0.85 and comparable > 0:
        warnings.append(
            f"action agreement {action_agree:.0%} < 85% gate"
        )
    if conf_delta > 0.15 and comparable > 0:
        warnings.append(
            f"confidence delta {conf_delta:.3f} > 0.15 gate"
        )

    return ComparisonResult(
        run_id=run_id,
        comparable_decisions=comparable,
        unmatched_real=unmatched_real,
        unmatched_replay=unmatched_replay,
        action_agreement_rate=float(action_agree),
        engine_agreement_rate=float(engine_agree),
        avg_confidence_delta=conf_delta,
        regime_agreement_rate=regime_agree,
        catalyst_presence_agreement_rate=catalyst_agree,
        feature_confidence_delta=fc_delta,
        replay_missing_rate=replay_missing,
        real_missing_rate=real_missing,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
def _load_replay(session: Session, run_id: str) -> pd.DataFrame:
    rows = session.execute(text("""
        SELECT as_of_date, symbol, engine AS engine,
               decision, confidence,
               data_quality, catalyst, regime
        FROM ml_replay_decision
        WHERE replay_run_id = :r
    """), {"r": run_id}).mappings().all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.normalize()
    df["confidence_replay"] = pd.to_numeric(df["confidence"], errors="coerce")
    df["engine_replay"] = df["engine"]
    df["decision_replay"] = df["decision"]
    df["data_conf_replay"] = df["data_quality"].apply(
        lambda v: _nested(v, "confidence", default=0.0),
    )
    df["regime_stress_replay"] = df["regime"].apply(
        lambda v: int(bool(_nested(v, "stress_regime"))),
    )
    df["regime_directional_replay"] = df["regime"].apply(
        lambda v: int(bool(_nested(v, "directional_regime"))),
    )
    df["catalyst_has_replay"] = df["catalyst"].apply(
        lambda v: 0 if bool(_nested(v, "partial", default=True)) else 1,
    )
    return df.drop(columns=["data_quality", "catalyst", "regime"])


def _load_real(
    session: Session, *,
    asofs: list[Any], symbols: list[str],
) -> pd.DataFrame:
    if not asofs or not symbols:
        return pd.DataFrame()
    rows = session.execute(text("""
        SELECT as_of_date, instrument, engine, action, feature_confidence,
               context_values, catalyst, data_quality
        FROM decision_log
        WHERE instrument = ANY(:syms)
          AND as_of_date = ANY(:asofs)
    """), {
        "syms":  [s.upper() for s in symbols],
        "asofs": [pd.to_datetime(a).date() for a in asofs],
    }).mappings().all()
    if not rows:
        return pd.DataFrame(columns=[
            "as_of_date", "instrument", "engine", "action",
            "feature_confidence", "regime_stress_real",
            "regime_directional_real", "catalyst_has_real",
        ])
    df = pd.DataFrame(rows)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.normalize()
    df["engine_real"] = df["engine"]
    df["feature_confidence"] = pd.to_numeric(
        df["feature_confidence"], errors="coerce",
    )
    df["regime_stress_real"] = df["context_values"].apply(
        lambda v: int(bool(_nested(v, "stress_regime"))),
    )
    df["regime_directional_real"] = df["context_values"].apply(
        lambda v: int(bool(_nested(v, "directional_regime"))),
    )
    df["catalyst_has_real"] = df["catalyst"].apply(
        lambda v: 0 if bool(_nested(v, "partial", default=True)) else 1,
    )
    return df.drop(columns=["context_values", "catalyst", "data_quality"])


def _regime_agreement_series(m: pd.DataFrame) -> float:
    stress = (m["regime_stress_replay"] == m["regime_stress_real"])
    direc = (m["regime_directional_replay"] == m["regime_directional_real"])
    return float((stress & direc).mean())


def _catalyst_presence_series(m: pd.DataFrame) -> float:
    return float(
        (m["catalyst_has_replay"] == m["catalyst_has_real"]).mean()
    )


def _nested(blob: Any, *keys: str, default: Any = None) -> Any:
    if blob is None:
        return default
    if isinstance(blob, str):
        try:
            blob = json.loads(blob)
        except (TypeError, ValueError):
            return default
    v = blob
    for k in keys:
        if isinstance(v, dict):
            v = v.get(k)
        else:
            return default
    return v if v is not None else default


def _r(x: float, d: int = 4) -> float:
    try:
        return round(float(x), d)
    except (TypeError, ValueError):
        return 0.0
