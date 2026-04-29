"""Phase 11T.4 - shadow_report unit tests."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pytest

from apps.api.src.ml import shadow_report as sr_mod
from apps.api.src.ml.shadow_report import (
    NEUTRAL_PLEDGE,
    REPORT_VERSION,
    ShadowReportError,
    build_report,
    report_path,
    write_report,
)
from apps.api.src.ml.shadow_scorer import (
    BUCKET_EDGES_FROZEN,
    ScorerConfig,
    ScoredRow,
    ScoringSummary,
    SHADOW_HIGH,
    SHADOW_LOW,
    SHADOW_MID,
)


def _cfg(*, commit=False, **kw):
    base = dict(
        model_id="m1",
        start=dt.date(2026, 1, 1), end=dt.date(2026, 4, 1),
        sources=("research_fast_fill",),
        domain="equity",
        include_provisional=False,
        bucket_edges=BUCKET_EDGES_FROZEN,
        output_dir="reports",
        dry_run=not commit, commit=commit,
    )
    base.update(kw)
    return ScorerConfig(**base)


def _row(*, bucket=SHADOW_HIGH, det="positive", realized="positive",
         qual=True, prov=False, score=0.7):
    return ScoredRow(
        observation_id="o1", as_of_date="2026-02-01",
        symbol="SPY", source="research_fast_fill",
        deterministic_rule_id="research_fast_fill_open_buy_v1",
        deterministic_outcome=det,
        deterministic_qualified=qual,
        deterministic_failed_gates_count=0 if qual else 4,
        model_score=score, model_bucket=bucket,
        realized_label=realized,
        is_provisional=prov,
        comparison_category="agreement_high",
    )


def _summary(rows, *, commit=False, output_dir="reports"):
    return ScoringSummary(
        config=_cfg(commit=commit, output_dir=output_dir),
        model_artifact_checksum_sha256="abcd",
        model_status="shadow_only",
        rows_input=len(rows), rows_scored=len(rows),
        rows_with_realized_label=sum(
            1 for r in rows
            if r.realized_label is not None
        ),
        rows_excluded_by_reason={},
        rows=tuple(rows),
    )


# ---------------------------------------------------------------------------
# Frozen constants
# ---------------------------------------------------------------------------

def test_report_version_frozen():
    assert REPORT_VERSION == "shadow-report-v1.0.0"


def test_neutral_pledge_string_present():
    assert "offline analysis only" in NEUTRAL_PLEDGE
    assert "not advice" in NEUTRAL_PLEDGE
    assert "neither is preferred" in NEUTRAL_PLEDGE


# ---------------------------------------------------------------------------
# build_report
# ---------------------------------------------------------------------------

def test_report_top_level_keys_match_spec():
    body = build_report(_summary([_row()]),
                        sources_included=("research_fast_fill",),
                        domain="equity")
    expected = {
        "report_version", "generated_at", "model_id",
        "model_artifact_checksum_sha256", "model_status",
        "scoring_window", "domain", "sources_included",
        "coverage", "model_metrics", "rule_comparison",
        "rows", "frozen_constants",
        "neutral_language_pledge", "warnings",
    }
    assert expected.issubset(body.keys())


def test_report_records_model_status():
    body = build_report(_summary([_row()]),
                        sources_included=("research_fast_fill",),
                        domain="equity")
    assert body["model_status"] == "shadow_only"


def test_report_records_model_artifact_checksum():
    body = build_report(_summary([_row()]),
                        sources_included=("research_fast_fill",),
                        domain="equity")
    assert body["model_artifact_checksum_sha256"] == "abcd"


def test_report_includes_frozen_constants_block():
    body = build_report(_summary([_row()]),
                        sources_included=("research_fast_fill",),
                        domain="equity")
    fc = body["frozen_constants"]
    assert fc["bucket_edges"] == [0.33, 0.66]
    assert fc["report_version"] == "shadow-report-v1.0.0"


def test_report_includes_neutral_language_pledge():
    body = build_report(_summary([_row()]),
                        sources_included=("research_fast_fill",),
                        domain="equity")
    assert body["neutral_language_pledge"] == NEUTRAL_PLEDGE


def test_report_calibration_bins_present_in_metrics_block():
    body = build_report(_summary([_row()]),
                        sources_included=("research_fast_fill",),
                        domain="equity")
    assert "lift_by_bucket" in body["model_metrics"]


def test_report_lift_by_bucket_present():
    rows = [
        _row(bucket=SHADOW_LOW,  realized="negative"),
        _row(bucket=SHADOW_LOW,  realized="negative"),
        _row(bucket=SHADOW_MID,  realized="neutral"),
        _row(bucket=SHADOW_HIGH, realized="positive"),
        _row(bucket=SHADOW_HIGH, realized="positive"),
    ]
    body = build_report(_summary(rows),
                        sources_included=("research_fast_fill",),
                        domain="equity")
    lb = body["model_metrics"]["lift_by_bucket"]
    assert lb["SHADOW_LOW"]["actual_positive_rate"] == 0.0
    assert lb["SHADOW_HIGH"]["actual_positive_rate"] == 1.0


def test_report_rows_have_observation_id():
    body = build_report(_summary([_row()]),
                        sources_included=("research_fast_fill",),
                        domain="equity")
    assert all("observation_id" in r for r in body["rows"])


def test_report_omits_recommendation_words():
    body = build_report(
        _summary([_row(), _row(bucket=SHADOW_LOW, det="negative",
                                realized="negative")]),
        sources_included=("research_fast_fill",),
        domain="equity",
    )
    flat = json.dumps(body).lower()
    for tok in (
        "recommend", "best trade", "top pick", "trade now",
        "place order", "auto-trade", "promote",
    ):
        assert tok not in flat, f"forbidden token {tok!r}"


def test_report_omits_signal_word():
    body = build_report(_summary([_row()]),
                        sources_included=("research_fast_fill",),
                        domain="equity")
    # "signal" must not appear as a noun in any user-facing string.
    flat = json.dumps(body).lower()
    assert " signal" not in flat
    assert "signal " not in flat


def test_report_round_trips_via_json_load():
    body = build_report(_summary([_row()]),
                        sources_included=("research_fast_fill",),
                        domain="equity")
    s = json.dumps(body, default=str)
    again = json.loads(s)
    assert again["model_id"] == body["model_id"]


# ---------------------------------------------------------------------------
# write_report
# ---------------------------------------------------------------------------

def test_report_filename_format(tmp_path):
    summary = _summary([_row()], commit=True, output_dir=str(tmp_path))
    p = report_path(summary, output_dir=tmp_path)
    assert p.name == (
        "shadow_score_m1_2026-01-01_2026-04-01.json"
    )


def test_report_writes_under_output_dir(tmp_path):
    summary = _summary([_row()], commit=True, output_dir=str(tmp_path))
    p = write_report(summary,
                     sources_included=("research_fast_fill",),
                     domain="equity",
                     output_dir=tmp_path)
    assert p.parent == tmp_path
    assert p.exists()


def test_report_refuses_to_overwrite_existing_file(tmp_path):
    summary = _summary([_row()], commit=True, output_dir=str(tmp_path))
    p = write_report(summary,
                     sources_included=("research_fast_fill",),
                     domain="equity",
                     output_dir=tmp_path)
    with pytest.raises(ShadowReportError, match="already exists"):
        write_report(summary,
                     sources_included=("research_fast_fill",),
                     domain="equity",
                     output_dir=tmp_path)


def test_report_refuses_dry_run_summary(tmp_path):
    summary = _summary([_row()], commit=False, output_dir=str(tmp_path))
    with pytest.raises(ShadowReportError, match="commit-mode"):
        write_report(summary,
                     sources_included=("research_fast_fill",),
                     domain="equity",
                     output_dir=tmp_path)


def test_report_module_no_db_writes():
    src = Path(sr_mod.__file__).read_text(encoding="utf-8")
    for tok in (
        "INSERT INTO", "UPDATE ", "DELETE FROM",
        "session.commit",
    ):
        assert tok not in src, f"forbidden token {tok!r}"
