"""Nightly ML diagnostics job.

Thin wrapper — invoked by whatever scheduler the operator uses (cron,
APScheduler, Airflow). Idempotent: each call produces one snapshot row.

Usage (from repo root):

    python -m apps.api.src.jobs.nightly_ml_diagnostics
"""

from __future__ import annotations

import argparse
import sys

from loguru import logger

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.ml.snapshots import capture_snapshot


def run(persist: bool = True, min_training_rows: int | None = None) -> dict:
    min_rows = min_training_rows or int(
        getattr(settings, "ML_MIN_TRAINING_ROWS", 1000)
    )
    logger.info(
        "nightly_ml_diagnostics: starting (min_training_rows={})", min_rows,
    )
    with SessionLocal() as session:
        rec = capture_snapshot(
            session, min_training_rows=min_rows, persist=persist,
        )
    logger.info(
        "nightly_ml_diagnostics: rows={} labeled={} tier={} leakage_clean={} "
        "engine_c_status={}",
        rec.row_count, rec.labeled_row_count, rec.tier, rec.leakage_clean,
        rec.payload.get("engine_c_status", {}).get("engine_c_ml_status"),
    )
    return rec.to_dict()


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run nightly ML diagnostics + persist snapshot.",
    )
    p.add_argument("--no-persist", action="store_true",
                   help="compute only; skip DB write")
    p.add_argument("--min-rows", type=int, default=None,
                   help="override ML_MIN_TRAINING_ROWS")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse()
    try:
        run(persist=not args.no_persist, min_training_rows=args.min_rows)
    except Exception as e:
        logger.exception("nightly_ml_diagnostics failed: {}", e)
        sys.exit(1)
