"""SYSTEM-ALPHA-2 nightly activation job.

Runs all 4 writers + final coverage report. Each phase isolated in
try/except so one failure never kills the others. Persists audit row in
job_run_log.

Usage:
    python -m apps.api.src.jobs.alpha_nightly
    python -m apps.api.src.jobs.alpha_nightly --dry-run
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import uuid
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.alpha.activation import (
    process_decision_attribution, process_paper_trades,
    write_provider_reliability, write_system_health_score,
)
from apps.api.src.alpha.coverage_report import build_coverage_report
from apps.api.src.db import SessionLocal


JOB_NAME = "alpha_nightly"


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=JOB_NAME)
    p.add_argument("--dry-run", action="store_true",
                   help="compute + log but do not write")
    p.add_argument("--batch", type=int, default=500)
    return p.parse_args()


def run(dry_run: bool = False, batch: int = 500) -> dict[str, Any]:
    started_at = dt.datetime.now(dt.timezone.utc)
    run_id = str(uuid.uuid4())
    phases: dict[str, Any] = {}
    warnings: list[str] = []
    errors: list[str] = []
    status = "completed"

    with SessionLocal() as session:
        _insert_job_start(session, run_id, dry_run=dry_run)

        # PHASE 1 — factor attribution
        try:
            phases["decision_attribution"] = process_decision_attribution(
                session, dry_run=dry_run, batch=batch,
            )
            logger.info("phase1 done: {}", phases["decision_attribution"])
        except Exception as e:
            errors.append(f"decision_attribution: {type(e).__name__} {e}")
            logger.exception("phase1 failed")

        # PHASE 2 — paper trades (exec quality + failure)
        try:
            phases["paper_trades"] = process_paper_trades(
                session, dry_run=dry_run, batch=batch,
            )
            logger.info("phase2 done: {}", phases["paper_trades"])
        except Exception as e:
            errors.append(f"paper_trades: {type(e).__name__} {e}")
            logger.exception("phase2 failed")

        # PHASE 3 — system health
        try:
            phases["system_health"] = write_system_health_score(
                session, dry_run=dry_run,
            )
            logger.info("phase3 done: {}", phases["system_health"])
        except Exception as e:
            errors.append(f"system_health: {type(e).__name__} {e}")
            logger.exception("phase3 failed")

        # PHASE 4 — provider reliability
        try:
            phases["provider_reliability"] = write_provider_reliability(
                session, dry_run=dry_run,
            )
            logger.info(
                "phase4 done: {}", phases["provider_reliability"],
            )
        except Exception as e:
            errors.append(f"provider_reliability: {type(e).__name__} {e}")
            logger.exception("phase4 failed")

        # PHASE 5 — coverage validation
        try:
            coverage = build_coverage_report(session).to_dict()
            phases["coverage"] = coverage
            warnings.extend(coverage.get("warnings") or [])
        except Exception as e:
            errors.append(f"coverage: {type(e).__name__} {e}")

        if errors and len(errors) >= 3:
            status = "failed"
        elif errors:
            status = "completed_with_errors"

        _finalize_job(
            session, run_id,
            status=status, dry_run=dry_run,
            phases=phases, warnings=warnings, errors=errors,
        )

    result = {
        "run_id": run_id,
        "status": status,
        "started_at": started_at.isoformat(),
        "phases": phases,
        "warnings": warnings,
        "errors": errors,
    }
    logger.info("alpha_nightly done: status={} phases={}",
                status, list(phases.keys()))
    return result


# ---------------------------------------------------------------------------

def _insert_job_start(
    session: Session, run_id: str, *, dry_run: bool,
) -> None:
    try:
        session.execute(text("""
            INSERT INTO job_run_log (id, job_name, status, dry_run)
            VALUES (:id, :jn, 'running', :dr)
        """), {"id": run_id, "jn": JOB_NAME, "dr": dry_run})
        session.commit()
    except Exception as e:
        logger.warning("job_run_log insert failed: {}", e)


def _finalize_job(
    session: Session, run_id: str, *,
    status: str, dry_run: bool,
    phases: dict[str, Any], warnings: list[str], errors: list[str],
) -> None:
    try:
        session.execute(text("""
            UPDATE job_run_log
               SET finished_at = :fin,
                   status      = :st,
                   phases      = CAST(:p AS jsonb),
                   summary     = CAST(:s AS jsonb),
                   warnings    = CAST(:w AS jsonb),
                   errors      = CAST(:e AS jsonb)
             WHERE id = :id
        """), {
            "fin": dt.datetime.now(dt.timezone.utc),
            "st":  status,
            "p":   json.dumps(phases, default=str),
            "s":   json.dumps(_summary(phases), default=str),
            "w":   json.dumps(warnings, default=str),
            "e":   json.dumps(errors, default=str),
            "id":  run_id,
        })
        session.commit()
    except Exception as e:
        logger.warning("job_run_log finalize failed: {}", e)


def _summary(phases: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision_attribution_processed": phases.get(
            "decision_attribution", {}).get("processed", 0),
        "paper_trades_eq_written": phases.get(
            "paper_trades", {}).get("execution_quality_written", 0),
        "paper_trades_fa_written": phases.get(
            "paper_trades", {}).get("failure_analysis_written", 0),
        "health_overall": phases.get(
            "system_health", {}).get("overall"),
        "provider_rows": phases.get(
            "provider_reliability", {}).get("written", 0),
        "coverage": phases.get("coverage"),
    }


def main() -> int:
    args = _parse()
    try:
        run(dry_run=args.dry_run, batch=int(args.batch))
    except Exception as e:
        logger.exception("alpha_nightly crashed: {}", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
