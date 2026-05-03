"""ML research snapshot — capture + persist one nightly diagnostic record."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.ml.advisory import engine_c_status, EngineCStatus
from apps.api.src.ml.baselines import run_baselines
from apps.api.src.ml.baselines_v2 import run_improved_baselines
from apps.api.src.ml.dataset import build_dataset, DatasetResult
from apps.api.src.ml.patterns import discover_patterns, PatternReport
from apps.api.src.ml.recommendation import build_recommendation
from apps.api.src.ml.report import build_feature_health
from apps.api.src.ml.splits import enough_data_for_ml
from apps.api.src.ml.validation import validate_no_leakage


@dataclass
class SnapshotRecord:
    id: str
    as_of_date: dt.date
    created_at: dt.datetime
    row_count: int
    labeled_row_count: int
    symbol_count: int
    date_start: dt.date | None
    date_end: dt.date | None
    tier: str
    leakage_clean: bool
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "as_of_date": self.as_of_date.isoformat(),
            "created_at": self.created_at.isoformat(),
            "row_count": self.row_count,
            "labeled_row_count": self.labeled_row_count,
            "symbol_count": self.symbol_count,
            "date_start":
                self.date_start.isoformat() if self.date_start else None,
            "date_end":
                self.date_end.isoformat() if self.date_end else None,
            "tier": self.tier,
            "leakage_clean": self.leakage_clean,
            **self.payload,
        }


def build_snapshot_payload(
    ds: DatasetResult,
    *,
    min_training_rows: int,
) -> dict[str, Any]:
    """Compute all diagnostics for a dataset, ready to INSERT or return."""
    df = ds.df
    feature_health = build_feature_health(df).to_dict() if ds.n_rows else {}
    leakage = validate_no_leakage(df, strict=False).to_dict() if ds.n_rows else {
        "ok": True, "violations": [], "suspicious_columns": [],
        "missing_timestamps": 0, "decision_label_overlap": 0,
        "forbidden_but_excluded": [],
    }
    v1 = run_baselines(df, label_col="fwd_ret_5d") if ds.n_rows else []
    v2 = run_improved_baselines(df, label_col="fwd_ret_5d") if ds.n_rows else []
    baseline_payload = {
        "v1": [b.to_dict() for b in v1],
        "v2": [b.to_dict() for b in v2],
    }
    best_sharpe = _best_sharpe(v1 + v2)
    patterns = (
        discover_patterns(df).to_dict() if ds.n_rows
        else PatternReport(n_rows=0, return_col="", control_mean=0.0).to_dict()
    )
    gate = enough_data_for_ml(ds.n_rows, min_for_models=min_training_rows)
    ec = engine_c_readiness(
        n_rows=ds.n_rows,
        labeled_rows=_count_labeled(df),
        leakage_ok=leakage.get("ok", False),
        best_baseline_sharpe=best_sharpe,
        ml_test_sharpe=None,
        catalyst_coverage=(feature_health.get("catalyst_coverage", 0.0)
                           if feature_health else 0.0),
        avg_feature_conf=_avg_feature_conf(df),
        min_training_rows=min_training_rows,
    )
    warnings = _collect_warnings(
        feature_health, leakage, v1 + v2, ec, ds,
    )
    rec = build_recommendation(
        n_rows=ds.n_rows,
        tier=gate["tier"],
        leakage_ok=leakage.get("ok", False),
        catalyst_coverage=(feature_health.get("catalyst_coverage", 0.0)
                           if feature_health else 0.0),
        best_baseline_sharpe=best_sharpe,
        engine_c_status=ec["engine_c_ml_status"],
        warnings=warnings,
    )
    return {
        "feature_health":   feature_health,
        "leakage_report":   leakage,
        "baseline_results": baseline_payload,
        "patterns":         patterns,
        "engine_c_status":  ec,
        "warnings":         warnings,
        "recommendation":   rec,
        "tier":             gate["tier"],
        "dataset_diag":     ds.diagnostics,
    }


# ---------------------------------------------------------------------------
# Engine C readiness — expanded state machine
# ---------------------------------------------------------------------------

def engine_c_readiness(
    *,
    n_rows: int,
    labeled_rows: int,
    leakage_ok: bool,
    best_baseline_sharpe: float,
    ml_test_sharpe: float | None,
    catalyst_coverage: float,
    avg_feature_conf: float,
    min_training_rows: int,
) -> dict[str, Any]:
    """Return an Engine C readiness dict covering all new states.

    States:
        DISABLED_INSUFFICIENT_DATA
        DISABLED_LEAKAGE_RISK
        BASELINES_ONLY
        ADVISORY_READY
        SHADOW_READY
        ACTIVE_CANDIDATE
    """
    blockers: list[str] = []
    if not leakage_ok:
        blockers.append("leakage violations present")
        status = "DISABLED_LEAKAGE_RISK"
    elif labeled_rows < min_training_rows // 5:
        blockers.append(f"labeled rows {labeled_rows} "
                        f"< {min_training_rows // 5} floor")
        status = "DISABLED_INSUFFICIENT_DATA"
    elif labeled_rows < min_training_rows:
        blockers.append(f"labeled rows {labeled_rows} < {min_training_rows}")
        status = "BASELINES_ONLY"
    elif ml_test_sharpe is None:
        status = "ADVISORY_READY"
        if catalyst_coverage < 0.3:
            blockers.append(
                f"catalyst coverage {catalyst_coverage:.0%} weak"
            )
        if avg_feature_conf < 0.6:
            blockers.append(
                f"avg feature_confidence {avg_feature_conf:.2f} < 0.6"
            )
    elif ml_test_sharpe <= best_baseline_sharpe:
        blockers.append(
            f"ml test sharpe {ml_test_sharpe:.3f} ≤ baseline "
            f"{best_baseline_sharpe:.3f}"
        )
        status = "SHADOW_READY"
    else:
        status = "ACTIVE_CANDIDATE"

    next_req: str
    if status == "DISABLED_INSUFFICIENT_DATA":
        next_req = f"accumulate to {min_training_rows // 5} labeled decisions"
    elif status == "DISABLED_LEAKAGE_RISK":
        next_req = "fix leakage — never train with contaminated features"
    elif status == "BASELINES_ONLY":
        next_req = f"accumulate to {min_training_rows} labeled decisions"
    elif status == "ADVISORY_READY":
        next_req = "run walk-forward evaluation; compare against baselines"
    elif status == "SHADOW_READY":
        next_req = ("accumulate out-of-sample shadow results before "
                    "promoting to candidate")
    else:
        next_req = ("keep monitoring; only promote if shadow holds across "
                    "regime shifts")

    return {
        "engine_c_ml_status": status,
        "engine_c_ml_reason":
            "; ".join(blockers) if blockers else "all readiness checks passed",
        "engine_c_training_rows": n_rows,
        "engine_c_labeled_rows":  labeled_rows,
        "engine_c_latest_eval_score": ml_test_sharpe,
        "engine_c_baseline_best":     best_baseline_sharpe,
        "engine_c_catalyst_coverage": catalyst_coverage,
        "engine_c_avg_feature_conf":  avg_feature_conf,
        "engine_c_blockers":          blockers,
        "engine_c_next_requirement":  next_req,
        "min_rows_required":          min_training_rows,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def capture_snapshot(
    session: Session,
    *,
    min_training_rows: int,
    bar_symbol_map: dict[str, str] | None = None,
    persist: bool = True,
) -> SnapshotRecord:
    """Build dataset + diagnostics. Persist to `ml_research_snapshot`."""
    ds = build_dataset(session, bar_symbol_map=bar_symbol_map)
    payload = build_snapshot_payload(ds, min_training_rows=min_training_rows)

    now = dt.datetime.now(dt.timezone.utc)
    today = now.date()
    labeled = _count_labeled(ds.df)
    sym_count = (int(ds.df["symbol"].nunique())
                 if "symbol" in ds.df.columns else 0)
    date_start, date_end = _date_range(ds.df)

    record_id: str
    if persist:
        row = session.execute(text("""
            INSERT INTO ml_research_snapshot
              (as_of_date, row_count, labeled_row_count, symbol_count,
               date_start, date_end, tier,
               leakage_clean, leakage_report, feature_health,
               baseline_results, patterns, engine_c_status, warnings,
               recommendation)
            VALUES
              (:asof, :rc, :lrc, :sc, :ds_start, :ds_end, :tier,
               :lok, CAST(:lr AS jsonb), CAST(:fh AS jsonb),
               CAST(:br AS jsonb), CAST(:pt AS jsonb),
               CAST(:ec AS jsonb), CAST(:wa AS jsonb),
               :rec)
            RETURNING id
        """), {
            "asof": today,
            "rc": ds.n_rows,
            "lrc": labeled,
            "sc": sym_count,
            "ds_start": date_start,
            "ds_end":   date_end,
            "tier":     payload["tier"],
            "lok":      payload["leakage_report"].get("ok", False),
            "lr":       json.dumps(payload["leakage_report"], default=str),
            "fh":       json.dumps(payload["feature_health"], default=str),
            "br":       json.dumps(payload["baseline_results"], default=str),
            "pt":       json.dumps(payload["patterns"], default=str),
            "ec":       json.dumps(payload["engine_c_status"], default=str),
            "wa":       json.dumps(payload["warnings"], default=str),
            "rec":      payload["recommendation"],
        }).fetchone()
        session.commit()
        record_id = str(row[0])
    else:
        record_id = "00000000-0000-0000-0000-000000000000"

    return SnapshotRecord(
        id=record_id, as_of_date=today, created_at=now,
        row_count=ds.n_rows, labeled_row_count=labeled,
        symbol_count=sym_count,
        date_start=date_start, date_end=date_end,
        tier=payload["tier"],
        leakage_clean=payload["leakage_report"].get("ok", False),
        payload=payload,
    )


def list_snapshots(
    session: Session, *, limit: int = 30,
) -> list[dict[str, Any]]:
    rows = session.execute(text("""
        SELECT id, as_of_date, created_at, row_count, labeled_row_count,
               symbol_count, date_start, date_end, tier, leakage_clean,
               recommendation
        FROM ml_research_snapshot
        ORDER BY created_at DESC
        LIMIT :lim
    """), {"lim": int(limit)}).mappings().all()
    return [dict(r) for r in rows]


def latest_snapshot(session: Session) -> dict[str, Any] | None:
    row = session.execute(text("""
        SELECT id, as_of_date, created_at, row_count, labeled_row_count,
               symbol_count, date_start, date_end, tier, leakage_clean,
               leakage_report, feature_health, baseline_results, patterns,
               engine_c_status, warnings, recommendation
        FROM ml_research_snapshot
        ORDER BY created_at DESC
        LIMIT 1
    """)).mappings().first()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _count_labeled(df) -> int:
    if df is None or df.empty:
        return 0
    if "fwd_ret_5d" in df.columns:
        return int(df["fwd_ret_5d"].notna().sum())
    return 0


def _avg_feature_conf(df) -> float:
    if df is None or df.empty or "feature_confidence" not in df.columns:
        return 0.0
    s = df["feature_confidence"].dropna()
    return float(s.mean()) if not s.empty else 0.0


def _date_range(df) -> tuple[dt.date | None, dt.date | None]:
    if df is None or df.empty or "as_of_date" not in df.columns:
        return None, None
    import pandas as pd
    s = pd.to_datetime(df["as_of_date"]).dropna()
    if s.empty:
        return None, None
    return s.min().date(), s.max().date()


def _best_sharpe(baselines) -> float:
    vals: list[float] = []
    for b in baselines:
        sv = getattr(b, "sharpe_proxy", None)
        if sv is None:
            continue
        if sv != float("inf") and sv == sv:   # not NaN
            vals.append(float(sv))
    return max(vals) if vals else 0.0


def _collect_warnings(
    feature_health: dict[str, Any],
    leakage: dict[str, Any],
    baselines: list[Any],
    engine_c: dict[str, Any],
    ds: DatasetResult,
) -> list[str]:
    warnings: list[str] = []
    if not leakage.get("ok", True):
        warnings.append("leakage: " + "; ".join(
            leakage.get("violations", [])
        ))
    warnings.extend(feature_health.get("warnings", []) or [])
    # Baseline degradation hint — only if any baseline has a negative sharpe
    neg_sharpe = [b for b in baselines
                  if getattr(b, "sharpe_proxy", 0.0) < -0.2]
    if neg_sharpe:
        warnings.append(
            f"{len(neg_sharpe)} baselines have sharpe_proxy < -0.2 — review"
        )
    if engine_c.get("engine_c_ml_status") == "DISABLED_LEAKAGE_RISK":
        warnings.append("engine_c disabled due to leakage risk")
    if ds.n_rows == 0:
        warnings.append("no decision_log rows yet; run paper pipeline")
    return warnings
