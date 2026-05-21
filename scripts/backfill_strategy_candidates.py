"""Phase B6.4 — backfill options_strategy_candidate from existing
options_shadow_decision_log rows.

One-shot. Processes every `would_trade=true` observation that does not
yet have a candidate row. Idempotent: re-running is a no-op because
the generator skips observations already enriched.

Read-only against shadow_decision_log + chain_snapshot + feature_daily.
Write-only against options_strategy_candidate.

Usage (host):
    docker exec -e PYTHONPATH=/app compose-api-1 \
        python -m scripts.backfill_strategy_candidates [--dry-run]

Usage (worker container, inside cron crew):
    PYTHONPATH=/app python -m scripts.backfill_strategy_candidates

Exit codes: 0 success, 1 failure.
"""

from __future__ import annotations

import argparse
import sys

from loguru import logger

from apps.api.src.db import SessionLocal
from apps.api.src.options.strategy_candidates.service import (
    generate_for_observations,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="backfill_strategy_candidates",
        description=(
            "Generate options_strategy_candidate rows for every "
            "accepted shadow observation that lacks them."
        ),
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Process rows but DO NOT commit. Useful for "
             "validation; the service module still uses idempotent "
             "ON CONFLICT writes regardless, so re-running after a "
             "real run is safe.",
    )
    args = p.parse_args(argv)

    # Pre-flight: how many candidates can be enriched?
    with SessionLocal() as session:
        from sqlalchemy import text
        n_total = session.execute(text(
            "SELECT COUNT(*) FROM options_shadow_decision_log "
            "WHERE would_trade = TRUE"
        )).scalar() or 0
        n_enriched = session.execute(text(
            "SELECT COUNT(DISTINCT shadow_observation_id) "
            "FROM options_strategy_candidate"
        )).scalar() or 0
        pending = int(n_total) - int(n_enriched)
        logger.info(
            "[backfill] total_accepted={} already_enriched={} pending={}",
            n_total, n_enriched, pending,
        )
        if pending == 0:
            logger.info("[backfill] nothing to do.")
            return 0

    if args.dry_run:
        logger.info(
            "[backfill] dry-run mode — counts above; no work performed."
        )
        return 0

    with SessionLocal() as session:
        stats = generate_for_observations(session, skip_existing=True)
    logger.info(
        "[backfill] processed={} candidates_generated={} "
        "inserted={} skipped_already_enriched={}",
        stats["processed"],
        stats["candidates_generated"],
        stats["inserted"],
        stats["skipped_already_enriched"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
