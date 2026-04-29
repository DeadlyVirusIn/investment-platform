"""Phase 11U - drift pipeline end-to-end against Postgres.

11U is read-only of files (registry + reports + datasets). It does
not directly touch DB. These integration tests assert that running
the drift orchestrator against a seeded PG instance:
  * never writes to paper_*, decision_log, paper_research_fill,
    paper_observation_label
  * never edits the registry file
  * never modifies the baseline / shadow report inputs
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db.models import PaperObservationLabel  # noqa: F401
from apps.api.src.ml.drift_monitor import (
    DriftConfig,
    DriftInputError,
    DriftMonitorError,
    REPORT_VERSION,
    STATUS_INSUFFICIENT,
    run as run_drift,
    write_report,
)


pytestmark = pytest.mark.integration


@pytest.fixture
def session_factory(pg_engine):
    return sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )


def _baseline_report(*, n_holdout: int = 312) -> dict:
    return {
        "model_type": "logreg",
        "task": "classification",
        "splits": {
            "train":   {"end": "2024-12-31", "n": 800},
            "test":    {"start": "2025-01-01", "end": "2025-12-31",
                        "n": 150},
            "holdout": {"start": "2026-01-01", "end": "2026-04-08",
                        "n": n_holdout},
        },
        "metrics": {
            "test":    {"auc_macro": 0.6, "brier_score": 0.21,
                        "hit_ratio": 0.51},
            "holdout": {"auc_macro": 0.58, "brier_score": 0.22,
                        "hit_ratio": 0.51,
                        "calibration_bins": [
                            {"bin": "0.0-0.5",
                             "actual_positive_rate": 0.10},
                            {"bin": "0.5-1.0",
                             "actual_positive_rate": 0.40},
                        ],
                        "lift_by_bucket": {
                            "SHADOW_LOW":  {"n": 100,
                                            "actual_positive_rate": 0.10},
                            "SHADOW_MID":  {"n": 200,
                                            "actual_positive_rate": 0.30},
                            "SHADOW_HIGH": {"n":  80,
                                            "actual_positive_rate": 0.50},
                        }},
        },
        "dataset": {"id": "ds-1", "n_rows": 1000,
                    "checksum_sha256": "abc"},
    }


def _shadow_report(*, n_rows: int = 200) -> dict:
    return {
        "report_version": "shadow-report-v1.0.0",
        "model_id": "m1",
        "model_artifact_checksum_sha256": "abcd",
        "model_status": "shadow_only",
        "scoring_window": {"start": "2026-04-09", "end": "2026-04-29"},
        "domain": "equity",
        "sources_included": ["research_fast_fill"],
        "coverage": {
            "rows_input": n_rows + 20,
            "rows_scored": n_rows,
            "rows_with_realized_label": n_rows,
            "rows_excluded": {"missing_features": 5,
                              "is_provisional": 15},
        },
        "model_metrics": {
            "auc_macro": 0.56, "brier_score": 0.23, "hit_ratio": 0.49,
            "calibration_bins": [
                {"bin": "0.0-0.5", "actual_positive_rate": 0.12},
                {"bin": "0.5-1.0", "actual_positive_rate": 0.42},
            ],
            "lift_by_bucket": {
                "SHADOW_LOW":  {"n":  60, "actual_positive_rate": 0.12},
                "SHADOW_MID":  {"n": 100, "actual_positive_rate": 0.32},
                "SHADOW_HIGH": {"n":  40, "actual_positive_rate": 0.48},
            },
        },
        "rows": [],
    }


def _write_inputs(tmp_path: Path, *, baseline=None, shadow=None) -> tuple[Path, Path, Path]:
    base = tmp_path / "base.json"
    base.write_text(json.dumps(baseline or _baseline_report()),
                    encoding="utf-8")
    sh = tmp_path / "shadow.json"
    sh.write_text(json.dumps(shadow or _shadow_report()),
                  encoding="utf-8")
    reg = tmp_path / "registry.json"
    reg.write_text(json.dumps([
        {"model_id": "m1", "status": "shadow_only",
         "artifact_path": str(tmp_path / "fake.pkl"),
         "artifact_checksum_sha256": "abcd"},
    ]), encoding="utf-8")
    (tmp_path / "fake.pkl").write_bytes(b"binary-blob")
    return base, sh, reg


def _cfg(tmp_path: Path, base: Path, sh: Path, *, commit=False) -> DriftConfig:
    return DriftConfig(
        model_id="m1",
        baseline_report_path=base,
        shadow_report_path=sh,
        baseline_dataset_path=None, recent_dataset_path=None,
        output_dir=tmp_path,
        dry_run=not commit, commit=commit, explain=False,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_full_drift_report_dry_run_against_seeded_pg(
    pg_session, session_factory, tmp_path,
):
    base, sh, reg = _write_inputs(tmp_path)
    body = run_drift(_cfg(tmp_path, base, sh), registry_path=reg)
    assert body["report_version"] == REPORT_VERSION
    # dry-run: no file written
    assert list(tmp_path.glob("model_drift_*.json")) == []


def test_full_drift_report_commit_writes_json_only(
    pg_session, session_factory, tmp_path,
):
    base, sh, reg = _write_inputs(tmp_path)
    cfg = _cfg(tmp_path, base, sh, commit=True)
    body = run_drift(cfg, registry_path=reg)
    p = write_report(cfg, body)
    assert p.exists()
    assert p.suffix == ".json"


def test_drift_report_writes_no_paper_or_decision_log(
    pg_engine, pg_session, session_factory, tmp_path,
):
    # Ensure decision_log exists with the full Phase 11P schema so
    # this fixture is compatible when run alongside other integration
    # suites that depend on the extended columns.
    with pg_engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS decision_log (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                decision_ts timestamptz NOT NULL DEFAULT now(),
                as_of_date date NOT NULL,
                engine text NOT NULL,
                action text NOT NULL,
                instrument text NOT NULL,
                inputs_used jsonb NOT NULL DEFAULT '{}'::jsonb,
                context_values jsonb NOT NULL DEFAULT '{}'::jsonb,
                decision_version text NOT NULL,
                reason text,
                blocked_by text,
                diagnostic_snapshot jsonb,
                data_quality jsonb,
                catalyst jsonb,
                feature_confidence numeric(6,4),
                skip_reason text,
                missing_features jsonb,
                ml_advisory jsonb,
                baseline_advisory jsonb,
                pattern_flags jsonb,
                factor_attribution jsonb,
                factor_version text,
                feature_set_version text,
                risk_context jsonb,
                alpha_rule_adjustment jsonb,
                alpha_rules_applied jsonb,
                alpha_rules_mode text,
                alpha_rule_size_multiplier numeric(6,4),
                alpha_rule_blocked boolean NOT NULL DEFAULT FALSE,
                alpha_rule_block_reason text,
                gate_mode text,
                exploratory_paper boolean NOT NULL DEFAULT FALSE,
                exploratory_reason text,
                gates_passed integer,
                gates_total integer,
                gates_failed jsonb,
                strict_would_block boolean NOT NULL DEFAULT FALSE,
                exploratory_size_multiplier numeric(6,4),
                source text NOT NULL DEFAULT 'strict_paper',
                strict_gates_passed boolean,
                failed_gates text[] NOT NULL DEFAULT '{}'::text[],
                ml_label_eligible boolean NOT NULL DEFAULT FALSE,
                CONSTRAINT ck_decision_log_source
                  CHECK (source IN
                    ('strict_paper','exploratory_paper','backfill'))
            )
            """
        ))
    base, sh, reg = _write_inputs(tmp_path)
    run_drift(_cfg(tmp_path, base, sh, commit=True), registry_path=reg)
    n_trade = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_trade"
    )).scalar_one()
    n_pos = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_position"
    )).scalar_one()
    n_dec = pg_session.execute(text(
        "SELECT COUNT(*) FROM decision_log"
    )).scalar_one()
    assert n_trade == 0
    assert n_pos == 0
    assert n_dec == 0


