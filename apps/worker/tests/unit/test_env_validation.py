"""P6D.36A — worker boot env validation unit tests."""

from __future__ import annotations

import pytest

from apps.worker.src.env_validation import (
    ALLOWED_OPTIONS_PROVIDERS,
    GATE_VARS,
    REQUIRED_VARS,
    enforce,
    gate_summary,
    validate_env,
)


def _good_env(**overrides: str) -> dict[str, str]:
    env = {
        "DATABASE_URL": "postgresql+psycopg://u:p@db:5432/investment_platform",
        "TIINGO_API_KEY": "tiingo-key",
        "FRED_API_KEY": "fred-key",
        "FERNET_KEY": "fernet-key",
        "OPTIONS_DATA_PROVIDER": "tradier",
    }
    env.update(overrides)
    return env


# ---------------------------------------------------------------- validate_env

def test_good_env_has_no_problems() -> None:
    assert validate_env(_good_env()) == []


@pytest.mark.parametrize("name", REQUIRED_VARS)
def test_missing_required_var_is_named(name: str) -> None:
    env = _good_env()
    del env[name]
    problems = validate_env(env)
    assert len(problems) == 1
    assert name in problems[0]


@pytest.mark.parametrize("name", REQUIRED_VARS)
def test_blank_required_var_is_named(name: str) -> None:
    problems = validate_env(_good_env(**{name: "   "}))
    assert len(problems) == 1
    assert name in problems[0]


def test_blank_credentials_database_url_flagged() -> None:
    # The exact 2026-05 incident shape: compose up without --env-file.
    problems = validate_env(
        _good_env(DATABASE_URL="postgresql+psycopg://:@db:5432/")
    )
    assert any("--env-file" in p for p in problems)


def test_unknown_options_provider_flagged_with_allowed_list() -> None:
    problems = validate_env(_good_env(OPTIONS_DATA_PROVIDER="thetadta"))
    assert len(problems) == 1
    for allowed in ALLOWED_OPTIONS_PROVIDERS:
        assert allowed in problems[0]


@pytest.mark.parametrize("provider", ALLOWED_OPTIONS_PROVIDERS)
def test_known_providers_pass(provider: str) -> None:
    assert validate_env(_good_env(OPTIONS_DATA_PROVIDER=provider)) == []


def test_absent_provider_is_not_a_problem() -> None:
    # Compose always injects a default; absent var must not fail boot.
    env = _good_env()
    del env["OPTIONS_DATA_PROVIDER"]
    assert validate_env(env) == []


# ---------------------------------------------------------------- gate_summary

def test_gate_summary_covers_all_gate_vars_and_marks_unset() -> None:
    summary = gate_summary({"OPTIONS_ENABLED": "false"})
    assert set(summary) == set(GATE_VARS)
    assert summary["OPTIONS_ENABLED"] == "false"
    assert summary["OPTIONS_CANARY_ENABLED"] == "<unset>"


# --------------------------------------------------------------------- enforce

def test_enforce_warn_mode_returns_problems_without_exiting() -> None:
    env = _good_env(WORKER_ENV_VALIDATION="warn")
    del env["TIINGO_API_KEY"]
    problems = enforce(env)
    assert len(problems) == 1
    assert "TIINGO_API_KEY" in problems[0]


def test_enforce_default_mode_is_warn() -> None:
    env = _good_env()  # no WORKER_ENV_VALIDATION key
    del env["FERNET_KEY"]
    problems = enforce(env)
    assert len(problems) == 1


def test_enforce_strict_mode_exits_on_problem() -> None:
    env = _good_env(WORKER_ENV_VALIDATION="strict")
    del env["DATABASE_URL"]
    with pytest.raises(SystemExit) as exc_info:
        enforce(env)
    assert exc_info.value.code == 1


def test_enforce_strict_mode_passes_clean_env() -> None:
    assert enforce(_good_env(WORKER_ENV_VALIDATION="strict")) == []


def test_enforce_off_mode_skips_checks() -> None:
    env = _good_env(WORKER_ENV_VALIDATION="off")
    del env["DATABASE_URL"]  # would fail in warn/strict
    assert enforce(env) == []
