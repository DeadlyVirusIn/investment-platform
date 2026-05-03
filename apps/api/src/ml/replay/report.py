"""Per-replay-run report — summary + pattern + comparison to real decisions."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.ml.patterns import discover_patterns


@dataclass
class ReplayReport:
    run_id: str
    n_decisions: int
    n_with_outcomes: int
    date_range: tuple[str, str] | None
    symbols: list[str]
    by_engine: list[dict[str, Any]] = field(default_factory=list)
    accepted_vs_skipped: dict[str, int] = field(default_factory=dict)
    outcomes_by_horizon: list[dict[str, Any]] = field(default_factory=list)
    perf_by_regime: list[dict[str, Any]] = field(default_factory=list)
    perf_by_catalyst_availability: list[dict[str, Any]] = field(default_factory=list)
    perf_by_data_confidence: list[dict[str, Any]] = field(default_factory=list)
    perf_by_symbol: list[dict[str, Any]] = field(default_factory=list)
    patterns: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    real_comparison: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "n_decisions": self.n_decisions,
            "n_with_outcomes": self.n_with_outcomes,
            "date_range": self.date_range,
            "symbols": list(self.symbols),
            "by_engine": self.by_engine,
            "accepted_vs_skipped": self.accepted_vs_skipped,
            "outcomes_by_horizon": self.outcomes_by_horizon,
            "perf_by_regime": self.perf_by_regime,
            "perf_by_catalyst_availability": self.perf_by_catalyst_availability,
            "perf_by_data_confidence": self.perf_by_data_confidence,
            "perf_by_symbol": self.perf_by_symbol,
            "patterns": self.patterns,
            "warnings": self.warnings,
            "real_comparison": self.real_comparison,
        }


def build_replay_report(
    session: Session, run_id: str,
) -> ReplayReport:
    decisions = _load_decisions(session, run_id)
    outcomes = _load_outcomes(session, run_id)
    real_cmp = _compare_to_real(session, decisions, outcomes)

    warnings: list[str] = []
    if decisions.empty:
        return ReplayReport(
            run_id=run_id, n_decisions=0, n_with_outcomes=0,
            date_range=None, symbols=[],
            warnings=["no decisions in this replay run"],
        )

    if outcomes.empty:
        warnings.append("no outcomes yet — call label_outcomes_for_run")

    # Enrich decisions with a flat returns column from horizon=5 outcomes
    joined = _join_with_outcomes(decisions, outcomes, horizon=5)
    n_with = int(joined["forward_return"].notna().sum())

    by_engine = _group_stats(joined, group_col="engine")
    accepted_vs_skipped = {
        "accepted": int((joined["decision"] == "enter_long").sum()),
        "skipped":  int(joined["decision"].isin(["skip", "no_fire"]).sum()),
    }
    outcomes_by_horizon = _outcomes_by_horizon(outcomes)
    perf_by_regime = _group_stats_regime(joined)
    perf_by_cat = _bucket_stats_bool(
        joined, col="catalyst_partial", axis="catalyst_availability",
        true_label="partial_or_missing", false_label="available",
    )
    perf_by_dc = _bucket_stats_numeric(
        joined, col="data_confidence",
        axis="data_confidence", edges=[-0.01, 0.5, 0.75, 1.01],
        labels=["low", "mid", "high"],
    )
    perf_by_sym = _top_symbols(joined, n=10)
    # Pattern sweep
    patterns = (
        discover_patterns(joined, return_col="forward_return").to_dict()
        if n_with > 0 else {}
    )
    if n_with < 100:
        warnings.append(
            f"only {n_with} decisions have outcomes — results directional"
        )
    warnings.extend(_universal_replay_warnings())

    return ReplayReport(
        run_id=run_id,
        n_decisions=int(len(decisions)),
        n_with_outcomes=n_with,
        date_range=_date_range(decisions),
        symbols=sorted(decisions["symbol"].dropna().unique().tolist()),
        by_engine=by_engine,
        accepted_vs_skipped=accepted_vs_skipped,
        outcomes_by_horizon=outcomes_by_horizon,
        perf_by_regime=perf_by_regime,
        perf_by_catalyst_availability=perf_by_cat,
        perf_by_data_confidence=perf_by_dc,
        perf_by_symbol=perf_by_sym,
        patterns=patterns,
        warnings=warnings,
        real_comparison=real_cmp,
    )


# ---------------------------------------------------------------------------
# DB loaders
# ---------------------------------------------------------------------------

def _load_decisions(session: Session, run_id: str) -> pd.DataFrame:
    rows = session.execute(text("""
        SELECT id::text AS decision_id, replay_run_id::text,
               as_of_date, decision_ts, symbol, engine, decision,
               confidence, features, data_quality, catalyst, regime,
               advisory, skip_reason
        FROM ml_replay_decision
        WHERE replay_run_id = :r
        ORDER BY as_of_date ASC, symbol ASC
    """), {"r": run_id}).mappings().all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["data_confidence"] = df["data_quality"].apply(
        lambda v: _get_nested(v, "confidence", default=0.0),
    )
    df["catalyst_partial"] = df["catalyst"].apply(
        lambda v: bool(_get_nested(v, "partial", default=True)),
    )
    df["regime_stress"] = df["regime"].apply(
        lambda v: 1 if _get_nested(v, "stress_regime") else 0,
    )
    df["regime_directional"] = df["regime"].apply(
        lambda v: 1 if _get_nested(v, "directional_regime") else 0,
    )
    df["regime_neutral"] = df["regime"].apply(
        lambda v: 1 if _get_nested(v, "neutral_regime") else 0,
    )
    return df


def _load_outcomes(session: Session, run_id: str) -> pd.DataFrame:
    rows = session.execute(text("""
        SELECT o.replay_decision_id::text AS decision_id,
               o.label_horizon, o.entry_price, o.exit_price,
               o.forward_return, o.max_adverse, o.max_favorable,
               o.win_label, o.label_start_date, o.label_end_date
        FROM ml_replay_outcome o
        JOIN ml_replay_decision d ON d.id = o.replay_decision_id
        WHERE d.replay_run_id = :r
    """), {"r": run_id}).mappings().all()
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _compare_to_real(
    session: Session, decisions: pd.DataFrame, outcomes: pd.DataFrame,
) -> dict[str, Any]:
    if decisions.empty:
        return {"available": False, "reason": "no decisions"}
    row = session.execute(text("""
        SELECT COUNT(*) FROM decision_log
    """)).scalar() or 0
    return {
        "available": True,
        "n_real_decisions": int(row),
        "n_replay_decisions": int(len(decisions)),
        "note": ("replay and real logs compared only in aggregate; "
                 "row-level join not performed"),
    }


# ---------------------------------------------------------------------------
# aggregations
# ---------------------------------------------------------------------------

def _group_stats(
    df: pd.DataFrame, *, group_col: str,
) -> list[dict[str, Any]]:
    if df.empty or group_col not in df.columns:
        return []
    out: list[dict[str, Any]] = []
    for key, g in df.groupby(group_col, dropna=False):
        rets = g["forward_return"].dropna()
        out.append({
            "key": str(key),
            "n": int(len(g)),
            "n_with_return": int(len(rets)),
            "hit_rate": float((rets > 0).mean()) if not rets.empty else 0.0,
            "mean_return": float(rets.mean()) if not rets.empty else 0.0,
        })
    return out


def _group_stats_regime(df: pd.DataFrame) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for col, label in (
        ("regime_stress", "stress"),
        ("regime_directional", "directional"),
        ("regime_neutral", "neutral"),
    ):
        if col in df.columns:
            sub = df[df[col] == 1]
            rets = sub["forward_return"].dropna()
            out.append({
                "regime": label,
                "n": int(len(sub)),
                "n_with_return": int(len(rets)),
                "mean_return": float(rets.mean()) if not rets.empty else 0.0,
                "hit_rate": float((rets > 0).mean()) if not rets.empty else 0.0,
            })
    return out


def _bucket_stats_bool(
    df: pd.DataFrame, *, col: str, axis: str,
    true_label: str, false_label: str,
) -> list[dict[str, Any]]:
    if col not in df.columns or df.empty:
        return []
    out = []
    for lab, mask in ((true_label, df[col].astype(bool)),
                       (false_label, ~df[col].astype(bool))):
        sub = df[mask]
        rets = sub["forward_return"].dropna()
        out.append({
            "axis": axis, "bucket": lab,
            "n": int(len(sub)),
            "n_with_return": int(len(rets)),
            "mean_return": float(rets.mean()) if not rets.empty else 0.0,
            "hit_rate": float((rets > 0).mean()) if not rets.empty else 0.0,
        })
    return out


def _bucket_stats_numeric(
    df: pd.DataFrame, *, col: str, axis: str,
    edges: list[float], labels: list[str],
) -> list[dict[str, Any]]:
    if col not in df.columns or df.empty:
        return []
    bins = pd.cut(df[col], bins=edges, labels=labels, include_lowest=True)
    out: list[dict[str, Any]] = []
    for lab in labels:
        sub = df[bins == lab]
        rets = sub["forward_return"].dropna()
        out.append({
            "axis": axis, "bucket": str(lab),
            "n": int(len(sub)),
            "mean_return": float(rets.mean()) if not rets.empty else 0.0,
            "hit_rate": float((rets > 0).mean()) if not rets.empty else 0.0,
        })
    return out


def _top_symbols(df: pd.DataFrame, *, n: int = 10) -> list[dict[str, Any]]:
    if df.empty or "symbol" not in df.columns:
        return []
    groups = df.groupby("symbol", dropna=False)["forward_return"]
    rows = []
    for sym, g in groups:
        rets = g.dropna()
        rows.append({
            "symbol": str(sym),
            "n": int(len(g)),
            "n_with_return": int(len(rets)),
            "mean_return": float(rets.mean()) if not rets.empty else 0.0,
            "hit_rate": float((rets > 0).mean()) if not rets.empty else 0.0,
        })
    rows.sort(key=lambda r: r["n"], reverse=True)
    return rows[:n]


def _outcomes_by_horizon(outcomes: pd.DataFrame) -> list[dict[str, Any]]:
    if outcomes.empty:
        return []
    out = []
    for h, g in outcomes.groupby("label_horizon"):
        rets = pd.to_numeric(g["forward_return"], errors="coerce").dropna()
        out.append({
            "horizon": int(h),
            "n": int(len(g)),
            "n_with_return": int(len(rets)),
            "mean_return": float(rets.mean()) if not rets.empty else 0.0,
            "hit_rate": float((rets > 0).mean()) if not rets.empty else 0.0,
        })
    out.sort(key=lambda r: r["horizon"])
    return out


def _join_with_outcomes(
    decisions: pd.DataFrame, outcomes: pd.DataFrame, *, horizon: int,
) -> pd.DataFrame:
    if decisions.empty:
        return decisions
    if outcomes.empty:
        decisions = decisions.copy()
        decisions["forward_return"] = np.nan
        return decisions
    h = outcomes[outcomes["label_horizon"] == horizon][
        ["decision_id", "forward_return"]
    ]
    merged = decisions.merge(h, on="decision_id", how="left")
    merged["forward_return"] = pd.to_numeric(
        merged["forward_return"], errors="coerce",
    )
    return merged


def _date_range(df: pd.DataFrame) -> tuple[str, str] | None:
    if df.empty or "as_of_date" not in df.columns:
        return None
    s = pd.to_datetime(df["as_of_date"]).dropna()
    if s.empty:
        return None
    return s.min().date().isoformat(), s.max().date().isoformat()


def _universal_replay_warnings() -> list[str]:
    return [
        "replay is NOT equivalent to live trading; execution, slippage, "
        "and borrow costs not modelled",
        "catalyst history is partial unless news_item table is populated "
        "with historical rows and correct published_at timestamps",
        "survivorship bias present — current universe applied historically",
        "regime proxies in replay are simplified versions of production "
        "selector; absolute numbers differ from paper pipeline",
    ]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _get_nested(blob: Any, *keys: str, default: Any = None) -> Any:
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
