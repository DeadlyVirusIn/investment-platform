"""ML research API — read-only diagnostics + on-demand evaluation.

Endpoints:
  GET  /ml/research/dataset-health
  GET  /ml/research/baselines
  GET  /ml/research/latest-report
  POST /ml/research/run-evaluation
  GET  /ml/research/engine-c-status

All endpoints are advisory. None of them change paper trading or engine
behavior. Feature flag `ML_ADVISORY_ENABLED` gates exposure — when off,
endpoints return 503 so the UI can hide the panel.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.ml import (
    WalkForwardConfig, build_advisory, build_dataset, build_feature_health,
    engine_c_status, evaluate_walk_forward, run_baselines,
    validate_no_leakage,
)
from apps.api.src.ml.baselines_v2 import run_improved_baselines
from apps.api.src.ml.patterns import discover_patterns
from apps.api.src.ml.snapshots import (
    capture_snapshot, latest_snapshot, list_snapshots,
    engine_c_readiness as engine_c_readiness_v2,
)
from apps.api.src.ml.recommendation import build_recommendation

router = APIRouter(prefix="/ml/research", tags=["ml-research"])


def _must_be_enabled() -> None:
    enabled = getattr(settings, "ML_ADVISORY_ENABLED", True)
    if not enabled:
        raise HTTPException(status_code=503, detail="ML advisory disabled")


def _open_session() -> Session:
    # Same pattern as api/operator.py — direct session from factory.
    return SessionLocal()


@router.get("/dataset-health")
async def dataset_health() -> dict[str, Any]:
    _must_be_enabled()
    with _open_session() as s:
        ds = build_dataset(s)
    report = build_feature_health(ds.df)
    leakage = validate_no_leakage(ds.df, strict=False)
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "diagnostics":  ds.diagnostics,
        "feature_health": report.to_dict(),
        "leakage": leakage.to_dict(),
    }


@router.get("/baselines")
async def baselines(
    label_col: str = "fwd_ret_5d",
) -> dict[str, Any]:
    _must_be_enabled()
    with _open_session() as s:
        ds = build_dataset(s)
    if ds.empty():
        return {"n_rows": 0, "baselines": [], "reason": "no data"}
    results = run_baselines(ds.df, label_col=label_col)
    return {
        "n_rows": ds.n_rows,
        "label_col": label_col,
        "baselines": [r.to_dict() for r in results],
    }


@router.get("/latest-report")
async def latest_report() -> dict[str, Any]:
    """Full snapshot: health + leakage + baselines + engine-c status.

    No training — cheap enough to hit from the UI on each panel open.
    """
    _must_be_enabled()
    with _open_session() as s:
        ds = build_dataset(s)
    health = build_feature_health(ds.df).to_dict()
    leakage = validate_no_leakage(ds.df, strict=False).to_dict()
    bases = (
        [b.to_dict() for b in run_baselines(ds.df, label_col="fwd_ret_5d")]
        if not ds.empty() else []
    )
    best_sharpe = max((b.get("sharpe_proxy", 0.0) or 0.0) for b in bases) \
                  if bases else 0.0
    ec = engine_c_status(
        n_rows=ds.n_rows,
        leakage_ok=leakage["ok"],
        baseline_best_sharpe=best_sharpe,
        ml_test_sharpe=None,
        min_training_rows=int(
            getattr(settings, "ML_MIN_TRAINING_ROWS", 1000)
        ),
    ).to_dict()
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "diagnostics":  ds.diagnostics,
        "feature_health": health,
        "leakage": leakage,
        "baselines": bases,
        "engine_c": ec,
    }


@router.post("/run-evaluation")
async def run_evaluation(
    model_name: str = "logistic",
    label_col: str = "label_win_5d",
    return_col: str = "fwd_ret_5d",
) -> dict[str, Any]:
    _must_be_enabled()
    with _open_session() as s:
        ds = build_dataset(s)
    if ds.empty():
        return {"trained": False, "reason": "no data"}
    leakage = validate_no_leakage(ds.df, strict=False)
    if not leakage.ok:
        return {
            "trained": False,
            "reason": "leakage detected",
            "leakage": leakage.to_dict(),
        }
    min_rows = int(getattr(settings, "ML_MIN_TRAINING_ROWS", 1000))
    eval_result = evaluate_walk_forward(
        ds.df,
        label_col=label_col,
        return_col=return_col,
        model_name=model_name,
        wf_cfg=WalkForwardConfig(),
        min_training_rows=min_rows,
    )
    test_folds = [f for f in eval_result.folds if f.split == "test"]
    ml_test_sharpe = None
    if test_folds:
        vals = [f.sharpe_proxy_accepted for f in test_folds
                if f.sharpe_proxy_accepted is not None]
        if vals:
            ml_test_sharpe = float(sum(vals) / len(vals))

    bases = run_baselines(ds.df, label_col=return_col)
    best_baseline_sharpe = max(
        (b.sharpe_proxy for b in bases), default=0.0,
    )
    ec = engine_c_status(
        n_rows=ds.n_rows,
        leakage_ok=leakage.ok,
        baseline_best_sharpe=best_baseline_sharpe,
        ml_test_sharpe=ml_test_sharpe,
        min_training_rows=min_rows,
    ).to_dict()
    # ---- Per-row advisory preview ----
    advisory_preview: list[dict[str, Any]] = []
    if eval_result.trained_any:
        # Advisory for LAST fold's test set, head 25 rows
        head = ds.df.tail(25)
        for i in range(len(head)):
            row = head.iloc[i]
            adv = build_advisory(
                decision_id=str(row.get("decision_id") or ""),
                ml_score=0.5,
                data_confidence=float(row.get("feature_confidence") or 0.0),
                catalyst_blocks=bool(row.get("trade_policy_block") or False),
                catalyst_reduces=bool(row.get("trade_policy_reduce") or False),
                n_training_rows=ds.n_rows,
                min_training_rows=min_rows,
            )
            advisory_preview.append(adv.to_dict())
    return {
        "trained": eval_result.trained_any,
        "model": model_name,
        "label": label_col,
        "eval": eval_result.to_dict(),
        "ml_test_sharpe_proxy": ml_test_sharpe,
        "baselines_best_sharpe": best_baseline_sharpe,
        "engine_c": ec,
        "advisory_preview": advisory_preview,
    }


@router.get("/patterns")
async def patterns(return_col: str | None = None) -> dict[str, Any]:
    _must_be_enabled()
    with _open_session() as s:
        ds = build_dataset(s)
    if ds.empty():
        return {"n_rows": 0, "patterns": [], "reason": "no data"}
    report = discover_patterns(ds.df, return_col=return_col)
    return report.to_dict()


@router.get("/baselines-v2")
async def baselines_v2(label_col: str = "fwd_ret_5d") -> dict[str, Any]:
    _must_be_enabled()
    with _open_session() as s:
        ds = build_dataset(s)
    if ds.empty():
        return {"n_rows": 0, "baselines": []}
    v1 = run_baselines(ds.df, label_col=label_col)
    v2 = run_improved_baselines(ds.df, label_col=label_col)
    return {
        "n_rows": ds.n_rows,
        "label_col": label_col,
        "v1": [b.to_dict() for b in v1],
        "v2": [b.to_dict() for b in v2],
    }


@router.get("/snapshots")
async def snapshots(limit: int = 30) -> dict[str, Any]:
    _must_be_enabled()
    with _open_session() as s:
        rows = list_snapshots(s, limit=limit)
    return {"count": len(rows), "snapshots": rows}


@router.get("/snapshots/latest")
async def snapshots_latest() -> dict[str, Any]:
    _must_be_enabled()
    with _open_session() as s:
        row = latest_snapshot(s)
    if row is None:
        return {"present": False}
    return {"present": True, "snapshot": row}


@router.post("/snapshots/capture")
async def snapshots_capture() -> dict[str, Any]:
    """Manually trigger diagnostics snapshot (same as nightly job)."""
    _must_be_enabled()
    min_rows = int(getattr(settings, "ML_MIN_TRAINING_ROWS", 1000))
    with _open_session() as s:
        rec = capture_snapshot(s, min_training_rows=min_rows, persist=True)
    return {"captured": True, "id": rec.id, "tier": rec.tier,
            "row_count": rec.row_count,
            "labeled_row_count": rec.labeled_row_count,
            "leakage_clean": rec.leakage_clean}


@router.get("/engine-c-readiness")
async def engine_c_readiness_endpoint() -> dict[str, Any]:
    _must_be_enabled()
    with _open_session() as s:
        ds = build_dataset(s)
    leakage = validate_no_leakage(ds.df, strict=False)
    v1 = run_baselines(ds.df, label_col="fwd_ret_5d") if ds.n_rows else []
    v2 = run_improved_baselines(ds.df, label_col="fwd_ret_5d") \
         if ds.n_rows else []
    best = max(
        (b.sharpe_proxy for b in (v1 + v2)), default=0.0,
    )
    feature_health = (build_feature_health(ds.df).to_dict()
                      if ds.n_rows else {})
    # Count labeled rows + avg feature_conf same way as snapshots module
    labeled = int(ds.df["fwd_ret_5d"].notna().sum()) \
              if "fwd_ret_5d" in ds.df.columns else 0
    avg_conf = (float(ds.df["feature_confidence"].dropna().mean())
                if "feature_confidence" in ds.df.columns
                and ds.df["feature_confidence"].notna().any()
                else 0.0)
    return engine_c_readiness_v2(
        n_rows=ds.n_rows,
        labeled_rows=labeled,
        leakage_ok=leakage.ok,
        best_baseline_sharpe=best,
        ml_test_sharpe=None,
        catalyst_coverage=(feature_health.get("catalyst_coverage", 0.0)
                            if feature_health else 0.0),
        avg_feature_conf=avg_conf,
        min_training_rows=int(getattr(settings, "ML_MIN_TRAINING_ROWS", 1000)),
    )


@router.get("/engine-c-status")
async def engine_c() -> dict[str, Any]:
    _must_be_enabled()
    with _open_session() as s:
        ds = build_dataset(s)
    leakage = validate_no_leakage(ds.df, strict=False)
    bases = run_baselines(ds.df, label_col="fwd_ret_5d") \
            if not ds.empty() else []
    best_sharpe = max(
        (b.sharpe_proxy for b in bases), default=0.0,
    )
    ec = engine_c_status(
        n_rows=ds.n_rows,
        leakage_ok=leakage.ok,
        baseline_best_sharpe=best_sharpe,
        ml_test_sharpe=None,
        min_training_rows=int(
            getattr(settings, "ML_MIN_TRAINING_ROWS", 1000)
        ),
    )
    return ec.to_dict()
