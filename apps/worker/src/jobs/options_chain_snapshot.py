"""Options chain snapshot worker job.

Pulls latest options chain data via the configured provider and
appends to `options_chain_snapshot` (append-only with ON CONFLICT
DO NOTHING). Runs in `compose-worker-tickloop-1` via the scheduler.

History note: this wrapper previously returned `None` on every path,
which tick_loop misclassified as `success` even on zero-work runs.
Chain ingestion was silently producing 0 new rows for 6 days while
job_run.status reported success. See
docs/research/OPTIONS_CHAIN_INGEST_FORENSIC_AUDIT.md.

The wrapper now returns structured outcomes that tick_loop can
classify honestly:

  - master flags off          → {skipped: True, reason: "master_flags_off"}
  - exception during ingest   → {return_code: 1, reason: f"exception:..."}
  - all symbols errored       → {skipped: True, reason: "all_symbols_failed"}
  - 0 new rows (dedup only)   → {skipped: True, reason: "no_new_chain_data"}
  - partial success           → {return_code: 0, reason: "partial", ...}
  - success with rows         → {return_code: 0, inserted: N, ...}

Each invocation also persists ONE row to `options_chain_ingest_run`
for queryable telemetry-of-truth (mirror of envelope_generation_run
from stocks side).

Hard-isolated from V2 / equity / governance / execution.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json as _json
import time
from typing import Any

from loguru import logger
from sqlalchemy import text as _sql_text

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.options.data.chain_ingest import (
    DEFAULT_UNIVERSE,
    ingest_universe,
)


def _write_telemetry(
    *,
    started_at: dt.datetime,
    finished_at: dt.datetime,
    provider: str,
    universe: list[str],
    summaries: list[Any] | None,
    classification: str,
    error_summary: dict | None = None,
) -> None:
    """Persist one row to options_chain_ingest_run.

    Never raises — telemetry failure does not abort the job. Logs at
    warning level if the table is missing (e.g. migration not yet
    applied).
    """
    rows_inserted = sum(getattr(s, "n_inserted", 0) for s in (summaries or []))
    rows_dedup = sum(getattr(s, "n_skipped_existing", 0) for s in (summaries or []))
    rows_filtered_out = sum(
        sum(getattr(s, "reject_counts", {}).values()) for s in (summaries or [])
    )
    n_ok = sum(1 for s in (summaries or []) if getattr(s, "status", "") == "ok")
    n_partial = sum(
        1 for s in (summaries or []) if getattr(s, "status", "") == "partial"
    )
    n_err = sum(
        1 for s in (summaries or [])
        if getattr(s, "status", "") in ("error", "skipped_unavailable", "partial_then_failed")
    )
    duration_sec = (finished_at - started_at).total_seconds()
    payload = {
        "started_at": started_at,
        "finished_at": finished_at,
        "provider": provider,
        "universe": universe,
        "rows_inserted": rows_inserted,
        "rows_dedup": rows_dedup,
        "rows_filtered_out": rows_filtered_out,
        "n_symbols_ok": n_ok,
        "n_symbols_partial": n_partial,
        "n_symbols_error": n_err,
        "classification": classification,
        "error_summary": _json.dumps(error_summary) if error_summary else None,
        "duration_sec": duration_sec,
    }
    try:
        with SessionLocal() as session:
            session.execute(
                _sql_text(
                    "INSERT INTO options_chain_ingest_run "
                    "  (started_at, finished_at, provider, universe, "
                    "   rows_inserted, rows_dedup, rows_filtered_out, "
                    "   n_symbols_ok, n_symbols_partial, n_symbols_error, "
                    "   classification, error_summary, duration_sec) "
                    "VALUES "
                    "  (:started_at, :finished_at, :provider, :universe, "
                    "   :rows_inserted, :rows_dedup, :rows_filtered_out, "
                    "   :n_symbols_ok, :n_symbols_partial, :n_symbols_error, "
                    "   :classification, "
                    "   CAST(:error_summary AS jsonb), :duration_sec)"
                ),
                payload,
            )
            session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "options_chain_snapshot telemetry write failed (table missing?): {}",
            exc,
        )


async def run_options_chain_snapshot_job() -> dict[str, Any]:
    """Scheduler entry point. Honest return values; tick_loop maps them
    to job_run.status correctly.
    """
    started_at = dt.datetime.now(dt.timezone.utc)
    provider = getattr(settings, "OPTIONS_DATA_PROVIDER", "unknown")
    universe = list(DEFAULT_UNIVERSE)

    # Master flag gate.
    if not (getattr(settings, "OPTIONS_ENABLED", False)
            or getattr(settings, "OPTIONS_SHADOW_EVAL_ENABLED", False)):
        logger.info(
            "options_chain_snapshot skipped — both OPTIONS_ENABLED and "
            "OPTIONS_SHADOW_EVAL_ENABLED are False",
        )
        finished_at = dt.datetime.now(dt.timezone.utc)
        _write_telemetry(
            started_at=started_at, finished_at=finished_at,
            provider=provider, universe=universe, summaries=None,
            classification="flags_off",
        )
        return {"skipped": True, "reason": "master_flags_off"}

    snapshot_at = started_at
    try:
        summaries = ingest_universe(
            universe=DEFAULT_UNIVERSE,
            snapshot_at_utc=snapshot_at,
        )
    except Exception as exc:  # noqa: BLE001
        finished_at = dt.datetime.now(dt.timezone.utc)
        err = {"type": type(exc).__name__, "message": str(exc)[:512]}
        logger.error(
            "options_chain_snapshot exception: {}: {}",
            type(exc).__name__, str(exc)[:512],
        )
        _write_telemetry(
            started_at=started_at, finished_at=finished_at,
            provider=provider, universe=universe, summaries=None,
            classification="error", error_summary=err,
        )
        return {
            "return_code": 1,
            "reason": f"exception:{type(exc).__name__}",
        }

    finished_at = dt.datetime.now(dt.timezone.utc)

    # Aggregate per-symbol outcomes.
    n_ok = sum(1 for s in summaries if s.status == "ok")
    n_partial = sum(1 for s in summaries if s.status == "partial")
    n_skipped = sum(
        1 for s in summaries
        if s.status in ("skipped_unavailable", "partial_then_failed")
    )
    n_error = sum(1 for s in summaries if s.status == "error")
    total_inserted = sum(s.n_inserted for s in summaries)
    total_dedup = sum(s.n_skipped_existing for s in summaries)

    logger.info(
        "options_chain_snapshot done snapshot_at={} ok={} partial={} "
        "skipped={} error={} inserted={} dedup={}",
        snapshot_at, n_ok, n_partial, n_skipped, n_error,
        total_inserted, total_dedup,
    )

    # Classification — explicit closed enum.
    if (n_ok + n_partial) == 0:
        # No symbol succeeded at all.
        _write_telemetry(
            started_at=started_at, finished_at=finished_at,
            provider=provider, universe=universe, summaries=summaries,
            classification="error",
            error_summary={"all_symbols_failed": True,
                           "n_skipped": n_skipped, "n_error": n_error},
        )
        return {"skipped": True, "reason": "all_symbols_failed"}

    if total_inserted == 0:
        # Provider returned data but everything dedup'd (no new rows
        # since previous snapshot). HONEST: this is NOT success.
        _write_telemetry(
            started_at=started_at, finished_at=finished_at,
            provider=provider, universe=universe, summaries=summaries,
            classification="no_new_data",
        )
        return {
            "skipped": True,
            "reason": "no_new_chain_data",
            "detail": {"dedup_count": total_dedup, "n_ok": n_ok},
        }

    classification = "partial" if n_partial > 0 else "success"
    _write_telemetry(
        started_at=started_at, finished_at=finished_at,
        provider=provider, universe=universe, summaries=summaries,
        classification=classification,
    )
    return {
        "return_code": 0,
        "inserted": total_inserted,
        "dedup": total_dedup,
        "classification": classification,
    }
