"""Paper exit-cycle worker job — Phase 2 stock fix Phase 5.

Schedules the existing operator-tested `scripts.run_paper_exit_cycle`
as a daily worker job. Paper-only. Next-bar fill guard preserved.

Cron target: `0 23 * * 1-5` interpreted in SCHEDULER_TZ
(America/New_York) → 23:00 ET = 03:00 UTC next day. Runs after
`ingest_prices_daily` (~02:00 UTC) so the latest close bar is
available for mark-and-rule evaluation, and 30 minutes before
`run_paper_trading` at 03:30 UTC so exits free slots before new
opens are evaluated.

Discipline locks:
  * Paper-only — relies on `submit_trade` which rejects any non-paper
    write at schema level.
  * Next-bar fill — script enforces `find_next_open` against real
    `price_bar` rows; same-bar exits are forbidden.
  * Commit mode programmatic — the script's CONFIRM_ENV gate is
    satisfied INSIDE this wrapper only. Operator CLI invocations
    still require manual env-var set.
  * No options behavior — never touches `options_*` tables.
  * Conservative defaults: TP=8%, SL=4%, MaxHold=10d.
    Overridable per env (`PAPER_TAKE_PROFIT_PCT`,
    `PAPER_STOP_LOSS_PCT`, `PAPER_MAX_HOLD_DAYS`).

OVA repair (2026-05-16) — Path B:
  * Pre-fix: wrapper invoked the script with default `as_of = today
    UTC`. With `submitted_at = combine(as_of, 15:00 UTC)`, the
    next-bar guard required a price_bar with `ts > today 15:00 UTC`,
    which only exists for a future trading day not yet ingested at
    fire time. Every fill rejected with
    "no price bar available after submitted_at; cannot fill".
  * Post-fix: wrapper computes `as_of` as the trading day BEFORE the
    most-recent ingested daily bar. Then `submitted_at = as_of 15:00
    UTC` is strictly less than the latest bar's `ts` (midnight UTC of
    a strictly later trading day), so `find_next_open` returns that
    latest bar and the fill lands at its OPEN. Decision input bar
    (`_latest_close(as_of)`) and fill output bar (`find_next_open`)
    are by construction different bars — same-bar fills remain
    impossible. This mirrors the Phase 11V semantics already used by
    `run_paper_trading`.
  * Wrapper also now raises on non-zero script return code so
    silent failure stops being recorded as `job_run.status='success'`.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
from typing import Any

from loguru import logger
from sqlalchemy import text

from scripts import run_paper_exit_cycle as _exit


def _previous_trading_day(d: dt.date) -> dt.date:
    """Return the most recent weekday strictly before ``d``."""
    cur = d - dt.timedelta(days=1)
    while cur.weekday() >= 5:  # 5=Sat, 6=Sun
        cur = cur - dt.timedelta(days=1)
    return cur


def _compute_as_of() -> dt.date:
    """Resolve the decision-input date for the exit cycle.

    Strategy: read the latest ingested daily price_bar timestamp,
    interpret its date as the most recent trading day, and return the
    weekday before it. The script's `submitted_at = combine(as_of,
    15:00 UTC)` will then be strictly less than the latest bar's `ts`
    (midnight UTC of a later trading day), so `find_next_open`
    resolves to the latest bar and fills land at its OPEN.

    Raises if no daily bars are ingested.
    """
    # Imported lazily so module import does not require a DB session.
    from apps.api.src.db import SessionLocal

    with SessionLocal() as session:
        latest_ts = session.execute(
            text("SELECT MAX(ts) FROM price_bar WHERE timeframe='1d'"),
        ).scalar()

    if latest_ts is None:
        raise RuntimeError(
            "[run_paper_exit_cycle_job] no daily price bars ingested; "
            "cannot anchor as_of."
        )

    return _previous_trading_day(latest_ts.date())


async def run_paper_exit_cycle_job() -> dict[str, Any]:
    """Run the paper exit-cycle in commit mode.

    Returns a summary dict for `job_run` telemetry. The script
    itself writes a detailed artifact to
    `artifacts/paper_exit_cycle/exit_cycle_<date>.json`.

    Raises RuntimeError if the underlying script exits non-zero so
    the scheduler records `job_run.status='error'` instead of
    silently masking the failure as 'success'.
    """
    # Satisfy the script's CONFIRM_ENV gate. Setting it here keeps
    # the safety check intact for ad-hoc CLI invocations elsewhere.
    os.environ[_exit.CONFIRM_ENV] = _exit.CONFIRM_VALUE

    as_of = _compute_as_of()
    logger.info(
        "[run_paper_exit_cycle_job] starting commit run "
        "(as_of={}, TP/SL/MaxHold=env-overridable defaults 8% / 4% / 10d)",
        as_of.isoformat(),
    )
    try:
        # Phase L M079: scheduled fires are 'live' by truth-contract.
        rc = await asyncio.to_thread(
            _exit.main,
            ["--commit", "--as-of", as_of.isoformat(), "--source", "live"],
        )
    except SystemExit as e:
        rc = int(e.code) if isinstance(e.code, int) else 1
    except Exception as exc:  # noqa: BLE001
        logger.error("[run_paper_exit_cycle_job] raised: {}", exc)
        raise
    finally:
        # Clear the env var so other code in the same worker process
        # cannot accidentally re-enter commit mode.
        os.environ.pop(_exit.CONFIRM_ENV, None)

    if rc != 0:
        raise RuntimeError(
            f"run_paper_exit_cycle returned non-zero code {rc}; "
            f"see worker logs and artifacts/paper_exit_cycle/ for details.",
        )

    return {"return_code": rc, "as_of": as_of.isoformat()}
