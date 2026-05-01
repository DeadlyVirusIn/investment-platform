"""Phase 11Z incident-response — guard tests.

Verifies the integration-harness safety check refuses URLs that look
like the dev/working DB. The guard sits in front of `drop_all` /
`create_all`, so any escape from these tests would mean another
data-loss incident is possible.

Pure-unit; no Postgres, no testcontainer. Always safe to run.
"""

from __future__ import annotations

import os

import pytest

from apps.api.tests.integration.conftest import (
    UnsafeIntegrationDatabaseError,
    _assert_test_database_url,
)


# --------------------------------------------------------------------------
# Forbidden URLs — must raise.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("url", [
    # Dev/working db reproducer from the actual incident.
    "postgresql+psycopg://invest:dev_only_password@db:5432/investment_platform",
    "postgresql://invest:x@compose-db-1:5432/investment_platform",
    "postgresql://invest:x@db:5432/production",
    "postgresql://invest:x@db:5432/prod",
    # Database name doesn't say 'test' / 'integration' anywhere.
    "postgresql://u:p@otherhost:5432/investment_platform",
    "postgresql://u:p@otherhost:5432/main_db",
])
def test_guard_rejects_unsafe_urls(url, monkeypatch):
    monkeypatch.delenv("INTEGRATION_DB_ALLOW_UNSAFE", raising=False)
    with pytest.raises(UnsafeIntegrationDatabaseError):
        _assert_test_database_url(url)


# --------------------------------------------------------------------------
# Allowed URLs — must NOT raise.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://u:p@otherhost:5432/investment_platform_test",
    "postgresql+psycopg://u:p@localhost:5432/integration_test",
    "postgresql://u:p@127.0.0.1:5432/app_integration",
    "postgresql://u:p@127.0.0.1:5432/test_db",
    "postgresql://u:p@some-runner:5432/ci_test_run_42",
])
def test_guard_accepts_safe_urls(url, monkeypatch):
    monkeypatch.delenv("INTEGRATION_DB_ALLOW_UNSAFE", raising=False)
    _assert_test_database_url(url)


# --------------------------------------------------------------------------
# Forbidden host — opt-in env still requires test-name semantics.
# --------------------------------------------------------------------------


def test_guard_unsafe_optin_still_requires_test_in_name(monkeypatch):
    monkeypatch.setenv("INTEGRATION_DB_ALLOW_UNSAFE", "1")
    # opt-in lets host 'db' through, but 'investment_platform' is on
    # the forbidden-name list and the URL doesn't contain 'test'.
    with pytest.raises(UnsafeIntegrationDatabaseError):
        _assert_test_database_url(
            "postgresql+psycopg://invest:x@db:5432/investment_platform"
        )


def test_guard_unsafe_optin_allows_test_db_on_forbidden_host(monkeypatch):
    monkeypatch.setenv("INTEGRATION_DB_ALLOW_UNSAFE", "1")
    _assert_test_database_url(
        "postgresql+psycopg://invest:x@db:5432/integration_test"
    )


# --------------------------------------------------------------------------
# Malformed URLs — must raise.
# --------------------------------------------------------------------------


def test_guard_rejects_malformed_url():
    with pytest.raises(UnsafeIntegrationDatabaseError):
        _assert_test_database_url("not a url at all")


# --------------------------------------------------------------------------
# Phase 11Z extension — DATABASE_URL cross-check + production hostnames.
# --------------------------------------------------------------------------


def test_guard_rejects_when_test_url_equals_database_url(monkeypatch):
    """Even when db name contains 'test', refuse if the URL points
    to the same host:port:db tuple as DATABASE_URL."""
    monkeypatch.delenv("INTEGRATION_DB_ALLOW_UNSAFE", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://invest:dev_only_password@elsewhere:5432/some_test_db",
    )
    with pytest.raises(UnsafeIntegrationDatabaseError):
        _assert_test_database_url(
            "postgresql+psycopg://invest:x@elsewhere:5432/some_test_db"
        )


def test_guard_allows_when_test_url_differs_from_database_url(monkeypatch):
    monkeypatch.delenv("INTEGRATION_DB_ALLOW_UNSAFE", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://invest:x@host-a:5432/investment_platform",
    )
    _assert_test_database_url(
        "postgresql+psycopg://invest:x@host-b:5432/investment_platform_test"
    )


@pytest.mark.parametrize("host", [
    "prod-pg.internal",
    "production.example.com",
    "us-east-1-prod-db",
    "PRODUCTION-rds-instance.aws",
])
def test_guard_rejects_production_host_strings(host, monkeypatch):
    monkeypatch.delenv("INTEGRATION_DB_ALLOW_UNSAFE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    url = f"postgresql+psycopg://u:p@{host}:5432/integration_test"
    with pytest.raises(UnsafeIntegrationDatabaseError):
        _assert_test_database_url(url)
