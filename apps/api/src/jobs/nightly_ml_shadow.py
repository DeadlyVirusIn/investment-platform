"""Nightly ML shadow job.

Usage:
    python -m apps.api.src.jobs.nightly_ml_shadow
"""

from __future__ import annotations

import argparse
import sys

from loguru import logger

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.ml.shadow import run_nightly_shadow
from apps.api.src.ml.shadow.trainer import ModelType


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Nightly shadow ML job.")
    p.add_argument("--no-persist", action="store_true")
    p.add_argument("--min-rows", type=int, default=None)
    p.add_argument(
        "--dataset-source",
        choices=("real", "replay", "combined"),
        default="real",
    )
    p.add_argument(
        "--model-types",
        default=getattr(
            settings, "ML_SHADOW_MODEL_TYPES",
            "logistic,ridge,rf",
        ),
    )
    return p.parse_args()


def main() -> int:
    if not getattr(settings, "ML_SHADOW_ENABLED", True):
        logger.info("shadow disabled via ML_SHADOW_ENABLED=false")
        return 0
    args = _parse()
    min_rows = args.min_rows or int(
        getattr(settings, "ML_SHADOW_MIN_ROWS", 1000)
    )
    types = tuple(
        ModelType(m.strip())
        for m in args.model_types.split(",")
        if m.strip() and m.strip() in {"logistic", "ridge", "rf", "gbm"}
    ) or (ModelType.LOGISTIC,)

    with SessionLocal() as s:
        result = run_nightly_shadow(
            s,
            min_training_rows=min_rows,
            dataset_source=args.dataset_source,
            model_types=types,
            persist=not args.no_persist,
        )
    logger.info(
        "shadow done: run_id={} status={} n_scored={} winner={}",
        result.model_run_id, result.status, result.n_scored, result.winner,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
