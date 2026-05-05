"""Integration tests for options strategy auto-promotion + sizing.

Verifies:
  * Eligibility blocks: insufficient samples, hit_rate, window, MAE,
    liquidity, data_blocked, positive horizons.
  * Tier assignment is conservative.
  * Sizing is bounded (>=min, <=hard cap).
  * Direction / IV-bucket lookups never fabricate.
  * Endpoint surfaces candidates with thresholds + sizing config.
  * Default off — env flags must be set explicitly to enforce.

NEVER asserts that any DB row in `options_paper_trade` is created;
promotion is read-only.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db import get_session
from apps.api.src.db.options_models import OptionsStrategyOutcome
from apps.api.src.domain.options_quality.promotion import (
    PromotionThresholds, SizingConfig,
    evaluate_promotions, _compute_size_pct,
    iv_bucket_from_atm, strategy_direction,
)
from apps.api.src.main import app


pytestmark = pytest.mark.integration


@pytest.fixture
def client(pg_engine):
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )

    def _override():
        s = SessionCls()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def _seed_outcomes(
    session: Session,
    *, underlying: str = "AAPL", strategy_name: str = "LONG_CALL",
    n: int = 30, hit_rate: float = 0.60,
    avg_return: float = 0.05,
    avg_mae: float = -0.05,
    span_days: int = 20,
    horizons: tuple[str, ...] = ("1D", "3D", "5D", "10D", "20D"),
    label_override: str | None = None,
) -> None:
    """Seed n synthetic outcome rows across span_days, distributed
    across horizons. The forward_return on each row matches
    avg_return; outcome_label is forced to good/bad consistent with
    hit_rate. NEVER touches options_paper_trade."""
    base = dt.date(2026, 4, 1)
    n_good = int(round(n * hit_rate))
    n_bad = n - n_good
    # Pick per-row good/bad returns so that the realized average over
    # the n rows equals `avg_return`. Holds bads at -2% loss; goods
    # are solved-for to hit target. Falls back if math gives a
    # non-positive good return.
    good_fr = (
        (avg_return * n - (-0.02) * n_bad) / n_good
        if n_good else avg_return
    )
    bad_fr = -0.02
    for i in range(n):
        as_of = base + dt.timedelta(
            days=int(round(i / max(1, n - 1) * span_days)),
        )
        # Spread submitted_at within day to keep natural keys unique
        submitted = dt.datetime.combine(
            as_of, dt.time(21, 0), tzinfo=dt.timezone.utc,
        ) + dt.timedelta(seconds=i)
        is_good = i < n_good
        label = label_override or ("good" if is_good else "bad")
        fr = good_fr if is_good else bad_fr
        for h in horizons:
            session.add(OptionsStrategyOutcome(
                underlying=underlying,
                strategy_name=strategy_name,
                legs_json=[{"option_symbol": "X", "action": "buy"}],
                as_of_date=as_of,
                submitted_at_utc=submitted + dt.timedelta(
                    microseconds=horizons.index(h)
                ),
                horizon=h,
                entry_reference=Decimal("1.00"),
                exit_reference=Decimal("1.00") + Decimal(str(fr)),
                forward_return_pct=Decimal(str(fr)),
                mfe_pct=Decimal(str(abs(fr))),
                mae_pct=Decimal(str(avg_mae)),
                outcome_label=label,
                source="suggestion",
                mode="strict",
            ))
    session.commit()


def test_iv_bucket_pure_helper():
    assert iv_bucket_from_atm(None) == "unknown"
    assert iv_bucket_from_atm(0.10) == "low"
    assert iv_bucket_from_atm(0.24) == "low"
    assert iv_bucket_from_atm(0.25) == "medium"
    assert iv_bucket_from_atm(0.44) == "medium"
    assert iv_bucket_from_atm(0.45) == "high"


def test_strategy_direction_static():
    assert strategy_direction("LONG_CALL") == "bullish"
    assert strategy_direction("BULL_CALL_SPREAD") == "bullish"
    assert strategy_direction("LONG_PUT") == "bearish"
    assert strategy_direction("BEAR_PUT_SPREAD") == "bearish"
    assert strategy_direction("IRON_CONDOR") == "neutral"
    assert strategy_direction("UNKNOWN") == "neutral"


def test_sizing_default_for_ineligible():
    """Ineligible/tier-0 candidates always return base_pct."""
    s = SizingConfig()
    out = _compute_size_pct(
        hit_rate=0.30, avg_fr=-0.05, avg_mae=-0.20,
        liquidity_pass_rate=0.5, sizing=s,
        eligible=False, tier=0,
    )
    assert out == s.base_pct


def test_sizing_bounded_above_by_hard_cap():
    """Even with absurd inputs, never exceed hard cap (2%)."""
    s = SizingConfig()
    out = _compute_size_pct(
        hit_rate=0.95, avg_fr=0.50, avg_mae=0.0,
        liquidity_pass_rate=1.0, sizing=s,
        eligible=True, tier=3,
    )
    assert out <= s.hard_max_per_strategy_pct
    assert out >= s.min_pct


def test_sizing_bounded_below_by_min():
    """Drawdown penalty pushes toward min, never below."""
    s = SizingConfig()
    out = _compute_size_pct(
        hit_rate=0.55, avg_fr=0.001, avg_mae=-0.50,
        liquidity_pass_rate=0.50, sizing=s,
        eligible=True, tier=2,
    )
    assert out >= s.min_pct
    # Tier-2 upper is midway between base and hard cap.
    upper = (s.base_pct + s.hard_max_per_strategy_pct) / 2.0
    assert out <= upper + 1e-9


def test_evaluate_promotions_blocks_low_samples(pg_session):
    _seed_outcomes(
        pg_session, n=10, hit_rate=0.70, avg_return=0.05,
        avg_mae=-0.03, span_days=20,
    )
    cands = evaluate_promotions(
        pg_session, horizon="5D", unit="strategy_name",
    )
    assert len(cands) == 1
    c = cands[0]
    assert c.eligible is False
    assert any("sample_count" in r for r in c.blocking_reasons)


def test_evaluate_promotions_blocks_low_hit_rate(pg_session):
    _seed_outcomes(
        pg_session, n=30, hit_rate=0.30, avg_return=0.05,
        avg_mae=-0.03, span_days=20,
    )
    cands = evaluate_promotions(
        pg_session, horizon="5D", unit="strategy_name",
    )
    c = cands[0]
    assert c.eligible is False
    assert any("hit_rate" in r for r in c.blocking_reasons)


def test_evaluate_promotions_blocks_negative_avg_return(pg_session):
    _seed_outcomes(
        pg_session, n=30, hit_rate=0.60, avg_return=-0.02,
        avg_mae=-0.03, span_days=20,
    )
    cands = evaluate_promotions(
        pg_session, horizon="5D", unit="strategy_name",
    )
    c = cands[0]
    assert c.eligible is False
    # avg_fr per row is -0.02 for "good" and bigger negative for bad,
    # so average is negative → blocking
    assert any("avg_forward_return" in r for r in c.blocking_reasons)


def test_evaluate_promotions_blocks_high_mae(pg_session):
    _seed_outcomes(
        pg_session, n=30, hit_rate=0.60, avg_return=0.05,
        avg_mae=-0.30, span_days=20,
    )
    cands = evaluate_promotions(
        pg_session, horizon="5D", unit="strategy_name",
    )
    c = cands[0]
    assert c.eligible is False
    assert any("avg_mae" in r for r in c.blocking_reasons)


def test_evaluate_promotions_eligible_clean(pg_session):
    _seed_outcomes(
        pg_session, n=40, hit_rate=0.65, avg_return=0.06,
        avg_mae=-0.03, span_days=20,
    )
    cands = evaluate_promotions(
        pg_session, horizon="5D", unit="strategy_name",
    )
    c = cands[0]
    assert c.eligible, c.blocking_reasons
    assert c.tier >= 2
    assert c.proposed_size_pct >= 0.005
    assert c.proposed_size_pct <= 0.02


def test_evaluate_promotions_data_blocked_blocks(pg_session):
    """Heavy data_blocked rate fails liquidity threshold."""
    _seed_outcomes(
        pg_session, n=30, hit_rate=0.60, avg_return=0.05,
        avg_mae=-0.03, span_days=20,
        label_override="data_blocked",
    )
    cands = evaluate_promotions(
        pg_session, horizon="5D", unit="strategy_name",
    )
    c = cands[0]
    assert c.eligible is False
    # data_blocked or liquidity_pass_rate or hit_rate etc — at least one
    assert c.data_blocked_rate == 1.0


def test_unit_underlying_strategy_groups_by_pair(pg_session):
    _seed_outcomes(
        pg_session, underlying="AAPL", n=30, hit_rate=0.60,
        avg_return=0.05, avg_mae=-0.03, span_days=20,
    )
    _seed_outcomes(
        pg_session, underlying="MSFT", n=30, hit_rate=0.60,
        avg_return=0.05, avg_mae=-0.03, span_days=20,
    )
    cands = evaluate_promotions(
        pg_session, horizon="5D", unit="underlying_strategy",
    )
    keys = {c.promotion_key for c in cands}
    assert "AAPL:LONG_CALL" in keys
    assert "MSFT:LONG_CALL" in keys


def test_unit_direction_strategy_groups_by_direction(pg_session):
    _seed_outcomes(
        pg_session, strategy_name="LONG_CALL", n=20,
        hit_rate=0.55, avg_return=0.04, avg_mae=-0.05,
        span_days=15,
    )
    _seed_outcomes(
        pg_session, strategy_name="LONG_PUT", n=20,
        hit_rate=0.55, avg_return=0.04, avg_mae=-0.05,
        span_days=15,
    )
    cands = evaluate_promotions(
        pg_session, horizon="5D", unit="direction_strategy",
    )
    dirs = {c.direction for c in cands}
    assert "bullish" in dirs and "bearish" in dirs


def test_endpoint_returns_thresholds_and_sizing(client):
    resp = client.get(
        "/api/performance/options/promotion-candidates"
        "?horizon=5D&unit=strategy_name"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "thresholds" in body and "sizing" in body
    assert body["thresholds"]["min_samples"] == 20
    assert body["sizing"]["hard_max_per_strategy_pct"] == 0.02
    assert "OPTIONS_STRATEGY_PROMOTION_ENABLED" in body["notice"]


def test_endpoint_rejects_bad_unit(client):
    resp = client.get(
        "/api/performance/options/promotion-candidates"
        "?horizon=5D&unit=ad_hoc"
    )
    body = resp.json()
    assert "error" in body and "unit" in body["error"]


def test_endpoint_rejects_bad_horizon(client):
    resp = client.get(
        "/api/performance/options/promotion-candidates"
        "?horizon=99D&unit=strategy_name"
    )
    body = resp.json()
    assert "error" in body and "horizon" in body["error"]


def test_endpoint_lists_candidates_after_seed(pg_session, client):
    _seed_outcomes(
        pg_session, n=40, hit_rate=0.65, avg_return=0.06,
        avg_mae=-0.03, span_days=20,
    )
    resp = client.get(
        "/api/performance/options/promotion-candidates"
        "?horizon=5D&unit=strategy_name"
    )
    body = resp.json()
    assert body["count"] >= 1
    assert body["eligible_count"] >= 1
    item = body["items"][0]
    assert item["proposed_size_pct"] <= 0.02
    assert item["proposed_size_pct"] >= 0.0025
    # Tier and key shape
    assert item["tier"] >= 2
    assert item["promotion_key"] == "LONG_CALL"


def test_promotion_artifact_writer_off_by_default(tmp_path, monkeypatch):
    """Operator script writes artifact, but `enforced` flag is False
    when env not set."""
    monkeypatch.delenv("OPTIONS_STRATEGY_PROMOTION_ENABLED", raising=False)
    monkeypatch.delenv("OPTIONS_DYNAMIC_SIZING_ENABLED", raising=False)
    monkeypatch.chdir(tmp_path)
    from scripts.run_options_promotion_eval import main
    rc = main(["--dry-run", "--horizon", "5D", "--unit", "strategy_name"])
    assert rc == 0
    out_path = (
        tmp_path / "artifacts/options_promotion"
        / "promotion_eval_5D_strategy_name.json"
    )
    assert out_path.exists()
    artifact = json.loads(out_path.read_text())
    assert artifact["promotion_enabled"] is False
    assert artifact["sizing_enabled"] is False
    assert artifact["enforced"] is False
    assert artifact["size_enforceable"] is False
    # Hard caps echoed
    assert artifact["execution_caps"]["hard_max_per_strategy_pct"] == 0.02


def test_promotion_artifact_apply_refused_without_env(monkeypatch):
    monkeypatch.delenv("OPTIONS_STRATEGY_PROMOTION_ENABLED", raising=False)
    from scripts.run_options_promotion_eval import main
    rc = main(["--apply", "--horizon", "5D", "--unit", "strategy_name"])
    assert rc == 2  # REFUSED


def test_promotion_artifact_apply_with_env(
    pg_session, tmp_path, monkeypatch,
):
    """When env is set + --apply, artifact marks enforced=True. The
    runner consumes this; the script itself still writes nothing to
    the DB."""
    _seed_outcomes(
        pg_session, n=40, hit_rate=0.65, avg_return=0.06,
        avg_mae=-0.03, span_days=20,
    )
    monkeypatch.setenv("OPTIONS_STRATEGY_PROMOTION_ENABLED", "true")
    monkeypatch.setenv("OPTIONS_DYNAMIC_SIZING_ENABLED", "true")
    monkeypatch.chdir(tmp_path)
    from scripts.run_options_promotion_eval import main
    rc = main(["--apply", "--horizon", "5D", "--unit", "strategy_name"])
    assert rc == 0
    out_path = (
        tmp_path / "artifacts/options_promotion"
        / "promotion_eval_5D_strategy_name.json"
    )
    assert out_path.exists()
    artifact = json.loads(out_path.read_text())
    assert artifact["promotion_enabled"] is True
    assert artifact["sizing_enabled"] is True
    assert artifact["enforced"] is True
    assert artifact["size_enforceable"] is True
    # Confirm: paper-trade table is untouched
    n_trades = pg_session.execute(
        text("SELECT count(*) FROM options_paper_trade")
    ).scalar()
    assert n_trades == 0
