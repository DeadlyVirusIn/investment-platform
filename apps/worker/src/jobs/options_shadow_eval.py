"""Phase Opt-B3a Step 4 — options shadow evaluator worker wrapper.

Wraps `apps.api.src.options.shadow_evaluator.evaluate()` for scheduler
integration. Inert until BOTH conditions are met:

  1. ``settings.OPTIONS_ENABLED`` is True            (master flag)
  2. a row in ``job_schedule`` references this job   (scheduler wiring)

Even when wired, persistence to ``options_shadow_decision_log`` only
happens when ``settings.OPTIONS_SHADOW_EVAL_ENABLED`` is ALSO True.
Default config has both flags False → wrapper runs in dry-mode only.

Hard rules
----------
* NEVER opens ``options_paper_trade`` rows. NEVER mutates lifecycle.
  Evaluator's only write target is ``options_shadow_decision_log`` and
  only when ``persist=True``.
* Idempotent at row level: evaluator dedups on
  ``(run_date, option_symbol)``.
* Logs provider + provider-version tagging from settings
  (``OPTIONS_DATA_PROVIDER``).
* Logs runtime timing metrics (wall-clock + DB-session elapsed).
* Returns an explicit summary ``dict`` for ad-hoc / dry-run / unit-test
  use. Scheduler ignores the return value; the summary is also logged.

Manual ad-hoc entry point: :func:`run_dry_manual` forces ``persist=False``
regardless of flag state. Intended for operator-driven validation
before Step-5 scheduler activation.
"""

from __future__ import annotations

import datetime as dt
import time
from typing import Any

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.options.data_provider._redact import safe_logger as logger
from apps.api.src.options.shadow_evaluator import evaluate


# ---------------------------------------------------------------------------
# Persistence resolver — two-flag gate
# ---------------------------------------------------------------------------

def _resolve_persist() -> bool:
    """Persistence requires BOTH master flag AND shadow-eval flag.
    Either being False forces dry-run."""
    if not bool(getattr(settings, "OPTIONS_ENABLED", False)):
        return False
    return bool(getattr(settings, "OPTIONS_SHADOW_EVAL_ENABLED", False))


# ---------------------------------------------------------------------------
# Single-pass internal
# ---------------------------------------------------------------------------

def _run_one(
    *,
    run_date: dt.date,
    persist: bool,
    underlyings: list[str] | None = None,
) -> dict[str, Any]:
    """Single shadow-eval pass. Pure-orchestration with explicit args.

    Returns a fully-typed summary dict suitable for JSON serialization,
    log emission, and unit-test assertions.
    """
    t0 = time.perf_counter()
    with SessionLocal() as session:
        summary, _decisions = evaluate(
            session,
            run_date=run_date,
            underlyings=underlyings,
            persist=persist,
        )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return {
        # Evaluator-supplied counts
        "run_date":              summary.run_date.isoformat(),
        "underlying_count":      summary.underlying_count,
        "contracts_evaluated":   summary.contracts_evaluated,
        "would_trade_count":     summary.would_trade_count,
        "blocked_reason_counts": dict(summary.blocked_reason_counts),
        "freshness_warnings":    list(summary.freshness_warnings),
        "inserted":              summary.inserted,
        # Wrapper-supplied context
        "persist":               persist,
        "options_enabled":
            bool(getattr(settings, "OPTIONS_ENABLED", False)),
        "options_shadow_eval_enabled":
            bool(getattr(settings, "OPTIONS_SHADOW_EVAL_ENABLED", False)),
        "options_data_provider":
            getattr(settings, "OPTIONS_DATA_PROVIDER", "unknown"),
        # Runtime metrics
        "elapsed_ms": round(elapsed_ms, 1),
    }


# ---------------------------------------------------------------------------
# Scheduler entry point
# ---------------------------------------------------------------------------

async def run_options_shadow_eval_job() -> None:
    """Scheduler entry point. No args. Today's run_date. Logs summary.

    Behavior matrix:
      * OPTIONS_ENABLED=False  → skip immediately, no DB session opened
      * OPTIONS_ENABLED=True & SHADOW_EVAL_ENABLED=False → dry-mode run
      * BOTH=True              → persisted run (writes to
                                  options_shadow_decision_log only)

    NEVER touches options_paper_trade. NEVER touches lifecycle table.
    """
    if not bool(getattr(settings, "OPTIONS_ENABLED", False)):
        logger.info(
            "options_shadow_eval skipped — OPTIONS_ENABLED=False")
        return

    run_date = dt.date.today()
    persist = _resolve_persist()

    logger.info(
        "options_shadow_eval start date={} persist={} provider={}",
        run_date, persist,
        getattr(settings, "OPTIONS_DATA_PROVIDER", "unknown"),
    )

    result = _run_one(run_date=run_date, persist=persist)

    logger.info(
        "options_shadow_eval done date={} underlyings={} contracts={} "
        "would_trade={} blocked_reasons={} inserted={} elapsed_ms={}",
        result["run_date"],
        result["underlying_count"],
        result["contracts_evaluated"],
        result["would_trade_count"],
        len(result["blocked_reason_counts"]),
        result["inserted"],
        result["elapsed_ms"],
    )


# ---------------------------------------------------------------------------
# Operator-only ad-hoc dry-run
# ---------------------------------------------------------------------------

def run_dry_manual(
    *,
    run_date: dt.date | None = None,
    underlyings: list[str] | None = None,
) -> dict[str, Any]:
    """Operator-only dry-run entry point. Forces ``persist=False``
    regardless of flag state. Returns the summary dict.

    Intended for ad-hoc validation, unit tests, and Step-5 pre-flight.
    NEVER persists.
    """
    if run_date is None:
        run_date = dt.date.today()
    logger.info(
        "options_shadow_eval dry-manual start date={} provider={} "
        "underlyings={}",
        run_date,
        getattr(settings, "OPTIONS_DATA_PROVIDER", "unknown"),
        underlyings or "ALL",
    )
    out = _run_one(
        run_date=run_date, persist=False, underlyings=underlyings)
    logger.info(
        "options_shadow_eval dry-manual done date={} contracts={} "
        "would_trade={} elapsed_ms={} (persist forced False)",
        out["run_date"], out["contracts_evaluated"],
        out["would_trade_count"], out["elapsed_ms"],
    )
    return out
