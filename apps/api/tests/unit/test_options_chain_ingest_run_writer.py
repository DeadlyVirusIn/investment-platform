"""Unit tests — Opt-Obs-Fix1 ingest-run telemetry aggregation.

Covers build_ingest_run_record's pure aggregation + classification
taxonomy. No DB, no clock, no provider — fully deterministic.
"""

from __future__ import annotations

import datetime as dt

from apps.api.src.options.data.chain_ingest import (
    IngestSummary,
    build_ingest_run_record,
)

_T0 = dt.datetime(2026, 6, 1, 14, 15, 0, tzinfo=dt.timezone.utc)
_T1 = dt.datetime(2026, 6, 1, 14, 16, 32, tzinfo=dt.timezone.utc)
_UNIVERSE = ("SPY", "QQQ", "IWM", "GLD", "TLT")


def _ok(sym: str, *, inserted: int, provider_quotes: int,
        filtered: int, dedup: int = 0,
        rejects: dict | None = None,
        status: str = "ok") -> IngestSummary:
    return IngestSummary(
        underlying=sym,
        snapshot_at_utc=_T0,
        status=status,
        n_provider_quotes=provider_quotes,
        n_filtered=filtered,
        n_inserted=inserted,
        n_skipped_existing=dedup,
        reject_counts=rejects or {},
        provider="tradier",
        provider_version="tradier-prod",
    )


def test_happy_path_classifies_success_and_sums_fields():
    summaries = [
        _ok("SPY", inserted=3708, provider_quotes=5000, filtered=3708,
            rejects={"spread": 800, "open_interest": 492}),
        _ok("QQQ", inserted=2786, provider_quotes=3500, filtered=2786,
            rejects={"spread": 400}),
        _ok("IWM", inserted=1433, provider_quotes=1800, filtered=1433),
        _ok("GLD", inserted=714, provider_quotes=900, filtered=714),
        _ok("TLT", inserted=646, provider_quotes=800, filtered=646),
    ]
    rec = build_ingest_run_record(
        summaries, started_at=_T0, finished_at=_T1,
        universe=_UNIVERSE, provider_default="tradier",
    )

    assert rec["classification"] == "success"
    assert rec["rows_inserted"] == 3708 + 2786 + 1433 + 714 + 646
    assert rec["rows_filtered_out"] == (
        (5000 - 3708) + (3500 - 2786) + (1800 - 1433)
        + (900 - 714) + (800 - 646)
    )
    assert rec["n_symbols_ok"] == 5
    assert rec["n_symbols_partial"] == 0
    assert rec["n_symbols_error"] == 0
    assert rec["provider"] == "tradier"
    assert rec["universe"] == list(_UNIVERSE)
    assert rec["duration_sec"] == 92.0
    # reject summary aggregated across symbols
    assert rec["error_summary"]["reject_counts"]["spread"] == 1200
    assert rec["error_summary"]["provider_version"] == "tradier-prod"


def test_all_deduped_classifies_no_new_data():
    # Provider returned quotes but every row already existed (idempotent
    # re-run) → 0 inserted → 'no_new_data', NOT 'error'.
    summaries = [
        _ok("SPY", inserted=0, provider_quotes=5000, filtered=3708,
            dedup=3708),
        _ok("QQQ", inserted=0, provider_quotes=3500, filtered=2786,
            dedup=2786),
    ]
    rec = build_ingest_run_record(
        summaries, started_at=_T0, finished_at=_T1,
        universe=("SPY", "QQQ"), provider_default="tradier",
    )
    assert rec["classification"] == "no_new_data"
    assert rec["rows_inserted"] == 0
    assert rec["rows_dedup"] == 3708 + 2786


def test_partial_symbol_with_inserts_classifies_partial():
    summaries = [
        _ok("SPY", inserted=100, provider_quotes=200, filtered=100),
        _ok("QQQ", inserted=50, provider_quotes=120, filtered=50,
            status="partial"),
    ]
    rec = build_ingest_run_record(
        summaries, started_at=_T0, finished_at=_T1,
        universe=("SPY", "QQQ"), provider_default="tradier",
    )
    assert rec["classification"] == "partial"
    assert rec["n_symbols_partial"] == 1


def test_provider_down_no_quotes_classifies_error():
    summaries = [
        IngestSummary(underlying="SPY", snapshot_at_utc=_T0,
                      status="skipped_unavailable", note="provider 503"),
        IngestSummary(underlying="QQQ", snapshot_at_utc=_T0,
                      status="error", note="timeout"),
    ]
    rec = build_ingest_run_record(
        summaries, started_at=_T0, finished_at=_T1,
        universe=("SPY", "QQQ"), provider_default="tradier",
    )
    assert rec["classification"] == "error"
    assert rec["rows_inserted"] == 0
    assert rec["n_symbols_error"] == 2
    assert rec["error_summary"]["notes"]["QQQ"] == "timeout"
    # provider falls back to default when no summary carried one
    assert rec["provider"] == "tradier"
