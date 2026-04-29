"""Phase 11R - fast-fill research-mode unit tests."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest

from apps.api.src.data.research import fast_fill_runner as ff
from apps.api.src.data.research.fast_fill_runner import (
    DEFAULT_ENGINE,
    DEFAULT_MAX_PER_DAY,
    DEFAULT_RULE_ID,
    DEFAULT_SIDE,
    DEFAULT_UNDERLYINGS,
    DECISION_TS_HOUR_UTC,
    FILL_MODEL,
    HARD_MAX_PER_DAY,
    JSONL_LOG_PREFIX,
    LABEL_VERSION,
    PRIORITY_ORDER,
    RESEARCH_QTY_PAPER,
    SOURCE,
    FillCandidate,
    PlannedFill,
    RunnerConfig,
    business_days_in_window,
    decision_ts_for,
    select_same_day_fill_price,
)


D = Decimal


# ---------------------------------------------------------------------------
# Frozen constants
# ---------------------------------------------------------------------------

def test_source_constant_frozen():
    assert SOURCE == "research_fast_fill"


def test_fill_model_constant_frozen():
    assert FILL_MODEL == "same_day_research_v1"


def test_label_version_constant_frozen():
    assert LABEL_VERSION == "research-fast-fill-v1.0.0"


def test_decision_ts_hour_utc_frozen():
    assert DECISION_TS_HOUR_UTC == 15


def test_priority_order_frozen():
    assert PRIORITY_ORDER == ("vwap", "close", "open")


def test_research_qty_is_one():
    assert RESEARCH_QTY_PAPER == D("1")


def test_default_underlyings_frozen():
    assert DEFAULT_UNDERLYINGS == ("SPY", "QQQ", "IWM", "GLD", "TLT")


def test_default_max_per_day_is_20():
    assert DEFAULT_MAX_PER_DAY == 20


def test_hard_max_per_day_is_100():
    assert HARD_MAX_PER_DAY == 100


def test_default_rule_id_research():
    assert DEFAULT_RULE_ID == "research_fast_fill_open_buy_v1"
    assert DEFAULT_ENGINE == "research"
    assert DEFAULT_SIDE == "BUY"


# ---------------------------------------------------------------------------
# Fill-price selection (pure-fn)
# ---------------------------------------------------------------------------

def _bar(*, ts, open=None, close=None, vwap=None):
    return {"ts": ts, "open": open, "close": close, "vwap": vwap,
            "asset_id": None}


def test_select_fill_price_prefers_vwap():
    decision_ts = dt.datetime(
        2026, 4, 28, 15, 0, tzinfo=dt.timezone.utc,
    )
    bars = [
        _bar(
            ts=dt.datetime(
                2026, 4, 28, 13, 30, tzinfo=dt.timezone.utc,
            ),
            open=D("440"), close=D("445"), vwap=D("443"),
        ),
    ]
    out = select_same_day_fill_price(bars, decision_ts=decision_ts)
    assert out is not None
    assert out.fill_price == D("443")
    assert out.fill_price_source == "vwap"


def test_select_fill_price_falls_back_to_close():
    decision_ts = dt.datetime(
        2026, 4, 28, 15, 0, tzinfo=dt.timezone.utc,
    )
    bars = [
        _bar(
            ts=dt.datetime(
                2026, 4, 28, 21, 0, tzinfo=dt.timezone.utc,
            ),
            open=D("440"), close=D("445"), vwap=None,
        ),
    ]
    out = select_same_day_fill_price(bars, decision_ts=decision_ts)
    assert out is not None
    assert out.fill_price == D("445")
    assert out.fill_price_source == "close"


def test_select_fill_price_falls_back_to_open_only_if_pre_decision():
    decision_ts = dt.datetime(
        2026, 4, 28, 15, 0, tzinfo=dt.timezone.utc,
    )
    bars = [
        _bar(
            ts=dt.datetime(
                2026, 4, 28, 13, 30, tzinfo=dt.timezone.utc,
            ),
            open=D("440"), close=None, vwap=None,
        ),
    ]
    out = select_same_day_fill_price(bars, decision_ts=decision_ts)
    assert out is not None
    assert out.fill_price == D("440")
    assert out.fill_price_source == "open"


def test_select_fill_price_skips_when_open_after_decision():
    decision_ts = dt.datetime(
        2026, 4, 28, 15, 0, tzinfo=dt.timezone.utc,
    )
    bars = [
        _bar(
            ts=dt.datetime(
                2026, 4, 28, 16, 0, tzinfo=dt.timezone.utc,
            ),
            open=D("440"), close=None, vwap=None,
        ),
    ]
    out = select_same_day_fill_price(bars, decision_ts=decision_ts)
    assert out is None


def test_select_fill_price_returns_none_when_no_bar():
    decision_ts = dt.datetime(
        2026, 4, 28, 15, 0, tzinfo=dt.timezone.utc,
    )
    assert select_same_day_fill_price([], decision_ts=decision_ts) is None


def test_select_fill_price_filters_none_bars():
    decision_ts = dt.datetime(
        2026, 4, 28, 15, 0, tzinfo=dt.timezone.utc,
    )
    bars = [None, _bar(  # type: ignore[list-item]
        ts=dt.datetime(2026, 4, 28, 21, 0, tzinfo=dt.timezone.utc),
        close=D("445"),
    )]
    out = select_same_day_fill_price(bars, decision_ts=decision_ts)
    assert out is not None
    assert out.fill_price_source == "close"


def test_select_fill_price_uses_first_bar_with_vwap():
    decision_ts = dt.datetime(
        2026, 4, 28, 15, 0, tzinfo=dt.timezone.utc,
    )
    bars = [
        _bar(
            ts=dt.datetime(
                2026, 4, 28, 13, 30, tzinfo=dt.timezone.utc,
            ),
            close=D("445"), vwap=D("443"),
        ),
        _bar(
            ts=dt.datetime(
                2026, 4, 28, 16, 30, tzinfo=dt.timezone.utc,
            ),
            close=D("446"), vwap=D("444"),
        ),
    ]
    out = select_same_day_fill_price(bars, decision_ts=decision_ts)
    assert out is not None
    assert out.fill_price == D("443")  # first bar's vwap


def test_select_fill_price_close_uses_latest_bar():
    decision_ts = dt.datetime(
        2026, 4, 28, 15, 0, tzinfo=dt.timezone.utc,
    )
    bars = [
        _bar(
            ts=dt.datetime(
                2026, 4, 28, 13, 30, tzinfo=dt.timezone.utc,
            ),
            close=D("440"),
        ),
        _bar(
            ts=dt.datetime(
                2026, 4, 28, 21, 0, tzinfo=dt.timezone.utc,
            ),
            close=D("445"),
        ),
    ]
    out = select_same_day_fill_price(bars, decision_ts=decision_ts)
    assert out is not None
    assert out.fill_price == D("445")


# ---------------------------------------------------------------------------
# decision_ts + business days
# ---------------------------------------------------------------------------

def test_decision_ts_for_is_15_utc():
    out = decision_ts_for(dt.date(2026, 4, 28))
    assert out == dt.datetime(
        2026, 4, 28, 15, 0, tzinfo=dt.timezone.utc,
    )


def test_business_days_filters_weekends():
    cfg = RunnerConfig(
        date=dt.date(2026, 4, 27),         # Monday
        backfill_from=dt.date(2026, 4, 24),  # Friday
        underlyings=("SPY",),
        max_per_day=20,
        label_version=LABEL_VERSION,
        dry_run=True, commit=False,
        explain=False, skip_context=True,
    )
    days = business_days_in_window(cfg)
    assert days == [dt.date(2026, 4, 24), dt.date(2026, 4, 27)]


# ---------------------------------------------------------------------------
# Config invariants
# ---------------------------------------------------------------------------

def _cfg(**kw):
    base = dict(
        date=dt.date(2026, 4, 28), backfill_from=None,
        underlyings=("SPY",), max_per_day=20,
        label_version=LABEL_VERSION,
        dry_run=True, commit=False,
        explain=False, skip_context=False,
    )
    base.update(kw)
    return RunnerConfig(**base)


def test_dry_xor_commit():
    with pytest.raises(ValueError, match="mutually exclusive"):
        _cfg(dry_run=True, commit=True)
    with pytest.raises(ValueError, match="mutually exclusive"):
        _cfg(dry_run=False, commit=False)


def test_max_per_day_bounds():
    for bad in (0, -1, HARD_MAX_PER_DAY + 1):
        with pytest.raises(ValueError, match="max_per_day"):
            _cfg(max_per_day=bad)
    for ok in (1, 50, HARD_MAX_PER_DAY):
        assert _cfg(max_per_day=ok).max_per_day == ok


def test_underlyings_required():
    with pytest.raises(ValueError, match="underlyings"):
        _cfg(underlyings=())


def test_backfill_from_must_be_le_date():
    with pytest.raises(ValueError, match="backfill_from"):
        _cfg(backfill_from=dt.date(2026, 5, 10))


# ---------------------------------------------------------------------------
# Boundary scans
# ---------------------------------------------------------------------------

def test_runner_no_forbidden_imports():
    src = Path(ff.__file__).read_text(encoding="utf-8")
    for tok in (
        "from broker_", "import broker_",
        "from live_", "import live_",
        "from execution_", "import execution_",
        "order_router",
    ):
        assert tok not in src, f"forbidden token {tok!r}"


def test_runner_does_not_import_strict_engine():
    src = Path(ff.__file__).read_text(encoding="utf-8")
    for tok in (
        "data.strategy.engine_a", "data.strategy.engine_b",
        "data.strategy.selector", "data.context.production",
        "options.paper.engine", "options.paper.eval_runner",
        "domain.paper_trading.auto_trader",
    ):
        assert tok not in src, f"strict-engine module pulled in: {tok!r}"


def test_runner_does_not_register_into_REGISTRY():
    from apps.worker.src.jobs.registry import REGISTRY
    assert "research_fast_fill" not in [k.lower() for k in REGISTRY]
    assert all(
        "research" not in k.lower() and "fast_fill" not in k.lower()
        for k in REGISTRY.keys()
    )


def test_runner_does_not_write_paper_trade_paper_position_or_decision_log():
    src = Path(ff.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "INSERT INTO paper_trade",
        "INSERT INTO paper_position",
        "INSERT INTO paper_portfolio",
        "INSERT INTO paper_equity_snapshot",
        "INSERT INTO decision_log",
        "UPDATE paper_trade",
        "UPDATE decision_log",
    ):
        assert forbidden not in src, (
            f"runner must never touch strict tables: {forbidden!r}"
        )


def test_runner_only_inserts_into_paper_research_fill():
    src = Path(ff.__file__).read_text(encoding="utf-8")
    inserts = []
    for line in src.splitlines():
        if "INSERT INTO" in line:
            inserts.append(line.strip())
    # Module currently issues exactly one INSERT statement, into the
    # research-fill table. Comments mentioning the constant token are
    # not full INSERT statements — filter to actual SQL strings.
    actual_inserts = [
        s for s in inserts if "INSERT INTO " in s
    ]
    for s in actual_inserts:
        assert "INSERT INTO paper_research_fill" in s, (
            f"unexpected INSERT in fast_fill_runner: {s}"
        )


def test_runner_no_recommendation_language():
    src = Path(ff.__file__).read_text(encoding="utf-8")
    for tok in (
        "recommend", "best trade", "top pick", "trade now",
        "place order", "auto-trade", "promote",
    ):
        assert tok.lower() not in src.lower(), (
            f"forbidden user-facing token {tok!r}"
        )


def test_runner_uses_only_same_day_filter_in_sql():
    """Hard guard: the SQL query restricts ts::date to the as_of_date,
    preventing future-bar bleed-through."""
    src = Path(ff.__file__).read_text(encoding="utf-8")
    assert "pb.ts::date = :day" in src
    # Must not query a date range that walks forward.
    for forbidden in (
        "BETWEEN :start AND :end",
        "ts::date > :day",
        "ts::date >= :day",
    ):
        assert forbidden not in src, (
            f"runner must not read future bars: {forbidden!r}"
        )


def test_cli_module_default_is_dry_run():
    cli = (
        Path(__file__).resolve().parents[4]
        / "scripts" / "run_research_fast_fill.py"
    )
    src = cli.read_text(encoding="utf-8")
    assert "dry_run = not commit" in src


def test_jsonl_log_prefix_includes_research_tag():
    assert JSONL_LOG_PREFIX == "research_fast_fill_"


def test_planned_fill_skipped_default_state():
    p = PlannedFill(
        decision_ts=decision_ts_for(dt.date(2026, 4, 28)),
        as_of_date=dt.date(2026, 4, 28),
        underlying="SPY", asset_id=None,
        rule_id=DEFAULT_RULE_ID, engine=DEFAULT_ENGINE,
        side=DEFAULT_SIDE, qty=RESEARCH_QTY_PAPER,
        fill_price=None, fill_price_source=None, fill_ts=None,
        gate_snapshot={}, failed_gates=(),
        skipped=True, skip_reason="no_same_day_bar",
    )
    assert p.skipped is True
    assert p.fill_price is None
    assert p.skip_reason == "no_same_day_bar"
