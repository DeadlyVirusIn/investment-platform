"""Phase 11O - dry-run unit tests for the manual options paper
evaluation runner.

Exercises pure-fn pipeline pieces against in-memory fixtures so we
need no Postgres for the bulk of the logic. PG-only behaviours
(dedupe, full open_trade) are covered in the integration suite.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.observatory.rules import (
    CriterionCheck,
    RuleEvaluation,
)
from apps.api.src.options.paper import eval_runner
from apps.api.src.options.paper.eval_runner import (
    step_apply_max_open,
    step_collect_qualified,
    step_plan_trade,
)
from apps.api.src.options.paper.eval_runner_models import (
    PlannedTrade,
    RunnerConfig,
    RunnerSummary,
)
from apps.api.src.options.paper.strategies import (
    LegSpec,
    RiskMetrics,
    STRATEGY_IRON_CONDOR,
    STRATEGY_SHORT_CALL_CREDIT_SPREAD,
    STRATEGY_SHORT_PUT_CREDIT_SPREAD,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EXPIRY = datetime.date(2026, 6, 18)
AS_OF = datetime.date(2026, 4, 27)
SNAP = datetime.datetime(2026, 4, 27, 14, 0, tzinfo=datetime.timezone.utc)


def _q(
    *,
    option_type: str,
    strike: float,
    bid: float = 1.0,
    ask: float = 1.05,
    delta: float = -0.30,
    age: int = 2,
    underlying: str = "SPY",
    expiry: datetime.date = EXPIRY,
) -> OptionChainQuote:
    mid = (bid + ask) / 2
    sym = (
        f"{underlying}{expiry.strftime('%y%m%d')}"
        f"{option_type[0]}{int(strike * 1000):08d}"
    )
    return OptionChainQuote(
        snapshot_at_utc=SNAP,
        underlying=underlying,
        expiry=expiry,
        strike=Decimal(str(strike)),
        option_type=option_type,
        option_symbol=sym,
        bid=Decimal(str(bid)),
        ask=Decimal(str(ask)),
        mid=Decimal(str(mid)),
        last=Decimal(str(bid)),
        volume=100,
        open_interest=1000,
        delta=Decimal(str(delta)),
        gamma=Decimal("0.02"),
        theta=Decimal("-0.05"),
        vega=Decimal("0.10"),
        iv=Decimal("0.20"),
        quote_age_seconds=age,
        provider="thetadata",
    )


def _qualified_put_eval(
    short: OptionChainQuote, long_: OptionChainQuote,
) -> RuleEvaluation:
    return RuleEvaluation(
        rule_id=STRATEGY_SHORT_PUT_CREDIT_SPREAD,
        name="Short put credit spread",
        qualified=True,
        n_criteria=5, n_passed=5,
        checks=tuple(
            CriterionCheck(code=c, passed=True, reason="ok")
            for c in (
                "SHORT_LEG_DELTA_BAND", "LONG_LEG_PROTECTION",
                "LIQUIDITY", "DTE_BAND", "SAME_QTY_SAME_EXPIRY",
            )
        ),
        candidate={
            "side": "PUT",
            "short_strike": str(short.strike),
            "short_delta": str(short.delta),
            "long_strike": str(long_.strike),
            "expiry": short.expiry.isoformat(),
            "short_symbol": short.option_symbol,
            "long_symbol": long_.option_symbol,
        },
    )


def _config(**overrides) -> RunnerConfig:
    base = dict(
        date=AS_OF, underlyings=("SPY",), strategy_filter=None,
        dry_run=True, commit=False, max_open=5,
        explain=False, skip_ingest=True,
    )
    base.update(overrides)
    return RunnerConfig(**base)


# ---------------------------------------------------------------------------
# step_plan_trade
# ---------------------------------------------------------------------------

def test_step_plan_trade_builds_defined_risk_legs():
    short = _q(option_type="PUT", strike=440, bid=1.20, ask=1.25, delta=-0.30)
    long_ = _q(option_type="PUT", strike=435, bid=0.50, ask=0.55, delta=-0.18)
    ev = _qualified_put_eval(short, long_)
    p = step_plan_trade(
        underlying="SPY", rule_eval=ev,
        accepted_quotes=[short, long_], as_of_date=AS_OF,
    )
    assert p.qualified is True
    assert p.committable is True
    assert p.rejection_reasons == ()
    assert len(p.legs) == 2
    assert {l.side for l in p.legs} == {"SELL", "BUY"}
    assert p.risk is not None
    assert p.risk.max_loss_dollars > 0
    assert p.risk.max_profit_dollars > 0
    assert p.entry_credit_dollars is not None
    assert p.entry_credit_dollars > 0
    assert p.quote_age_max_seconds == 2
    assert p.observation_id == (
        "SPY:2026-04-27:" + STRATEGY_SHORT_PUT_CREDIT_SPREAD
    )


def test_step_plan_trade_rejects_when_candidate_missing():
    ev = RuleEvaluation(
        rule_id=STRATEGY_SHORT_PUT_CREDIT_SPREAD,
        name="x", qualified=True,
        n_criteria=5, n_passed=5, checks=(),
        candidate=None,
    )
    p = step_plan_trade(
        underlying="SPY", rule_eval=ev,
        accepted_quotes=[], as_of_date=AS_OF,
    )
    assert p.committable is False
    assert "CANDIDATE_MISSING" in p.rejection_reasons


def test_step_plan_trade_rejects_when_quote_missing():
    short = _q(option_type="PUT", strike=440)
    long_ = _q(option_type="PUT", strike=435)
    ev = _qualified_put_eval(short, long_)
    # Provide only the short — long is missing from accepted quotes
    p = step_plan_trade(
        underlying="SPY", rule_eval=ev,
        accepted_quotes=[short], as_of_date=AS_OF,
    )
    assert p.committable is False
    assert any("QUOTE_MISSING" in r for r in p.rejection_reasons)


def test_step_plan_trade_rejects_non_defined_risk():
    """Build a put credit spread candidate where the long strike is
    above the short strike — defined-risk validator should reject."""
    short = _q(option_type="PUT", strike=440)
    long_ = _q(option_type="PUT", strike=445)  # invalid: long > short
    ev = _qualified_put_eval(short, long_)
    p = step_plan_trade(
        underlying="SPY", rule_eval=ev,
        accepted_quotes=[short, long_], as_of_date=AS_OF,
    )
    assert p.committable is False
    assert any("NOT_DEFINED_RISK" in r for r in p.rejection_reasons)


def test_step_plan_trade_iron_condor_builds_four_legs():
    long_put   = _q(option_type="PUT",  strike=425, bid=0.30, ask=0.35, delta=-0.10)
    short_put  = _q(option_type="PUT",  strike=440, bid=1.20, ask=1.25, delta=-0.30)
    short_call = _q(option_type="CALL", strike=460, bid=1.10, ask=1.15, delta=0.30)
    long_call  = _q(option_type="CALL", strike=465, bid=0.40, ask=0.45, delta=0.18)
    ev = RuleEvaluation(
        rule_id=STRATEGY_IRON_CONDOR, name="Iron condor", qualified=True,
        n_criteria=5, n_passed=5, checks=(),
        candidate={
            "put_wing": {
                "side": "PUT",
                "short_strike": str(short_put.strike),
                "long_strike":  str(long_put.strike),
                "expiry":       EXPIRY.isoformat(),
                "short_symbol": short_put.option_symbol,
                "long_symbol":  long_put.option_symbol,
            },
            "call_wing": {
                "side": "CALL",
                "short_strike": str(short_call.strike),
                "long_strike":  str(long_call.strike),
                "expiry":       EXPIRY.isoformat(),
                "short_symbol": short_call.option_symbol,
                "long_symbol":  long_call.option_symbol,
            },
        },
    )
    p = step_plan_trade(
        underlying="SPY", rule_eval=ev,
        accepted_quotes=[long_put, short_put, short_call, long_call],
        as_of_date=AS_OF,
    )
    assert p.committable is True
    assert len(p.legs) == 4
    types = sorted([l.option_type for l in p.legs])
    assert types == ["CALL", "CALL", "PUT", "PUT"]
    sides = sorted([l.side for l in p.legs])
    assert sides == ["BUY", "BUY", "SELL", "SELL"]


def test_step_plan_trade_rejects_when_mid_missing():
    short = _q(option_type="PUT", strike=440)
    short_no_mid = OptionChainQuote(**{
        **short.__dict__, "mid": None,
    })
    long_ = _q(option_type="PUT", strike=435)
    ev = _qualified_put_eval(short_no_mid, long_)
    p = step_plan_trade(
        underlying="SPY", rule_eval=ev,
        accepted_quotes=[short_no_mid, long_], as_of_date=AS_OF,
    )
    assert p.committable is False
    assert any("MID_MISSING" in r for r in p.rejection_reasons)


# ---------------------------------------------------------------------------
# step_collect_qualified
# ---------------------------------------------------------------------------

def test_step_collect_qualified_filters_unqualified(monkeypatch):
    short = _q(option_type="PUT", strike=440)
    long_ = _q(option_type="PUT", strike=435)
    quotes = [short, long_]

    def fake_read_day(session, *, symbol, day):
        return quotes if symbol == "SPY" else []

    qualified_ev = _qualified_put_eval(short, long_)
    unqualified_ev = RuleEvaluation(
        rule_id=STRATEGY_SHORT_CALL_CREDIT_SPREAD,
        name="x", qualified=False,
        n_criteria=5, n_passed=2, checks=(), candidate=None,
    )

    def fake_evaluate_rules(accepted, *, as_of):
        return [qualified_ev, unqualified_ev]

    class FakeFilterResult:
        def __init__(self, accepted):
            self.accepted = tuple(accepted)

    def fake_filter_chain(quotes, **kwargs):
        return FakeFilterResult(quotes)

    monkeypatch.setattr(eval_runner, "_read_day", fake_read_day)
    monkeypatch.setattr(eval_runner, "evaluate_rules", fake_evaluate_rules)
    monkeypatch.setattr(eval_runner, "filter_chain", fake_filter_chain)

    n_total, triples = step_collect_qualified(
        session=None, date=AS_OF,
        underlyings=("SPY",), strategy_filter=None,
    )
    assert n_total == 2
    assert len(triples) == 1
    sym, ev, accepted = triples[0]
    assert sym == "SPY"
    assert ev.qualified is True
    assert len(accepted) == 2


def test_step_collect_qualified_applies_strategy_filter(monkeypatch):
    short = _q(option_type="PUT", strike=440)
    long_ = _q(option_type="PUT", strike=435)
    quotes = [short, long_]
    ev_put = _qualified_put_eval(short, long_)
    ev_call = RuleEvaluation(
        rule_id=STRATEGY_SHORT_CALL_CREDIT_SPREAD,
        name="x", qualified=True,
        n_criteria=5, n_passed=5, checks=(), candidate={},
    )

    monkeypatch.setattr(
        eval_runner, "_read_day",
        lambda session, *, symbol, day: quotes,
    )
    monkeypatch.setattr(
        eval_runner, "evaluate_rules",
        lambda accepted, *, as_of: [ev_put, ev_call],
    )

    class FakeFilterResult:
        def __init__(self, accepted):
            self.accepted = tuple(accepted)

    monkeypatch.setattr(
        eval_runner, "filter_chain",
        lambda quotes, **kwargs: FakeFilterResult(quotes),
    )

    n_total, triples = step_collect_qualified(
        session=None, date=AS_OF,
        underlyings=("SPY",),
        strategy_filter=(STRATEGY_SHORT_PUT_CREDIT_SPREAD,),
    )
    assert n_total == 1
    assert len(triples) == 1
    assert triples[0][1].rule_id == STRATEGY_SHORT_PUT_CREDIT_SPREAD


def test_step_collect_qualified_returns_zero_on_empty_chain(monkeypatch):
    monkeypatch.setattr(
        eval_runner, "_read_day",
        lambda session, *, symbol, day: [],
    )
    n_total, triples = step_collect_qualified(
        session=None, date=AS_OF,
        underlyings=("SPY",), strategy_filter=None,
    )
    assert n_total == 0
    assert triples == []


# ---------------------------------------------------------------------------
# step_apply_max_open
# ---------------------------------------------------------------------------

def _planned(underlying: str, rule_id: str) -> PlannedTrade:
    return PlannedTrade(
        observation_id=f"{underlying}:2026-04-27:{rule_id}",
        underlying=underlying, rule_id=rule_id,
        legs=(LegSpec(
            side="SELL", option_type="PUT",
            strike=Decimal("440"), expiry=EXPIRY, qty=1,
            option_symbol="X",
        ),),
        risk=RiskMetrics(
            max_loss_dollars=Decimal("100"),
            max_profit_dollars=Decimal("50"),
            breakeven_lower=None, breakeven_upper=None,
        ),
        entry_credit_dollars=Decimal("50"),
        quote_age_max_seconds=2,
        rejection_reasons=(), qualified=True,
    )


def test_step_apply_max_open_truncates_deterministically():
    ps = [
        _planned("QQQ", STRATEGY_SHORT_PUT_CREDIT_SPREAD),
        _planned("SPY", STRATEGY_SHORT_PUT_CREDIT_SPREAD),
        _planned("SPY", STRATEGY_IRON_CONDOR),
        _planned("AAA", STRATEGY_SHORT_PUT_CREDIT_SPREAD),
    ]
    out = step_apply_max_open(ps, cap=2)
    assert [(p.underlying, p.rule_id) for p in out] == [
        ("AAA", STRATEGY_SHORT_PUT_CREDIT_SPREAD),
        ("QQQ", STRATEGY_SHORT_PUT_CREDIT_SPREAD),
    ]


def test_step_apply_max_open_returns_empty_for_zero_cap():
    ps = [_planned("SPY", STRATEGY_SHORT_PUT_CREDIT_SPREAD)]
    out = step_apply_max_open(ps, cap=0)
    assert out == []


def test_step_apply_max_open_no_truncation_when_cap_exceeds():
    ps = [_planned("SPY", STRATEGY_SHORT_PUT_CREDIT_SPREAD)]
    out = step_apply_max_open(ps, cap=10)
    assert len(out) == 1


# ---------------------------------------------------------------------------
# Dry-run = zero mutation
# ---------------------------------------------------------------------------

def test_dry_run_calls_no_engine_mutation(monkeypatch):
    """When config.dry_run is True the runner must NEVER call open_trade,
    record_mtm, close_trade, expire_trade or write the audit log."""

    short = _q(option_type="PUT", strike=440, bid=1.20, ask=1.25, delta=-0.30)
    long_ = _q(option_type="PUT", strike=435, bid=0.50, ask=0.55, delta=-0.18)
    quotes = [short, long_]
    ev = _qualified_put_eval(short, long_)

    monkeypatch.setattr(
        eval_runner, "_read_day",
        lambda session, *, symbol, day: quotes,
    )

    class FakeFilterResult:
        def __init__(self, accepted):
            self.accepted = tuple(accepted)

    monkeypatch.setattr(
        eval_runner, "filter_chain",
        lambda quotes, **kwargs: FakeFilterResult(quotes),
    )
    monkeypatch.setattr(
        eval_runner, "evaluate_rules",
        lambda accepted, *, as_of: [ev],
    )
    monkeypatch.setattr(
        eval_runner, "step_ingest_chain",
        lambda *, snapshot_at_utc, universe: 0,
    )

    # Track that open_trade is NEVER called in dry-run.
    calls: list = []

    def boom(*a, **kw):
        calls.append((a, kw))
        raise AssertionError("open_trade must not be called in dry-run")

    monkeypatch.setattr(eval_runner, "open_trade", boom)

    # Bypass real DB via a dummy session contextmanager / dedupe SQL
    class FakeSession:
        def execute(self, sql, params=None):  # noqa: D401
            class _R:
                def all(self_inner):
                    return []
            return _R()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_session_factory():
        return FakeSession()

    settings_obj = SimpleNamespace(
        OPTIONS_ENABLED=True,
        OPTIONS_PAPER_ONLY=True,
        OPTIONS_ML_CAN_AFFECT_TRADES=False,
    )

    cfg = _config(skip_ingest=False)  # exercise the ingest branch too
    summary = eval_runner.run(
        cfg, settings_obj=settings_obj,
        session_factory=fake_session_factory,
    )

    assert calls == [], "open_trade must not be invoked in dry-run"
    assert summary.config.dry_run is True
    assert summary.n_committed == 0
    assert len(summary.committed_trade_ids) == 0
    assert summary.n_qualified == 1
    assert summary.n_planned == 1


# ---------------------------------------------------------------------------
# Summary serialisation shape
# ---------------------------------------------------------------------------

def test_summary_shape_dry_run():
    cfg = _config()
    s = RunnerSummary(
        config=cfg,
        n_chain_inserted=0, n_observations_total=0,
        n_qualified=0, n_planned=0, n_planned_rejected=0,
        n_existing_open_trade_dedup=0, n_committed=0,
        planned_trades=(), committed_trade_ids=(),
    )
    assert s.config.dry_run is True
    assert s.config.commit is False
    assert s.n_committed == 0
    assert s.committed_trade_ids == ()
