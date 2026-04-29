"""Phase 11T.2 - shadow scorer.

Read-only. Loads a pickled model artifact registered via the model
registry, scores rows, assigns frozen 3-tier buckets, joins realized
labels when present. NEVER mutates DB. NEVER mutates pickle.
NEVER mutates dataset. NEVER imports broker / live / execution
modules.

Frozen constants:
  BUCKET_EDGES = (0.33, 0.66)
  REGRESSION_TRANSFORM = "frozen_sigmoid_v1.0.0"
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Sequence

from loguru import logger

from apps.api.src.ml.model_registry import (
    ModelRegistryError,
    show_entry,
)
from apps.api.src.ml.rule_comparator import (
    SHADOW_HIGH, SHADOW_LOW, SHADOW_MID,
    categorize,
)


BUCKET_EDGES_FROZEN: tuple[float, float] = (0.33, 0.66)
REGRESSION_TRANSFORM = "frozen_sigmoid_v1.0.0"
EXCLUDED_REASON_MISSING = "missing_features"
EXCLUDED_REASON_PROVISIONAL = "is_provisional"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ShadowScorerError(RuntimeError):
    """Base shadow scorer error."""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScorerConfig:
    model_id: str
    start: dt.date
    end: dt.date
    sources: tuple[str, ...]
    domain: str                              # 'equity'|'options'|'both'
    include_provisional: bool
    bucket_edges: tuple[float, float]
    output_dir: str
    dry_run: bool
    commit: bool

    def __post_init__(self) -> None:
        if self.dry_run == self.commit:
            raise ValueError(
                "dry_run and commit are mutually exclusive"
            )
        if self.start > self.end:
            raise ValueError("start must be <= end")
        if self.domain not in ("equity", "options", "both"):
            raise ValueError(
                f"domain must be one of equity|options|both: "
                f"{self.domain!r}"
            )
        if not self.sources:
            raise ValueError("sources must be non-empty")
        if (
            len(self.bucket_edges) != 2
            or not (0.0 < self.bucket_edges[0] < self.bucket_edges[1] < 1.0)
        ):
            raise ValueError(
                f"bucket_edges must be (lo, hi) with 0<lo<hi<1; "
                f"got {self.bucket_edges}"
            )


@dataclass(frozen=True)
class ScoredRow:
    observation_id: str
    as_of_date: str
    symbol: str
    source: str
    deterministic_rule_id: str | None
    deterministic_outcome: str | None
    deterministic_qualified: bool
    deterministic_failed_gates_count: int
    model_score: float
    model_bucket: str
    realized_label: str | None
    is_provisional: bool
    comparison_category: str


@dataclass(frozen=True)
class ScoringSummary:
    config: ScorerConfig
    model_artifact_checksum_sha256: str
    model_status: str
    rows_input: int
    rows_scored: int
    rows_with_realized_label: int
    rows_excluded_by_reason: dict[str, int]
    rows: tuple[ScoredRow, ...]


# ---------------------------------------------------------------------------
# Bucket assignment + transforms (pure-fn)
# ---------------------------------------------------------------------------

def assign_bucket(
    score: float,
    *,
    edges: tuple[float, float] = BUCKET_EDGES_FROZEN,
) -> str:
    lo, hi = edges
    if score < lo:
        return SHADOW_LOW
    if score >= hi:
        return SHADOW_HIGH
    return SHADOW_MID


def regression_to_score(
    pred: float, *, train_median: float = 0.0,
    train_scale: float = 0.01,
) -> float:
    """Frozen monotone sigmoid mapping a predicted return into [0,1].
    `train_median` and `train_scale` come from the pickle's
    `trained_on` block when available; otherwise default to 0/0.01 so
    the transform is deterministic but conservative."""
    if train_scale <= 0:
        train_scale = 0.01
    z = (pred - train_median) / train_scale
    # Clip extreme z to avoid float overflow.
    if z > 30:
        return 1.0
    if z < -30:
        return 0.0
    return 1.0 / (1.0 + math.exp(-z))


# ---------------------------------------------------------------------------
# Pickle load (read-only)
# ---------------------------------------------------------------------------

def _file_sha256(path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_pickle(path) -> dict[str, Any]:
    import joblib
    obj = joblib.load(path)
    if not isinstance(obj, dict):
        raise ShadowScorerError(
            f"pickle at {path} must be a dict (got {type(obj).__name__})"
        )
    return obj


# ---------------------------------------------------------------------------
# Row scoring (pure-fn)
# ---------------------------------------------------------------------------

def _positive_class_index(estimator) -> int:
    """For sklearn classification estimators with classes_ attribute,
    locate the index of the 'positive' class. Falls back to last
    column when an explicit 'positive' label is absent."""
    classes = getattr(estimator, "classes_", None)
    if classes is None:
        return -1
    for i, c in enumerate(list(classes)):
        if str(c).lower() == "positive":
            return i
    return len(classes) - 1


def score_features_classification(
    estimator, x_row, preprocessor=None,
) -> float:
    """Predict positive-class probability for a single row. Returns
    a float in [0,1]."""
    import numpy as np
    if preprocessor is not None:
        x = preprocessor.transform(x_row)
    else:
        x = x_row
    if hasattr(estimator, "predict_proba"):
        p = estimator.predict_proba(x)
        idx = _positive_class_index(estimator)
        return float(np.asarray(p)[0, idx])
    if hasattr(estimator, "decision_function"):
        z = float(np.asarray(estimator.decision_function(x))[0])
        return 1.0 / (1.0 + math.exp(-z))
    raise ShadowScorerError(
        "estimator has neither predict_proba nor decision_function"
    )


def score_features_regression(
    estimator, x_row, preprocessor=None,
    *,
    train_median: float = 0.0, train_scale: float = 0.01,
) -> float:
    if preprocessor is not None:
        x = preprocessor.transform(x_row)
    else:
        x = x_row
    pred = float(estimator.predict(x)[0])
    return regression_to_score(
        pred, train_median=train_median, train_scale=train_scale,
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _read_observations(
    session,
    *,
    cfg: ScorerConfig,
):
    from sqlalchemy import text
    rows = session.execute(text(
        """
        SELECT
            l.id::text                AS observation_id,
            l.entry_date              AS as_of_date,
            l.symbol                  AS symbol,
            l.source                  AS source,
            l.rule_id                 AS deterministic_rule_id,
            l.outcome_class           AS deterministic_outcome,
            (cardinality(COALESCE(l.failed_gates, ARRAY[]::text[]))
             = 0)                     AS deterministic_qualified,
            cardinality(
                COALESCE(l.failed_gates, ARRAY[]::text[])
            )                         AS deterministic_failed_gates_count,
            l.outcome_class           AS realized_label,
            l.is_provisional          AS is_provisional,
            l.gate_snapshot           AS gate_snapshot,
            l.domain                  AS domain
        FROM paper_observation_label l
        WHERE l.entry_date >= :start
          AND l.entry_date <= :end
          AND l.source = ANY(:sources)
          AND (:domain = 'both' OR l.domain = :domain)
        ORDER BY l.entry_date, l.symbol
        """
    ), {
        "start": cfg.start, "end": cfg.end,
        "sources": list(cfg.sources),
        "domain": cfg.domain,
    }).all()
    return [dict(r._mapping) for r in rows]


def _build_feature_vector(
    obs: dict[str, Any],
    feature_names: Sequence[str],
):
    """Try to build a minimal feature vector from gate_snapshot. When
    a feature is not present in the snapshot, the value is None and
    the row is excluded as `missing_features`. Pure-fn over a single
    obs dict."""
    import numpy as np
    snap = obs.get("gate_snapshot") or {}
    if isinstance(snap, str):
        import json as _json
        try:
            snap = _json.loads(snap)
        except Exception:  # noqa: BLE001
            snap = {}
    vals: list[float] = []
    missing: list[str] = []
    for fn in feature_names:
        v = snap.get(fn)
        if v is None:
            missing.append(fn)
            vals.append(0.0)
            continue
        if isinstance(v, bool):
            vals.append(1.0 if v else 0.0)
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            missing.append(fn)
            vals.append(0.0)
    return np.asarray([vals], dtype=float), missing


def run(
    cfg: ScorerConfig,
    *,
    session_factory=None,
    registry_path=None,
) -> ScoringSummary:
    """Read-only orchestrator."""
    from apps.api.src.db import SessionLocal
    sf = session_factory or SessionLocal

    entry = show_entry(cfg.model_id, registry_path=registry_path)
    if entry is None:
        raise ShadowScorerError(
            f"model_id {cfg.model_id!r} not in registry"
        )
    if entry.get("status") not in ("shadow_only",):
        raise ShadowScorerError(
            f"registry status must be shadow_only; got "
            f"{entry.get('status')!r}"
        )
    artifact_path = entry.get("artifact_path")
    if not artifact_path:
        raise ShadowScorerError(
            "registry entry has no artifact_path"
        )
    artifact_checksum = _file_sha256(artifact_path)
    expected = entry.get("artifact_checksum_sha256")
    if expected and expected != artifact_checksum:
        raise ShadowScorerError(
            "model artifact checksum mismatch — pickle was modified "
            f"since registration ({expected!r} vs {artifact_checksum!r})"
        )
    pickle_payload = _load_pickle(artifact_path)
    estimator = pickle_payload.get("model")
    preprocessor = pickle_payload.get("preprocessor")
    feature_names = list(
        pickle_payload.get("feature_names") or []
    )
    task = pickle_payload.get("task") or entry.get("task")
    trained_on = pickle_payload.get("trained_on") or {}
    train_median = float(trained_on.get("train_median", 0.0))
    train_scale = float(trained_on.get("train_scale", 0.01))

    rows_excluded: dict[str, int] = {}
    scored: list[ScoredRow] = []
    rows_with_label = 0

    with sf() as session:
        observations = _read_observations(session, cfg=cfg)
        rows_input = len(observations)
        for obs in observations:
            if obs.get("is_provisional") and not cfg.include_provisional:
                rows_excluded[EXCLUDED_REASON_PROVISIONAL] = (
                    rows_excluded.get(EXCLUDED_REASON_PROVISIONAL, 0)
                    + 1
                )
                continue
            x_row, missing = _build_feature_vector(
                obs, feature_names=feature_names,
            )
            if missing:
                rows_excluded[EXCLUDED_REASON_MISSING] = (
                    rows_excluded.get(EXCLUDED_REASON_MISSING, 0) + 1
                )
                continue
            try:
                if task == "classification":
                    score = score_features_classification(
                        estimator, x_row, preprocessor=preprocessor,
                    )
                else:
                    score = score_features_regression(
                        estimator, x_row, preprocessor=preprocessor,
                        train_median=train_median,
                        train_scale=train_scale,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "score failed for obs={}: {}",
                    obs.get("observation_id"), exc,
                )
                rows_excluded[EXCLUDED_REASON_MISSING] = (
                    rows_excluded.get(EXCLUDED_REASON_MISSING, 0) + 1
                )
                continue
            bucket = assign_bucket(score, edges=cfg.bucket_edges)
            realized = obs.get("realized_label")
            if realized is not None and not obs.get("is_provisional"):
                rows_with_label += 1
            scored.append(ScoredRow(
                observation_id=str(obs["observation_id"]),
                as_of_date=str(obs["as_of_date"]),
                symbol=str(obs["symbol"]),
                source=str(obs["source"]),
                deterministic_rule_id=(
                    str(obs.get("deterministic_rule_id"))
                    if obs.get("deterministic_rule_id") else None
                ),
                deterministic_outcome=(
                    str(obs.get("deterministic_outcome"))
                    if obs.get("deterministic_outcome") else None
                ),
                deterministic_qualified=bool(
                    obs.get("deterministic_qualified", False),
                ),
                deterministic_failed_gates_count=int(
                    obs.get(
                        "deterministic_failed_gates_count", 0,
                    ) or 0,
                ),
                model_score=round(float(score), 6),
                model_bucket=bucket,
                realized_label=(
                    str(realized) if realized is not None else None
                ),
                is_provisional=bool(obs.get("is_provisional")),
                comparison_category=categorize(
                    obs.get("deterministic_outcome"),
                    bucket,
                ),
            ))

    summary = ScoringSummary(
        config=cfg,
        model_artifact_checksum_sha256=artifact_checksum,
        model_status=str(entry.get("status")),
        rows_input=rows_input,
        rows_scored=len(scored),
        rows_with_realized_label=rows_with_label,
        rows_excluded_by_reason=rows_excluded,
        rows=tuple(scored),
    )
    logger.info(
        "phase 11T shadow_score complete: dry_run={} model_id={} "
        "rows_scored={} excluded={}",
        cfg.dry_run, cfg.model_id, summary.rows_scored,
        summary.rows_excluded_by_reason,
    )
    return summary
