"""M6 — pure preflight config-validation tests (no DB)."""

from __future__ import annotations

from apps.api.src.api.preflight import config_ok, evaluate_config

SAFE_ENV = {"DATABASE_URL": "postgresql+psycopg://u:p@db/x", "FERNET_KEY": "k"}
PROD_ORIGINS = ["https://app.arthos.example"]


def _prod(**over):
    base = dict(
        mode="prod", auth_disabled_local=False, demo_device_mode=False,
        session_cookie_secure=True, cors_origins=PROD_ORIGINS, env=SAFE_ENV,
    )
    base.update(over)
    return evaluate_config(**base)


def _keys(issues, level=None):
    return {i.key for i in issues if level is None or i.level == level}


def test_safe_prod_config_passes():
    issues = _prod()
    assert issues == []
    assert config_ok(issues, mode="prod") is True


def test_auth_disabled_local_fails_prod():
    issues = _prod(auth_disabled_local=True)
    assert "AUTH_DISABLED_LOCAL" in _keys(issues, "error")
    assert config_ok(issues, mode="prod") is False


def test_demo_device_mode_fails_prod():
    issues = _prod(demo_device_mode=True)
    assert "DEMO_DEVICE_MODE" in _keys(issues, "error")
    assert config_ok(issues, mode="prod") is False


def test_session_cookie_secure_false_fails_prod():
    issues = _prod(session_cookie_secure=False)
    assert "SESSION_COOKIE_SECURE" in _keys(issues, "error")
    assert config_ok(issues, mode="prod") is False


def test_missing_required_env_reported():
    issues = _prod(env={"DATABASE_URL": "x"})  # FERNET_KEY missing
    assert "FERNET_KEY" in _keys(issues, "error")
    assert config_ok(issues, mode="prod") is False


def test_no_cors_origins_fails_prod():
    issues = _prod(cors_origins=[])
    assert "CORS" in _keys(issues, "error")


def test_dev_mode_does_not_block_local_dev():
    # The real local dev config: unsafe flags on, insecure cookie, localhost CORS.
    issues = evaluate_config(
        mode="dev", auth_disabled_local=True, demo_device_mode=True,
        session_cookie_secure=False, cors_origins=["http://localhost:5173"], env=SAFE_ENV,
    )
    # Warnings are emitted, but dev mode never blocks.
    assert all(i.level == "warn" for i in issues)
    assert config_ok(issues, mode="dev") is True
