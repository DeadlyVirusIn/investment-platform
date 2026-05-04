"""Phase 11Z — operator-only options chain ingestion contract tests.

Pins:
  * Default mode is dry-run (no DB writes).
  * --commit refuses without OPTIONS_CHAIN_INGEST_CONFIRM env.
  * --source provider is reserved (refused with exit 2).
  * CSV with bid > ask, missing required columns, non-numeric strike,
    or expiry before as-of is rejected with exit 1.
  * Script source contains no INSERT/UPDATE/DELETE against
    options_paper_trade, options_paper_trade_leg,
    options_shadow_decision_log, paper_trade, or paper_trade_log.
  * Idempotency: ON CONFLICT DO NOTHING against the natural-key
    constraint is the only conflict handler.
  * Confirmation phrase pinned.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path("scripts/ingest_options_chain.py")
FIXTURE = Path("apps/api/tests/fixtures/options_chain_sample.csv")


def _run(args: list[str], env: dict[str, str] | None = None) -> tuple[
    int, str, str
]:
    """Run the script with -m so package imports resolve."""
    env_full = {**os.environ, **(env or {})}
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.ingest_options_chain", *args],
        capture_output=True, text=True, env=env_full,
        cwd=Path.cwd(),
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_script_exists():
    assert SCRIPT.exists(), f"missing {SCRIPT}"


def test_fixture_exists():
    assert FIXTURE.exists(), f"missing fixture {FIXTURE}"


def test_module_imports_without_db():
    """Importing the module must not connect to the DB."""
    import scripts.ingest_options_chain as mod  # noqa: F401
    assert hasattr(mod, "main")
    assert hasattr(mod, "load_csv")


def test_dry_run_writes_zero_rows():
    """Default invocation: --source csv, no --commit. Writes nothing."""
    rc, out, err = _run([
        "--symbol", "SPY", "--as-of", "2026-05-03",
        "--source", "csv", "--csv", str(FIXTURE),
    ])
    assert rc == 0, f"dry-run failed: rc={rc} err={err}"
    assert "[dry-run]" in out
    assert "rows=10" in out
    # Sanity: no commit-mode keyword in dry-run output.
    assert "[commit]" not in out


def test_commit_refused_without_env_confirmation():
    rc, out, err = _run([
        "--symbol", "SPY", "--as-of", "2026-05-03",
        "--source", "csv", "--csv", str(FIXTURE),
        "--commit",
    ], env={"OPTIONS_CHAIN_INGEST_CONFIRM": ""})
    assert rc == 2, f"commit must refuse without env: rc={rc}"
    assert "REFUSED" in err
    assert "OPTIONS_CHAIN_INGEST_CONFIRM" in err


def test_commit_refused_with_wrong_phrase():
    rc, out, err = _run([
        "--symbol", "SPY", "--as-of", "2026-05-03",
        "--source", "csv", "--csv", str(FIXTURE),
        "--commit",
    ], env={"OPTIONS_CHAIN_INGEST_CONFIRM": "yes"})
    assert rc == 2, "wrong phrase must still refuse"


def test_provider_source_refused_in_v1():
    rc, out, err = _run([
        "--symbol", "SPY", "--as-of", "2026-05-03",
        "--source", "provider",
    ])
    assert rc == 2
    assert "REFUSED" in err
    assert "provider" in err.lower()


def test_unknown_source_rejected_by_argparse():
    rc, out, err = _run([
        "--symbol", "SPY", "--as-of", "2026-05-03",
        "--source", "live",
    ])
    assert rc != 0


def test_validation_rejects_bid_gt_ask(tmp_path: Path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text(
        "expiry,strike,option_type,option_symbol,bid,ask,mid,last,"
        "volume,open_interest,delta,gamma,theta,vega,iv,quote_age_seconds\n"
        "2026-05-30,500,PUT,SPYP500,5.00,1.00,3.00,2.00,100,500,"
        "-0.2,0.01,-0.05,0.5,0.2,12\n"
    )
    rc, out, err = _run([
        "--symbol", "SPY", "--as-of", "2026-05-03",
        "--source", "csv", "--csv", str(bad_csv),
    ])
    assert rc == 1, f"bid>ask must fail: rc={rc}"
    assert "VALIDATION ERROR" in err
    assert "bid > ask" in err


def test_validation_rejects_missing_required_column(tmp_path: Path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("expiry,strike\n2026-05-30,500\n")
    rc, out, err = _run([
        "--symbol", "SPY", "--as-of", "2026-05-03",
        "--source", "csv", "--csv", str(bad_csv),
    ])
    assert rc == 1
    assert "missing required columns" in err


def test_validation_rejects_expiry_before_as_of(tmp_path: Path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text(
        "expiry,strike,option_type,option_symbol,bid,ask,mid,last,"
        "volume,open_interest,delta,gamma,theta,vega,iv,quote_age_seconds\n"
        # expiry == as-of → should fail (must be strictly after)
        "2026-05-03,500,PUT,SPYP500,1.0,1.1,1.05,1.05,100,500,"
        "-0.2,0.01,-0.05,0.5,0.2,12\n"
    )
    rc, out, err = _run([
        "--symbol", "SPY", "--as-of", "2026-05-03",
        "--source", "csv", "--csv", str(bad_csv),
    ])
    assert rc == 1, f"expired contract must fail: rc={rc}"
    assert "VALIDATION ERROR" in err
    assert "expiry" in err.lower()


def test_validation_rejects_negative_oi(tmp_path: Path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text(
        "expiry,strike,option_type,option_symbol,bid,ask,mid,last,"
        "volume,open_interest,delta,gamma,theta,vega,iv,quote_age_seconds\n"
        "2026-05-30,500,PUT,SPYP500,1.0,1.1,1.05,1.05,100,-3,"
        "-0.2,0.01,-0.05,0.5,0.2,12\n"
    )
    rc, _, err = _run([
        "--symbol", "SPY", "--as-of", "2026-05-03",
        "--source", "csv", "--csv", str(bad_csv),
    ])
    assert rc == 1
    assert "open_interest" in err


def test_missing_csv_path_refused():
    rc, out, err = _run([
        "--symbol", "SPY", "--as-of", "2026-05-03",
        "--source", "csv",
    ])
    assert rc == 2
    assert "--csv" in err


def test_source_has_no_writes_to_forbidden_tables():
    """Static guard: script source must not contain SQL writes against
    any non-options_chain_snapshot table.

    Looks for `INSERT INTO X`, `UPDATE X SET`, `DELETE FROM X` against
    the forbidden table set. Mention of the names in docstrings is
    fine (they explain what we DON'T write to)."""
    src = SCRIPT.read_text(encoding="utf-8")
    forbidden = (
        "options_paper_trade",
        "options_paper_trade_leg",
        "options_shadow_decision_log",
        "paper_trade_log",
        "paper_trade",  # account path
    )
    for tbl in forbidden:
        for pat in (
            rf"\bINSERT\s+INTO\s+{tbl}\b",
            rf"\bUPDATE\s+{tbl}\b",
            rf"\bDELETE\s+FROM\s+{tbl}\b",
        ):
            assert not re.search(pat, src, flags=re.IGNORECASE), (
                f"SQL write against forbidden table {tbl!r}: pattern {pat}"
            )


def test_idempotency_uses_on_conflict_do_nothing():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "ON CONFLICT" in src
    assert "ux_options_chain_snapshot_natural_key" in src
    assert "DO NOTHING" in src


def test_target_table_pinned_to_options_chain_snapshot():
    src = SCRIPT.read_text(encoding="utf-8")
    # Any INSERT INTO must target options_chain_snapshot.
    inserts = re.findall(r"INSERT\s+INTO\s+(\w+)", src, flags=re.IGNORECASE)
    assert inserts, "expected at least one INSERT statement"
    for t in inserts:
        assert t == "options_chain_snapshot", (
            f"unexpected INSERT target: {t}"
        )


def test_confirmation_phrase_pinned():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "OPTIONS_CHAIN_INGEST_CONFIRM" in src
    assert "I_UNDERSTAND_THIS_WRITES_OPTIONS_CHAIN_DATA" in src


def test_no_post_or_scheduler_in_script():
    src = SCRIPT.read_text(encoding="utf-8")
    forbidden = (
        "@router.post", "scheduler.add_job", "BackgroundTasks",
        "ML_CAN_AFFECT_TRADES",
    )
    for f in forbidden:
        assert f not in src, f"forbidden token in ingest script: {f}"
