"""Phase Opt-B3a Phase B — chain-selection invariant tests.

Covers six invariants enforced by `shadow_evaluator._read_chains` +
`shadow_evaluator._select_run_batch`:

  1. RUN_BATCH_COHERENCE         — single snapshot_at_utc per run
  2. DETERMINISTIC_BATCH_SELECTION — picks newest eligible batch
  3. PROVIDER_WHITELIST          — fixtures filtered out
  4. PROVIDER_VERSION_HOMOGENEITY — pinned to picked batch's version
  5. RUN_FRESHNESS_BOUND         — batch must be ≤ MAX_RUN_CHAIN_AGE_HOURS old
  6. RUN_UNIVERSE_CLOSURE        — only OPTIONS_RUN_UNIVERSE underlyings

In-memory SQLite is unsuitable here because the SQL uses
`make_interval(hours=>...)` and `EXTRACT(EPOCH FROM ...)` Postgres
features. Tests use the live Postgres test schema spun up by the
integration harness if available, OR a stubbed session that captures
the executed SQL parameters and returns synthetic results.

We use the second path here for hermetic offline coverage.
"""

from __future__ import annotations

import datetime as dt
import types
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Stub Session that captures execute() calls + returns canned mappings
# ---------------------------------------------------------------------------

class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _StubSession:
    """Captures every execute call. Returns from a queue of canned
    results indexed by call order."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def execute(self, stmt, params=None):
        self.calls.append({"sql": str(stmt), "params": dict(params or {})})
        if not self._results:
            return _StubResult([])
        return _StubResult(self._results.pop(0))


# ---------------------------------------------------------------------------
# Settings stub helper
# ---------------------------------------------------------------------------

def _settings(provs=("tradier", "thetadata"), max_age_h=24,
              universe=("SPY", "QQQ", "IWM", "GLD", "TLT")):
    return types.SimpleNamespace(
        OPTIONS_PRODUCTION_PROVIDERS=provs,
        MAX_RUN_CHAIN_AGE_HOURS=max_age_h,
        OPTIONS_RUN_UNIVERSE=universe,
    )


# ---------------------------------------------------------------------------
# 1. RUN_BATCH_COHERENCE — read query references a single snapshot_at_utc
# ---------------------------------------------------------------------------

def test_read_chains_query_pins_single_snapshot_at_utc():
    from apps.api.src.options.shadow_evaluator import _read_chains
    fake_batch = {
        "snapshot_at_utc": dt.datetime(2026, 5, 13, 17, 47, tzinfo=dt.timezone.utc),
        "provider": "tradier", "provider_version": "tradier-sandbox",
        "age_seconds": 3600, "n_rows": 6561,
    }
    sess = _StubSession([
        [fake_batch],   # _select_run_batch result
        [],             # _read_chains main query result
    ])
    with patch("apps.api.src.options.shadow_evaluator.settings",
               _settings()):
        _read_chains(sess, run_date=dt.date(2026, 5, 13))

    main_call = sess.calls[1]
    assert "snapshot_at_utc = :ts" in main_call["sql"]
    assert main_call["params"]["ts"] == fake_batch["snapshot_at_utc"]
    # No DISTINCT ON, no per-symbol latest selection
    assert "DISTINCT ON" not in main_call["sql"]


# ---------------------------------------------------------------------------
# 2. DETERMINISTIC_BATCH_SELECTION — _select_run_batch sorts DESC + LIMIT 1
# ---------------------------------------------------------------------------

def test_select_run_batch_sql_picks_newest_one():
    from apps.api.src.options.shadow_evaluator import _select_run_batch
    sess = _StubSession([[{
        "snapshot_at_utc": dt.datetime(2026, 5, 13, tzinfo=dt.timezone.utc),
        "provider": "tradier", "provider_version": "tradier-sandbox",
        "age_seconds": 3600, "n_rows": 6561,
    }]])
    out = _select_run_batch(
        sess, run_date=dt.date(2026, 5, 13),
        production_providers=("tradier",), max_age_hours=24)
    sql = sess.calls[0]["sql"]
    assert "ORDER BY snapshot_at_utc DESC" in sql
    assert "LIMIT 1" in sql
    assert out["age_hours"] == 1.0


# ---------------------------------------------------------------------------
# 3. PROVIDER_WHITELIST — fixtures filtered by SQL params
# ---------------------------------------------------------------------------

def test_select_run_batch_passes_only_production_providers():
    from apps.api.src.options.shadow_evaluator import _select_run_batch
    sess = _StubSession([[]])
    _select_run_batch(
        sess, run_date=dt.date(2026, 5, 13),
        production_providers=("tradier", "thetadata"), max_age_hours=24)
    params = sess.calls[0]["params"]
    assert params["provs"] == ["tradier", "thetadata"]
    assert "csv-fixture" not in params["provs"]
    assert "yahoo" not in params["provs"]
    assert "provider = ANY(:provs)" in sess.calls[0]["sql"]


def test_read_chains_returns_empty_when_no_eligible_batch():
    from apps.api.src.options.shadow_evaluator import _read_chains
    # _select_run_batch returns None (empty result list)
    sess = _StubSession([[]])
    with patch("apps.api.src.options.shadow_evaluator.settings", _settings()):
        rows = _read_chains(sess, run_date=dt.date(2026, 5, 13))
    assert rows == []
    # The main read query was NOT executed (only the batch picker)
    assert len(sess.calls) == 1


# ---------------------------------------------------------------------------
# 4. PROVIDER_VERSION_HOMOGENEITY — pinned to picked batch's version
# ---------------------------------------------------------------------------

def test_read_chains_pins_provider_version_from_batch():
    from apps.api.src.options.shadow_evaluator import _read_chains
    fake_batch = {
        "snapshot_at_utc": dt.datetime(2026, 5, 13, tzinfo=dt.timezone.utc),
        "provider": "tradier", "provider_version": "tradier-sandbox",
        "age_seconds": 600, "n_rows": 6561,
    }
    sess = _StubSession([[fake_batch], []])
    with patch("apps.api.src.options.shadow_evaluator.settings", _settings()):
        _read_chains(sess, run_date=dt.date(2026, 5, 13))
    main_call = sess.calls[1]
    assert main_call["params"]["pver"] == "tradier-sandbox"
    assert "provider_version IS NOT DISTINCT FROM :pver" in main_call["sql"]
    assert main_call["params"]["prov"] == "tradier"


# ---------------------------------------------------------------------------
# 5. RUN_FRESHNESS_BOUND — SQL uses make_interval, NOT frozen quote_age_seconds
# ---------------------------------------------------------------------------

def test_select_run_batch_uses_live_age_via_make_interval():
    from apps.api.src.options.shadow_evaluator import _select_run_batch
    sess = _StubSession([[]])
    _select_run_batch(
        sess, run_date=dt.date(2026, 5, 13),
        production_providers=("tradier",), max_age_hours=12)
    sql = sess.calls[0]["sql"]
    # Live freshness check (NOT relying on stored quote_age_seconds)
    assert "(NOW() - snapshot_at_utc)" in sql
    assert "make_interval(hours => :hrs)" in sql
    assert sess.calls[0]["params"]["hrs"] == 12
    # Confirm the query does NOT reference the frozen field
    assert "quote_age_seconds" not in sql.split("WHERE")[1].split("GROUP")[0]


# ---------------------------------------------------------------------------
# 6. RUN_UNIVERSE_CLOSURE — underlying must be in OPTIONS_RUN_UNIVERSE
# ---------------------------------------------------------------------------

def test_read_chains_filters_to_run_universe():
    from apps.api.src.options.shadow_evaluator import _read_chains
    fake_batch = {
        "snapshot_at_utc": dt.datetime(2026, 5, 13, tzinfo=dt.timezone.utc),
        "provider": "tradier", "provider_version": "tradier-sandbox",
        "age_seconds": 600, "n_rows": 6561,
    }
    sess = _StubSession([[fake_batch], []])
    with patch("apps.api.src.options.shadow_evaluator.settings",
               _settings(universe=("SPY", "QQQ"))):
        _read_chains(sess, run_date=dt.date(2026, 5, 13))
    main_call = sess.calls[1]
    assert main_call["params"]["unders"] == ["SPY", "QQQ"]
    assert "underlying = ANY(:unders)" in main_call["sql"]


def test_read_chains_intersects_caller_subset_with_universe():
    """If caller passes underlyings=['SPY','AAPL'] and universe is
    SPY+QQQ, the effective filter is {SPY} only (intersection)."""
    from apps.api.src.options.shadow_evaluator import _read_chains
    fake_batch = {
        "snapshot_at_utc": dt.datetime(2026, 5, 13, tzinfo=dt.timezone.utc),
        "provider": "tradier", "provider_version": "tradier-sandbox",
        "age_seconds": 600, "n_rows": 6561,
    }
    sess = _StubSession([[fake_batch], []])
    with patch("apps.api.src.options.shadow_evaluator.settings",
               _settings(universe=("SPY", "QQQ"))):
        _read_chains(sess, run_date=dt.date(2026, 5, 13),
                     underlyings=["SPY", "AAPL", "MSFT"])
    main_call = sess.calls[1]
    assert set(main_call["params"]["unders"]) == {"SPY"}


def test_read_chains_returns_empty_when_caller_subset_disjoint_from_universe():
    """If caller passes ['AAPL'] and universe is {SPY,QQQ}, intersection
    is empty → return [] without hitting main query."""
    from apps.api.src.options.shadow_evaluator import _read_chains
    fake_batch = {
        "snapshot_at_utc": dt.datetime(2026, 5, 13, tzinfo=dt.timezone.utc),
        "provider": "tradier", "provider_version": "tradier-sandbox",
        "age_seconds": 600, "n_rows": 100,
    }
    sess = _StubSession([[fake_batch], []])
    with patch("apps.api.src.options.shadow_evaluator.settings",
               _settings(universe=("SPY",))):
        rows = _read_chains(
            sess, run_date=dt.date(2026, 5, 13), underlyings=["AAPL"])
    assert rows == []
    # Only the batch picker ran; no main read query
    assert len(sess.calls) == 1


# ---------------------------------------------------------------------------
# Composite: multiple invariants in one call
# ---------------------------------------------------------------------------

def test_read_chains_composite_all_invariants_visible():
    from apps.api.src.options.shadow_evaluator import _read_chains
    fake_batch = {
        "snapshot_at_utc": dt.datetime(2026, 5, 13, tzinfo=dt.timezone.utc),
        "provider": "tradier", "provider_version": "tradier-sandbox",
        "age_seconds": 600, "n_rows": 6561,
    }
    sess = _StubSession([[fake_batch], []])
    with patch("apps.api.src.options.shadow_evaluator.settings",
               _settings(provs=("tradier",), max_age_h=12,
                         universe=("SPY", "QQQ", "IWM", "GLD", "TLT"))):
        _read_chains(sess, run_date=dt.date(2026, 5, 13))

    picker = sess.calls[0]
    main = sess.calls[1]
    # batch picker enforces provider whitelist + freshness bound
    assert picker["params"]["provs"] == ["tradier"]
    assert picker["params"]["hrs"] == 12
    # main query enforces single batch + universe + provider_version pin
    assert main["params"]["ts"] == fake_batch["snapshot_at_utc"]
    assert main["params"]["prov"] == "tradier"
    assert main["params"]["pver"] == "tradier-sandbox"
    assert set(main["params"]["unders"]) == {
        "SPY", "QQQ", "IWM", "GLD", "TLT"}
