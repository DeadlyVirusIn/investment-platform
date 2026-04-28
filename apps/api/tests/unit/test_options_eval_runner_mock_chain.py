"""Phase 11O.1 - Mock-chain CLI flag unit tests.

Schema validation + safety guards. Does not require Postgres — the
seed function is monkeypatched to a no-op so we can exercise the CLI
branches in isolation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_options_paper_eval as cli


def _patch_safety(monkeypatch):
    monkeypatch.setattr(
        cli, "assert_safety_invariants", lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        cli, "assert_no_scheduler_drift", lambda: None,
    )


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def test_mock_chain_loads_valid_json(tmp_path):
    payload = {
        "snapshot_at_utc": "2026-04-27T14:00:00Z",
        "rows": [
            {
                "underlying": "SPY", "expiry": "2026-05-27",
                "strike": 440, "option_type": "PUT",
                "option_symbol": "SPY260527P00440000",
                "bid": 1.20, "ask": 1.25,
            },
        ],
    }
    parsed = cli._validate_mock_payload(payload)
    assert parsed["snapshot_at_utc"].tzinfo is not None
    assert len(parsed["rows"]) == 1


def test_mock_chain_rejects_missing_snapshot_key():
    with pytest.raises(ValueError, match="snapshot_at_utc"):
        cli._validate_mock_payload({"rows": []})


def test_mock_chain_rejects_missing_rows_key():
    with pytest.raises(ValueError, match="rows"):
        cli._validate_mock_payload({"snapshot_at_utc": "2026-04-27T00:00Z"})


def test_mock_chain_rejects_non_dict_top_level():
    with pytest.raises(ValueError, match="object"):
        cli._validate_mock_payload([])


def test_mock_chain_rejects_missing_required_fields():
    bad = {
        "snapshot_at_utc": "2026-04-27T00:00:00Z",
        "rows": [{"underlying": "SPY"}],
    }
    with pytest.raises(ValueError, match="missing required fields"):
        cli._validate_mock_payload(bad)


def test_mock_chain_rejects_bad_option_type():
    bad = {
        "snapshot_at_utc": "2026-04-27T00:00:00Z",
        "rows": [{
            "underlying": "SPY", "expiry": "2026-05-27",
            "strike": 1, "option_type": "XX",
            "option_symbol": "X", "bid": 1, "ask": 2,
        }],
    }
    with pytest.raises(ValueError, match="option_type"):
        cli._validate_mock_payload(bad)


def test_mock_chain_rejects_bad_expiry_format():
    bad = {
        "snapshot_at_utc": "2026-04-27T00:00:00Z",
        "rows": [{
            "underlying": "SPY", "expiry": "not-a-date",
            "strike": 1, "option_type": "PUT",
            "option_symbol": "X", "bid": 1, "ask": 2,
        }],
    }
    with pytest.raises(ValueError, match="expiry"):
        cli._validate_mock_payload(bad)


# ---------------------------------------------------------------------------
# CLI safety guards
# ---------------------------------------------------------------------------

def test_mock_chain_with_commit_without_allow_mock_commit_exits_2(
    tmp_path, monkeypatch, capsys,
):
    _patch_safety(monkeypatch)
    p = tmp_path / "mock.json"
    p.write_text(json.dumps({
        "snapshot_at_utc": "2026-04-27T00:00:00Z",
        "rows": [],
    }))
    rc = cli.main([
        "--mock-chain-from", str(p),
        "--commit", "--confirm-commit", "YES",
    ])
    err = capsys.readouterr().err
    assert rc == 2
    assert "--allow-mock-commit" in err


def test_mock_chain_with_commit_and_allow_mock_commit_proceeds(
    tmp_path, monkeypatch, capsys,
):
    """With --allow-mock-commit the CLI moves past the safety guard
    and reaches the runner. We monkeypatch _seed_mock_chain + the
    runner so the test does not need a database."""
    _patch_safety(monkeypatch)
    monkeypatch.setattr(cli, "_seed_mock_chain", lambda payload: 0)

    from apps.api.src.options.paper.eval_runner_models import (
        RunnerSummary,
    )

    captured: dict = {}

    def fake_run(config, **kw):
        captured["config"] = config
        return RunnerSummary(
            config=config, n_chain_inserted=0, n_observations_total=0,
            n_qualified=0, n_planned=0, n_planned_rejected=0,
            n_existing_open_trade_dedup=0, n_committed=0,
            planned_trades=(), committed_trade_ids=(),
        )

    monkeypatch.setattr(cli, "run", fake_run)

    p = tmp_path / "mock.json"
    p.write_text(json.dumps({
        "snapshot_at_utc": "2026-04-27T00:00:00Z",
        "rows": [],
    }))
    rc = cli.main([
        "--mock-chain-from", str(p),
        "--commit", "--confirm-commit", "YES",
        "--allow-mock-commit",
    ])
    # rc=4 because the fake run returns 0 qualified observations
    assert rc == 4
    # Critical: the runner ran with skip_ingest forced True
    assert captured["config"].skip_ingest is True
    assert captured["config"].commit is True


def test_mock_chain_dry_run_does_not_require_allow_flag(
    tmp_path, monkeypatch, capsys,
):
    _patch_safety(monkeypatch)
    monkeypatch.setattr(cli, "_seed_mock_chain", lambda payload: 0)

    from apps.api.src.options.paper.eval_runner_models import (
        RunnerSummary,
    )

    def fake_run(config, **kw):
        return RunnerSummary(
            config=config, n_chain_inserted=0, n_observations_total=0,
            n_qualified=0, n_planned=0, n_planned_rejected=0,
            n_existing_open_trade_dedup=0, n_committed=0,
            planned_trades=(), committed_trade_ids=(),
        )

    monkeypatch.setattr(cli, "run", fake_run)

    p = tmp_path / "mock.json"
    p.write_text(json.dumps({
        "snapshot_at_utc": "2026-04-27T00:00:00Z",
        "rows": [],
    }))
    rc = cli.main([
        "--mock-chain-from", str(p),
        "--dry-run",
    ])
    assert rc == 4   # no qualified, but the guard didn't block


def test_mock_chain_missing_file_exits_2(monkeypatch, capsys, tmp_path):
    _patch_safety(monkeypatch)
    rc = cli.main([
        "--mock-chain-from", str(tmp_path / "missing.json"),
    ])
    err = capsys.readouterr().err
    assert rc == 2
    assert "file not found" in err


def test_mock_chain_invalid_json_exits_2(tmp_path, monkeypatch, capsys):
    _patch_safety(monkeypatch)
    p = tmp_path / "broken.json"
    p.write_text("{not json")
    rc = cli.main(["--mock-chain-from", str(p)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "[mock] invalid schema" in err


def test_mock_provider_constants():
    """Mock-tagged rows must clearly identify themselves in the audit
    trail and not collide with real provider names."""
    assert cli.MOCK_PROVIDER_NAME == "mock_local"
    assert "mock" in cli.MOCK_PROVIDER_VERSION.lower()
    assert cli.MOCK_PROVIDER_NAME != "thetadata"


def test_mock_fixture_file_is_valid():
    """The committed sample fixture must round-trip through validator."""
    p = Path("data/test/mock_spy_chain.json")
    assert p.exists()
    payload = json.loads(p.read_text(encoding="utf-8"))
    parsed = cli._validate_mock_payload(payload)
    assert len(parsed["rows"]) >= 4
