"""Alembic env.py – uses SQLAlchemy 2 metadata from ORM models.

Phase 15i.R — migration safety repair (post-incident hardening).
See docs/ops/INCIDENT_2026_05_11_dev_db_unintended_migration.md for
the incident this rewrite prevents from recurring.

URL resolution precedence (highest first):
  1. -x url=...     CLI argument (per Alembic convention; lets ad-hoc
                     invocations target a specific DB without changing
                     env vars or config files)
  2. DATABASE_URL    env variable (container default)
  3. alembic.ini     fallback (the placeholder; refuses to connect)

Defense in depth — when ALEMBIC_REQUIRE_TEST_TARGET=1 is set
(Makefile sets this for the db-clean-test target), env.py refuses
to run if the resolved DB hostname matches the known dev DB. This
is the second-layer guard the missing of which caused the incident.

EVERY invocation logs the resolved target host:port:db to stderr
BEFORE running migrations, so silent target mis-routing is no
longer possible.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from urllib.parse import urlparse

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# Import all models so their tables are registered on Base.metadata
# ---------------------------------------------------------------------------
from apps.api.src.db import Base
import apps.api.src.db.models  # noqa: F401 – side-effect: registers all ORM classes
import apps.api.src.db.options_models  # noqa: F401 – Phase 11B options schema

# ---------------------------------------------------------------------------
# Alembic Config object
# ---------------------------------------------------------------------------
config = context.config


# ---------------------------------------------------------------------------
# Phase 15i.R — URL resolution + safety guard + target logging
# ---------------------------------------------------------------------------

# Hostnames that MUST NEVER be the alembic target when the caller
# has declared "this is the test workflow" via the env var below.
# Add entries here if other dev/prod DB hostnames need protecting.
_DEV_PROD_DB_HOSTNAMES = frozenset({
    "db",                      # docker-compose dev DB service name
    "compose-db-1",            # explicit container name
    "investment_platform",     # legacy alias just in case
})


def _resolve_database_url() -> tuple[str | None, str]:
    """Return (resolved_url, source_label) per the precedence above."""
    x_args = context.get_x_argument(as_dictionary=True)
    url_from_x = x_args.get("url")
    if url_from_x:
        return url_from_x, "-x url=..."
    url_from_env = os.environ.get("DATABASE_URL")
    if url_from_env:
        return url_from_env, "DATABASE_URL env"
    return None, "alembic.ini fallback"


def _format_target_for_log(url: str | None) -> str:
    if not url:
        return "<none — alembic.ini fallback>"
    try:
        p = urlparse(url)
        host = p.hostname or "?"
        port = p.port or 5432
        db = (p.path or "/").lstrip("/") or "?"
        user = p.username or "?"
        # NEVER log the password.
        return f"{p.scheme}://{user}:***@{host}:{port}/{db}"
    except Exception:
        return "<parse failed>"


def _enforce_test_target_guard(url: str | None) -> None:
    """Phase 15i.R.3 — refuse silently-mis-routed dev mutations.

    When ALEMBIC_REQUIRE_TEST_TARGET=1 is set in the environment
    (the Makefile db-clean-test target sets this), the resolved URL's
    hostname MUST NOT be a dev/prod DB hostname. This is the second
    layer of defense (the first is correct URL routing). If the
    routing layer ever silently misfires again, this guard catches
    it BEFORE any DDL runs.
    """
    if os.environ.get("ALEMBIC_REQUIRE_TEST_TARGET") != "1":
        return
    if not url:
        raise RuntimeError(
            "ALEMBIC_REQUIRE_TEST_TARGET=1 is set but no DATABASE_URL "
            "was resolved. Refusing to run against alembic.ini fallback."
        )
    host = (urlparse(url).hostname or "").lower()
    if host in _DEV_PROD_DB_HOSTNAMES:
        raise RuntimeError(
            f"ALEMBIC_REQUIRE_TEST_TARGET=1 is set but the resolved "
            f"alembic target hostname '{host}' is a known dev/prod DB. "
            f"Refusing to run. Pass an isolated test DB URL via "
            f"`-e DATABASE_URL=postgresql+psycopg://test:test@pg-11v-test:5432/test` "
            f"or `-x url=...` to target the test container."
        )


_database_url, _url_source = _resolve_database_url()

# Log the resolved target BEFORE any migration runs. To stderr so it
# survives whatever logging configuration alembic loads next.
print(
    f"[alembic] resolved target ({_url_source}): "
    f"{_format_target_for_log(_database_url)}",
    file=sys.stderr,
)

# Safety guard runs AFTER logging so the operator sees the target the
# guard considered before refusal.
_enforce_test_target_guard(_database_url)

if _database_url:
    config.set_main_option("sqlalchemy.url", _database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# offline mode
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# online mode
# ---------------------------------------------------------------------------

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
