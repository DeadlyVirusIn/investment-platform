"""Worker boot-time environment validation — P6D.36A.

Catches the recurring failure class where a missing or mistyped env key
silently degrades scheduled behavior instead of failing loudly. Prior
incidents of this class:

  * P6B.6  — worker-cron missing OPTIONS_SHADOW_EVAL_ENABLED → shadow
             eval ran in dry mode, 0 rows persisted.
  * P6D.4  — worker-cron missing OPTIONS_GENERATOR_STRUCTURES → credit
             pass (SPCS/IC) silently skipped on cron-claimed generation.
  * P6D.16 — worker-cron defaulted OPTIONS_DATA_PROVIDER to a broken
             adapter → cron chain ingestion failed.
  * 2026-05 — compose run without --env-file → ${POSTGRES_*} blank →
             DATABASE_URL "postgresql+psycopg://:@db:5432/" → auth fail.

Modes via WORKER_ENV_VALIDATION:
  * "warn"   (default) — log every problem at WARNING, continue boot.
  * "strict"           — log every problem at ERROR, exit(1).
  * "off"              — skip problem checks (gate summary still logged).

The gate summary is always logged at INFO so every boot records the
effective trading-relevant gate values (the "boot-log gate value"
dress-rehearsal item: gate-flip + stale-worker env drift becomes
visible in `docker logs` instead of silent).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping

from loguru import logger

# Vars that must be present AND non-blank for the worker to do useful
# work. All four are passed by compose without defaults — a missing
# .env key arrives here as "" (empty string), not as an absent var.
REQUIRED_VARS: tuple[str, ...] = (
    "DATABASE_URL",
    "TIINGO_API_KEY",
    "FRED_API_KEY",
    "FERNET_KEY",
)

# Mirror of chain_ingest._build_adapter's dispatch — kept as a literal
# (not imported) so validation never pulls provider adapters at boot.
ALLOWED_OPTIONS_PROVIDERS: tuple[str, ...] = ("thetadata", "finnhub", "tradier")

# Trading-relevant gates logged on every boot. Order = display order.
GATE_VARS: tuple[str, ...] = (
    "OPTIONS_ENABLED",
    "OPTIONS_CANARY_ENABLED",
    "OPTIONS_SHADOW_EVAL_ENABLED",
    "OPTIONS_DATA_PROVIDER",
    "OPTIONS_GENERATOR_STRUCTURES",
    "OPTIONS_CANARY_UNIVERSE",
    "OPTIONS_PERSIST_LEGS",
    "PAPER_MAX_HOLD_DAYS",
    "ML_CAN_AFFECT_TRADES",
    "ML_HYBRID_ENABLED",
    "ENGINE_B_MODE",
    "WORKER_ENV_VALIDATION",
)

_BLANK_CREDENTIALS_MARKER = "://:@"


def validate_env(env: Mapping[str, str]) -> list[str]:
    """Pure check — returns a list of human-readable problems (empty = ok)."""
    problems: list[str] = []

    for name in REQUIRED_VARS:
        value = env.get(name, "")
        if not value.strip():
            problems.append(
                f"required env var {name} is missing or blank "
                f"(compose passes it through without a default — "
                f"check .env / --env-file)"
            )

    db_url = env.get("DATABASE_URL", "")
    if _BLANK_CREDENTIALS_MARKER in db_url:
        problems.append(
            "DATABASE_URL has blank credentials ('://:@…') — compose was "
            "started without --env-file .env so ${POSTGRES_*} expanded empty"
        )

    provider = env.get("OPTIONS_DATA_PROVIDER", "").strip()
    if provider and provider not in ALLOWED_OPTIONS_PROVIDERS:
        problems.append(
            f"OPTIONS_DATA_PROVIDER={provider!r} is not a known provider; "
            f"supported: {', '.join(ALLOWED_OPTIONS_PROVIDERS)}"
        )

    return problems


def gate_summary(env: Mapping[str, str]) -> dict[str, str]:
    """Effective gate values for boot logging. '<unset>' marks vars the
    process never received (vs explicitly set to empty)."""
    return {name: env.get(name, "<unset>") for name in GATE_VARS}


def enforce(env: Mapping[str, str] | None = None) -> list[str]:
    """Log the gate summary, run validation per WORKER_ENV_VALIDATION
    mode, and return the problem list. strict mode exits(1) on problems."""
    if env is None:
        env = os.environ
    mode = env.get("WORKER_ENV_VALIDATION", "warn").strip().lower() or "warn"

    for name, value in gate_summary(env).items():
        logger.info("env gate {} = {}", name, value)

    if mode == "off":
        logger.info("env validation skipped (WORKER_ENV_VALIDATION=off)")
        return []

    problems = validate_env(env)
    if not problems:
        logger.info("env validation passed ({} mode)", mode)
        return []

    if mode == "strict":
        for p in problems:
            logger.error("env validation: {}", p)
        logger.error(
            "env validation failed with {} problem(s) — refusing to start "
            "(WORKER_ENV_VALIDATION=strict)", len(problems),
        )
        sys.exit(1)

    for p in problems:
        logger.warning("env validation: {}", p)
    logger.warning(
        "env validation found {} problem(s) — continuing because "
        "WORKER_ENV_VALIDATION={} (set to 'strict' to fail boot)",
        len(problems), mode,
    )
    return problems
