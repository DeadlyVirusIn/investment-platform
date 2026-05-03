"""Nightly shadow orchestrator — eligibility → train → score → report."""

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.ml.dataset import build_dataset
from apps.api.src.ml.features import FEATURE_COLUMNS
from apps.api.src.ml.shadow.calibration import compute_calibration
from apps.api.src.ml.shadow.comparison import compare_shadow_vs_baselines
from apps.api.src.ml.shadow.disagreement import compute_disagreements
from apps.api.src.ml.shadow.eligibility import (
    EligibilityStatus, evaluate_eligibility,
)
from apps.api.src.ml.shadow.scorer import score_recent_decisions
from apps.api.src.ml.shadow.trainer import (
    ModelType, TrainerResult, train_shadow_models,
)


SHADOW_STATUSES = {
    "SKIPPED_INSUFFICIENT_DATA",
    "SKIPPED_LEAKAGE_RISK",
    "SKIPPED_LOW_FEATURE_HEALTH",
    "SKIPPED_REPLAY_NOT_READY",
    "SKIPPED_NO_LABELS",
    "TRAINED_SHADOW",
    "TRAINED_BUT_BELOW_BASELINE",
    "TRAINED_BUT_UNCALIBRATED",
    "SHADOW_OUTPERFORMING",
}


@dataclass
class NightlyShadowResult:
    model_run_id: str
    status: str
    n_rows: int = 0
    n_labeled: int = 0
    n_scored: int = 0
    best_model_type: str | None = None
    best_model_test_sharpe: float | None = None
    best_baseline_sharpe: float | None = None
    winner: str | None = None
    delta_sharpe: float | None = None
    ece: float | None = None
    brier: float | None = None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_run_id": self.model_run_id,
            "status": self.status,
            "n_rows": self.n_rows,
            "n_labeled": self.n_labeled,
            "n_scored": self.n_scored,
            "best_model_type": self.best_model_type,
            "best_model_test_sharpe": self.best_model_test_sharpe,
            "best_baseline_sharpe": self.best_baseline_sharpe,
            "winner": self.winner,
            "delta_sharpe": self.delta_sharpe,
            "ece": self.ece,
            "brier": self.brier,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


def run_nightly_shadow(
    session: Session,
    *,
    min_training_rows: int,
    # PA-2 — net-of-cost defaults
    label_col: str = "label_win_net_5d",
    return_col: str = "fwd_ret_net_5d",
    horizon: int = 5,
    dataset_source: str = "real",
    replay_readiness_status: str | None = None,
    model_types: tuple[ModelType, ...] = (
        ModelType.LOGISTIC, ModelType.RIDGE, ModelType.RF_SHALLOW,
    ),
    persist: bool = True,
    score_recent_n: int = 200,
) -> NightlyShadowResult:
    ds = build_dataset(session, source=dataset_source)
    df = ds.df
    elig = evaluate_eligibility(
        df,
        min_training_rows=min_training_rows,
        label_col=label_col,
        replay_readiness_status=replay_readiness_status,
        dataset_source=dataset_source,
    )
    model_run_id = str(uuid.uuid4())

    # --- not eligible → persist skipped row + exit ---
    if not elig.ok:
        if persist:
            _insert_model_run_row(
                session, model_run_id=model_run_id,
                run_name=f"shadow-{dt.date.today()}",
                model_type="logistic",    # placeholder
                dataset_source=dataset_source,
                label=label_col, horizon=horizon,
                feature_list=list(FEATURE_COLUMNS),
                row_count=elig.row_count,
                labeled_row_count=elig.labeled_row_count,
                hyperparams={},
                metrics=None, baseline_comparison=None,
                calibration=None,
                leakage=elig.leakage_summary,
                feature_health=elig.feature_health_summary,
                status=elig.status.value,
                blockers=elig.blockers,
            )
            session.commit()
        return NightlyShadowResult(
            model_run_id=model_run_id,
            status=elig.status.value,
            n_rows=elig.row_count,
            n_labeled=elig.labeled_row_count,
            blockers=elig.blockers,
        )

    # --- train ---
    trainer_results: list[TrainerResult] = train_shadow_models(
        df,
        label_col=label_col,
        return_col=return_col,
        feature_cols=FEATURE_COLUMNS,
        model_types=model_types,
    )
    best: TrainerResult | None = None
    for tr in trainer_results:
        if tr.skipped or tr.final_model is None:
            continue
        if best is None or (
            (tr.val_sharpe_proxy or 0.0) > (best.val_sharpe_proxy or 0.0)
        ):
            best = tr

    if best is None:
        # Every model skipped → treat as skipped run
        status = "SKIPPED_INSUFFICIENT_DATA"
        if persist:
            _insert_model_run_row(
                session, model_run_id=model_run_id,
                run_name=f"shadow-{dt.date.today()}",
                model_type="logistic",
                dataset_source=dataset_source,
                label=label_col, horizon=horizon,
                feature_list=list(FEATURE_COLUMNS),
                row_count=elig.row_count,
                labeled_row_count=elig.labeled_row_count,
                hyperparams={},
                metrics={"trainer_results": [tr.to_dict() for tr in trainer_results]},
                baseline_comparison=None,
                calibration=None,
                leakage=elig.leakage_summary,
                feature_health=elig.feature_health_summary,
                status=status,
                blockers=["all candidate models skipped"],
            )
            session.commit()
        return NightlyShadowResult(
            model_run_id=model_run_id, status=status,
            n_rows=elig.row_count, n_labeled=elig.labeled_row_count,
            blockers=["all candidate models skipped"],
        )

    # --- score frame-wide for comparison + calibration ---
    scored = best.final_model.predict_proba(df)
    df = df.copy()
    df["__shadow_score"] = scored
    cmp = compare_shadow_vs_baselines(
        df, shadow_score_col="__shadow_score",
        label_col=label_col, return_col=return_col,
    )
    calib = compute_calibration(
        df[label_col].fillna(0).astype(float).to_numpy(),
        df["__shadow_score"].to_numpy(),
    )

    # --- status determination ---
    status = _determine_status(cmp, calib)

    # --- score recent decisions → ml_shadow_prediction ---
    recent = df.sort_values("as_of_date").tail(score_recent_n)
    n_scored = 0
    if persist:
        # Insert model_run row FIRST so FK works
        _insert_model_run_row(
            session, model_run_id=model_run_id,
            run_name=f"shadow-{dt.date.today()}",
            model_type=best.model_type.value,
            dataset_source=dataset_source,
            label=label_col, horizon=horizon,
            feature_list=best.feature_list,
            row_count=elig.row_count,
            labeled_row_count=elig.labeled_row_count,
            hyperparams={"model_cap": 10},
            metrics={
                "trainer_results": [tr.to_dict() for tr in trainer_results],
                "best_model": best.to_dict(),
            },
            baseline_comparison=cmp.to_dict(),
            calibration=calib.to_dict(),
            leakage=elig.leakage_summary,
            feature_health=elig.feature_health_summary,
            status=status,
            blockers=[],
        )
        session.commit()

        scoring = score_recent_decisions(
            session, recent,
            model=best.final_model,
            model_run_id=model_run_id,
            feature_cols=list(best.feature_list),
            n_training_rows=elig.labeled_row_count,
            min_training_rows=min_training_rows,
            persist=True,
        )
        n_scored = scoring.n_persisted

    return NightlyShadowResult(
        model_run_id=model_run_id,
        status=status,
        n_rows=elig.row_count,
        n_labeled=elig.labeled_row_count,
        n_scored=n_scored,
        best_model_type=best.model_type.value,
        best_model_test_sharpe=best.test_sharpe_proxy,
        best_baseline_sharpe=(
            cmp.baselines_best.get("sharpe_proxy")
            if cmp.baselines_best else None
        ),
        winner=cmp.winner,
        delta_sharpe=cmp.delta_sharpe,
        ece=calib.ece,
        brier=calib.brier,
        warnings=cmp.notes,
    )