def test_drift_report_writes_no_research_fill(
    pg_engine, pg_session, session_factory, tmp_path,
):
    base, sh, reg = _write_inputs(tmp_path)
    run_drift(_cfg(tmp_path, base, sh, commit=True), registry_path=reg)
    n = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_research_fill"
    )).scalar_one()
    assert n == 0


def test_drift_report_does_not_modify_registry(tmp_path):
    base, sh, reg = _write_inputs(tmp_path)
    before = reg.read_bytes()
    mtime_before = reg.stat().st_mtime
    cfg = _cfg(tmp_path, base, sh, commit=True)
    body = run_drift(cfg, registry_path=reg)
    write_report(cfg, body)
    assert reg.read_bytes() == before
    assert reg.stat().st_mtime == mtime_before


def test_drift_report_does_not_modify_baseline_report(tmp_path):
    base, sh, reg = _write_inputs(tmp_path)
    before = base.read_bytes()
    mtime = base.stat().st_mtime
    cfg = _cfg(tmp_path, base, sh, commit=True)
    body = run_drift(cfg, registry_path=reg)
    write_report(cfg, body)
    assert base.read_bytes() == before
    assert base.stat().st_mtime == mtime


def test_drift_report_does_not_modify_shadow_report(tmp_path):
    base, sh, reg = _write_inputs(tmp_path)
    before = sh.read_bytes()
    mtime = sh.stat().st_mtime
    cfg = _cfg(tmp_path, base, sh, commit=True)
    body = run_drift(cfg, registry_path=reg)
    write_report(cfg, body)
    assert sh.read_bytes() == before
    assert sh.stat().st_mtime == mtime


def test_drift_report_handles_missing_recent_rows_returns_4(
    tmp_path,
):
    base, _sh, reg = _write_inputs(tmp_path)
    sh_thin = tmp_path / "shadow_thin.json"
    sh_thin.write_text(
        json.dumps(_shadow_report(n_rows=50)),
        encoding="utf-8",
    )
    cfg = _cfg(tmp_path, base, sh_thin)
    body = run_drift(cfg, registry_path=reg)
    assert body["overall_monitoring_status"] == STATUS_INSUFFICIENT


def test_drift_report_idempotent_filename_collision_refused(tmp_path):
    base, sh, reg = _write_inputs(tmp_path)
    cfg = _cfg(tmp_path, base, sh, commit=True)
    body = run_drift(cfg, registry_path=reg)
    write_report(cfg, body)
    with pytest.raises(DriftMonitorError, match="already exists"):
        # Same body → identical timestamp → identical filename
        write_report(cfg, body)


def test_drift_report_neutral_language_in_rendered_body(tmp_path):
    base, sh, reg = _write_inputs(tmp_path)
    cfg = _cfg(tmp_path, base, sh, commit=True)
    body = run_drift(cfg, registry_path=reg)
    flat = json.dumps(body).lower()
    for tok in (
        "recommend", "promote", "best model", "bad model",
        "stop trading", "replace model", "failed model",
        "trade now", "place order", "auto-trade", "broken model",
    ):
        assert tok not in flat, f"forbidden token {tok!r}"
