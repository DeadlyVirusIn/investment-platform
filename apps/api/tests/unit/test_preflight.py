"""M6 — pure preflight config-validation tests (no DB)."""

from __future__ import annotations

from apps.api.src.api.preflight import config_ok, evaluate_config, parse_cors_origins

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


# --- M6A CORS ---
def test_parse_cors_origins_default_includes_localhost():
    assert parse_cors_origins("http://localhost:5173") == ["http://localhost:5173"]


def test_parse_cors_origins_comma_separated_and_whitespace():
    assert parse_cors_origins(" https://a.example , https://b.example ,,") == [
        "https://a.example", "https://b.example",
    ]
    assert parse_cors_origins("") == []
    assert parse_cors_origins(None) == []


def test_wildcard_rejected_with_credentials():
    issues = _prod(cors_origins=["*"])
    assert "CORS" in _keys(issues, "error")
    assert config_ok(issues, mode="prod") is False
    # also flagged (as an error issue) even in dev mode
    dev = evaluate_config(
        mode="dev", auth_disabled_local=False, demo_device_mode=False,
        session_cookie_secure=True, cors_origins=["*"], env=SAFE_ENV,
    )
    assert any(i.key == "CORS" and i.level == "error" for i in dev)


def test_localhost_only_fails_prod():
    issues = _prod(cors_origins=["http://localhost:5173"])
    assert "CORS" in _keys(issues, "error")
    assert config_ok(issues, mode="prod") is False


def test_mixed_localhost_plus_real_origin_warns_not_blocks():
    issues = _prod(cors_origins=["http://localhost:5173", "https://app.arthos.example"])
    cors = [i for i in issues if i.key == "CORS"]
    assert cors and all(i.level == "warn" for i in cors)
    assert config_ok(issues, mode="prod") is True


def test_safe_prod_https_origin_passes():
    issues = _prod(cors_origins=["https://app.arthos.example"])
    assert [i for i in issues if i.key == "CORS"] == []
    assert config_ok(issues, mode="prod") is True