# ---------------------------------------------------------------------------
def _determine_status(cmp, calib) -> str:
    if calib.poor_calibration:
        return "TRAINED_BUT_UNCALIBRATED"
    if cmp.winner == "ml" and cmp.delta_sharpe >= 0.1:
        return "SHADOW_OUTPERFORMING"
    if cmp.winner == "baseline" and cmp.delta_sharpe < -0.05:
        return "TRAINED_BUT_BELOW_BASELINE"
    return "TRAINED_SHADOW"


def _insert_model_run_row(
    session: Session, *,
    model_run_id: str, run_name: str, model_type: str,
    dataset_source: str, label: str, horizon: int,
    feature_list: list[str],
    row_count: int, labeled_row_count: int,
    hyperparams: dict[str, Any],
    metrics: dict[str, Any] | None,
    baseline_comparison: dict[str, Any] | None,
    calibration: dict[str, Any] | None,
    leakage: dict[str, Any],
    feature_health: dict[str, Any],
    status: str, blockers: list[str],
) -> None:
    # Dataset builder may swallow schema-mismatch errors during read; those
    # leave Postgres in aborted-txn state. Rollback defensively before
    # writing the audit row so INSERT never fails on a stale txn.
    try:
        session.rollback()
    except Exception:
        pass
    session.execute(text("""
        INSERT INTO ml_model_run
          (id, run_name, model_type, dataset_source,
           row_count, labeled_row_count, feature_list,
           label_target, horizon, hyperparams,
           metrics, baseline_comparison, calibration,
           leakage_report, feature_health,
           status, blockers)
        VALUES
          (:id, :rn, :mt, :ds,
           :rc, :lrc, CAST(:fl AS jsonb),
           :lb, :h, CAST(:hp AS jsonb),
           CAST(:m AS jsonb), CAST(:bc AS jsonb),
           CAST(:cal AS jsonb),
           CAST(:lr AS jsonb), CAST(:fh AS jsonb),
           :st, CAST(:bl AS jsonb))
    """), {
        "id":  model_run_id,
        "rn":  run_name,
        "mt":  model_type,
        "ds":  dataset_source,
        "rc":  row_count,
        "lrc": labeled_row_count,
        "fl":  json.dumps(list(feature_list)),
        "lb":  label,
        "h":   horizon,
        "hp":  json.dumps(hyperparams, default=str),
        "m":   json.dumps(metrics or {}, default=str),
        "bc":  json.dumps(baseline_comparison or {}, default=str),
        "cal": json.dumps(calibration or {}, default=str),
        "lr":  json.dumps(leakage or {}, default=str),
        "fh":  json.dumps(feature_health or {}, default=str),
        "st":  status,
        "bl":  json.dumps(blockers or [], default=str),
    })
