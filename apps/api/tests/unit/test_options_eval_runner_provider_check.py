"""Phase 11O.1 - Provider-check CLI tests."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from apps.api.src.options.data_provider import thetadata_adapter as ta_mod
from apps.api.src.options.data_provider.thetadata_adapter import (
    ThetaDataAdapter,
    ThetaDataConfig,
)
from scripts import run_options_paper_eval as cli


def _ok_settings(**kw):
    base = dict(
        OPTIONS_ENABLED=True,
        OPTIONS_PAPER_ONLY=True,
        OPTIONS_ML_CAN_AFFECT_TRADES=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _patch_real_settings(monkeypatch, **kw):
    """Patch the live `settings` so default ThetaDataAdapter() succeeds."""
    from apps.api.src.config import settings
    for k, v in kw.items():
        monkeypatch.setattr(settings, k, v)


def _patch_safety(monkeypatch):
    monkeypatch.setattr(
        cli, "assert_safety_invariants", lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        cli, "assert_no_scheduler_drift", lambda: None,
    )
    # Provide a non-empty base URL so `assert_settings_provided`
    # (called inside _check_provider) does not short-circuit.
    _patch_real_settings(
        monkeypatch,
        THETADATA_BASE_URL="http://127.0.0.1:25510",
        THETADATA_API_KEY=None,
        THETADATA_USERNAME=None,
        THETADATA_PASSWORD=None,
    )


def _adapter_factory(transport: httpx.MockTransport):
    cfg = ThetaDataConfig(
        base_url="http://127.0.0.1:25510",
        max_retries=0, rate_limit_qps=1000.0,
    )
    client = httpx.Client(
        transport=transport, base_url=cfg.base_url,
        headers={"Accept": "application/json"}, timeout=cfg.timeout_seconds,
    )
    return lambda: ThetaDataAdapter(
        config=cfg, http_client=client, sleeper=lambda _s: None,
    )


def test_check_provider_prints_ok_and_exits_0(monkeypatch, capsys):
    _patch_safety(monkeypatch)
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"status": "ok"}),
    )
    monkeypatch.setattr(
        ta_mod, "ThetaDataAdapter", _adapter_factory(transport),
    )
    rc = cli.main(["--check-provider"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ok=true" in out
    assert "status=200" in out
    assert "auth_mode=" in out


def test_check_provider_prints_failure_and_exits_3(monkeypatch, capsys):
    _patch_safety(monkeypatch)
    transport = httpx.MockTransport(
        lambda req: httpx.Response(401, text="unauthorized"),
    )
    monkeypatch.setattr(
        ta_mod, "ThetaDataAdapter", _adapter_factory(transport),
    )
    rc = cli.main(["--check-provider"])
    err = capsys.readouterr().err
    assert rc == 3
    assert "ok=false" in err
    assert "401" in err


def test_check_provider_does_not_call_step_ingest_chain(monkeypatch):
    _patch_safety(monkeypatch)
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"status": "ok"}),
    )
    monkeypatch.setattr(
        ta_mod, "ThetaDataAdapter", _adapter_factory(transport),
    )

    from apps.api.src.options.paper import eval_runner

    def boom(*a, **kw):
        raise AssertionError("step_ingest_chain must not be called")

    monkeypatch.setattr(eval_runner, "step_ingest_chain", boom)
    rc = cli.main(["--check-provider"])
    assert rc == 0


def test_check_provider_does_not_open_db_session(monkeypatch):
    _patch_safety(monkeypatch)
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"status": "ok"}),
    )
    monkeypatch.setattr(
        ta_mod, "ThetaDataAdapter", _adapter_factory(transport),
    )

    def boom(*a, **kw):
        raise AssertionError("SessionLocal must not be called")

    monkeypatch.setattr(cli, "SessionLocal", boom)
    rc = cli.main(["--check-provider"])
    assert rc == 0


def test_check_provider_returns_2_on_safety_failure(monkeypatch, capsys):
    from apps.api.src.options.paper.eval_runner import (
        EvalRunnerSafetyError,
    )

    def fail(*a, **kw):
        raise EvalRunnerSafetyError("OPTIONS_ENABLED must be True")

    monkeypatch.setattr(cli, "assert_safety_invariants", fail)
    rc = cli.main(["--check-provider"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "[safety]" in err


def test_check_provider_returns_2_on_missing_base_url(monkeypatch, capsys):
    _patch_safety(monkeypatch)
    _patch_real_settings(
        monkeypatch,
        THETADATA_BASE_URL=None,
        THETADATA_API_KEY=None,
        THETADATA_USERNAME=None,
        THETADATA_PASSWORD=None,
    )
    rc = cli.main(["--check-provider"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "THETADATA_BASE_URL" in err
