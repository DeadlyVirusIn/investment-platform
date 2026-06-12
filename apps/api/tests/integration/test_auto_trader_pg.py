"""Integration tests for the auto_trader + run_paper_trading job."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    PaperPortfolio,
    PaperPosition,
    PaperTrade,
    PriceBar,
    Recommendation,
)
from apps.api.src.domain.paper_trading.auto_trader import (
    AutoTradeConfig,
    auto_trade_portfolio,
    generate_decisions,
)
from apps.api.src.domain.paper_trading.paper_service import (
    PortfolioCreate,
    create_portfolio,
)
from apps.worker.src.jobs.run_paper_trading import run_paper_trading

pytestmark = pytest.mark.integration

BASE_TS = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _seed_asset_with_prices(
    pg_session: Session,
    symbol: str,
    n_bars: int = 40,
    open_price: Decimal = Decimal("100"),
    step: Decimal = Decimal("0"),
) -> str:
    asset = Asset(symbol=symbol, asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()
    for i in range(n_bars):
        p = open_price + step * Decimal(i)
        pg_session.add(PriceBar(
            asset_id=asset.id, timeframe="1d",
            ts=BASE_TS + dt.timedelta(days=i),
            open=p, high=p + Decimal("0.5"), low=p - Decimal("0.5"),
            close=p, adjusted_close=p, volume=1_000_000, provider="test",
        ))
    pg_session.commit()
    return asset.id


def _seed_recommendation(
    pg_session: Session,
    asset_id: str,
    action: str,
    conviction: Decimal,
    snap: str,
    offset_days_ago: int = 0,
) -> str:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    rec = Recommendation(
        asset_id=asset_id, action=action, conviction=conviction,
        model_version="0.1.0", snapshot_hash=snap,
        rationale='{"snapshot_hash":"' + snap + '"}',
        generated_at=now - dt.timedelta(days=offset_days_ago),
    )
    pg_session.add(rec)
    pg_session.flush()
    pg_session.commit()
    return rec.id


def _active_portfolio(pg_session: Session, name: str, cash: str = "10000") -> PaperPortfolio:
    p = create_portfolio(pg_session, PortfolioCreate(name=name, starting_cash=Decimal(cash)))
    pg_session.commit()
    return p


# ---------------------------------------------------------------------------
# Decision rules
# ---------------------------------------------------------------------------


def test_high_confidence_buy_produces_open_buy(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(pg_session, "BUY1")
    _seed_recommendation(pg_session, asset_id, "Buy", Decimal("70"), "s1")
    p = _active_portfolio(pg_session, "ct-buy")

    decisions = generate_decisions(
        pg_session, p, AutoTradeConfig(buy_confidence_threshold=Decimal("60")),
        now=BASE_TS,
    )
    assert len(decisions) == 1
    d = decisions[0]
    assert d.kind == "open_buy"
    assert d.asset_id == asset_id
    assert d.usd_amount == Decimal("1000.00")  # 10% of 10000


def test_low_confidence_buy_is_skipped(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(pg_session, "LOWC")
    _seed_recommendation(pg_session, asset_id, "Buy", Decimal("40"), "s2")
    p = _active_portfolio(pg_session, "ct-low")

    decisions = generate_decisions(
        pg_session, p, AutoTradeConfig(buy_confidence_threshold=Decimal("60")),
        now=BASE_TS,
    )
    assert decisions == []


def test_already_held_asset_skipped(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(pg_session, "HELD")
    _seed_recommendation(pg_session, asset_id, "Buy", Decimal("80"), "s3")
    p = _active_portfolio(pg_session, "ct-held")
    pg_session.add(PaperPosition(
        portfolio_id=p.id, asset_id=asset_id,
        quantity=Decimal("1"), avg_cost=Decimal("100"),
        is_open=True, opened_at=BASE_TS,
    ))
    pg_session.commit()

    decisions = generate_decisions(pg_session, p, AutoTradeConfig(), now=BASE_TS)
    assert all(d.asset_id != asset_id or d.kind == "close_sell" for d in decisions)
    # Only valid close condition: sell rec or max hold; neither applies → empty.
    assert decisions == []


def test_max_open_positions_caps_buys(pg_session: Session) -> None:
    p = create_portfolio(
        pg_session,
        PortfolioCreate(name="ct-cap", starting_cash=Decimal("100000"), max_open_positions=2),
    )
    pg_session.commit()
    # 3 buy recs
    for i, sym in enumerate(["M1", "M2", "M3"]):
        aid = _seed_asset_with_prices(pg_session, sym)
        _seed_recommendation(pg_session, aid, "Buy", Decimal("80"), f"cap{i}")

    decisions = generate_decisions(pg_session, p, AutoTradeConfig(), now=BASE_TS)
    buys = [d for d in decisions if d.kind == "open_buy"]
    assert len(buys) == 2


def test_max_holding_days_forces_sell(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(pg_session, "OLD")
    p = _active_portfolio(pg_session, "ct-old")
    # Position opened 35 days before "now"
    now = BASE_TS + dt.timedelta(days=35)
    pg_session.add(PaperPosition(
        portfolio_id=p.id, asset_id=asset_id,
        quantity=Decimal("2"), avg_cost=Decimal("100"),
        is_open=True, opened_at=BASE_TS,
    ))
    pg_session.commit()

    decisions = generate_decisions(
        pg_session, p, AutoTradeConfig(max_holding_days=30), now=now,
    )
    sells = [d for d in decisions if d.kind == "close_sell"]
    assert len(sells) == 1
    assert "max_holding_days" in sells[0].reason
    assert sells[0].quantity == Decimal("2")


def test_rec_flip_to_sell_triggers_exit(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(pg_session, "FLP")
    p = _active_portfolio(pg_session, "ct-flip")
    pg_session.add(PaperPosition(
        portfolio_id=p.id, asset_id=asset_id,
        quantity=Decimal("3"), avg_cost=Decimal("100"),
        is_open=True, opened_at=BASE_TS + dt.timedelta(days=5),
    ))
    pg_session.commit()
    _seed_recommendation(pg_session, asset_id, "Sell", Decimal("50"), "flip1")

    decisions = generate_decisions(
        pg_session, p, AutoTradeConfig(),
        now=BASE_TS + dt.timedelta(days=10),
    )
    sells = [d for d in decisions if d.kind == "close_sell"]
    assert len(sells) == 1
    assert "flipped to Sell" in sells[0].reason


def test_rec_trim_also_triggers_exit(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(pg_session, "TRM")
    p = _active_portfolio(pg_session, "ct-trim")
    pg_session.add(PaperPosition(
        portfolio_id=p.id, asset_id=asset_id,
        quantity=Decimal("2"), avg_cost=Decimal("100"),
        is_open=True, opened_at=BASE_TS + dt.timedelta(days=5),
    ))
    pg_session.commit()
    _seed_recommendation(pg_session, asset_id, "Trim", Decimal("50"), "trim1")

    decisions = generate_decisions(
        pg_session, p, AutoTradeConfig(),
        now=BASE_TS + dt.timedelta(days=10),
    )
    assert any(d.kind == "close_sell" for d in decisions)


# ---------------------------------------------------------------------------
# Execution path
# ---------------------------------------------------------------------------


def test_auto_trade_portfolio_executes_buy_end_to_end(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(pg_session, "EXE")
    _seed_recommendation(pg_session, asset_id, "Buy", Decimal("75"), "exe1")
    p = _active_portfolio(pg_session, "ct-exe")

    result = auto_trade_portfolio(pg_session, p, AutoTradeConfig(), now=BASE_TS)
    pg_session.commit()

    assert len(result.executed) == 1
    trades = list(pg_session.scalars(
        select(PaperTrade).where(PaperTrade.portfolio_id == p.id)
    ))
    assert len(trades) == 1
    assert trades[0].side == "buy"
    assert trades[0].recommendation_id is not None
    assert "auto_trader" in (trades[0].reason or "")


def test_buy_and_sell_full_round_trip(pg_session: Session) -> None:
    asset_id = _seed_asset_with_prices(
        pg_session, "RND", n_bars=40, open_price=Decimal("100"), step=Decimal("1"),
    )
    # Buy rec is "older"; Sell rec placed AFTER with explicit later timestamp.
    _seed_recommendation(
        pg_session, asset_id, "Buy", Decimal("80"), "rnd1", offset_days_ago=10,
    )
    p = _active_portfolio(pg_session, "ct-rt")

    res_buy = auto_trade_portfolio(pg_session, p, AutoTradeConfig(), now=BASE_TS)
    pg_session.commit()
    assert len(res_buy.executed) == 1

    # Flip recommendation to Sell (offset=0 → clearly newer than Buy@10d ago)
    _seed_recommendation(
        pg_session, asset_id, "Sell", Decimal("50"), "rnd2", offset_days_ago=0,
    )
    res_sell = auto_trade_portfolio(
        pg_session, p, AutoTradeConfig(),
        now=BASE_TS + dt.timedelta(days=5),
    )
    pg_session.commit()
    assert len(res_sell.executed) == 1

    open_pos = list(pg_session.scalars(
        select(PaperPosition).where(
            PaperPosition.portfolio_id == p.id,
            PaperPosition.is_open.is_(True),
        )
    ))
    assert open_pos == []


def _seed_asset_with_future_prices(
    pg_session: Session,
    symbol: str,
    n_bars: int = 10,
    open_price: Decimal = Decimal("100"),
) -> str:
    """Seed a price series starting from `now - 1 day` so real-time jobs can fill."""
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    start = now - dt.timedelta(days=1)
    asset = Asset(symbol=symbol, asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()
    for i in range(n_bars):
        p = open_price
        pg_session.add(PriceBar(
            asset_id=asset.id, timeframe="1d",
            ts=start + dt.timedelta(days=i),
            open=p, high=p + Decimal("0.5"), low=p - Decimal("0.5"),
            close=p, adjusted_close=p, volume=1_000_000, provider="test",
        ))
    pg_session.commit()
    return asset.id


def test_run_paper_trading_job_snapshots_equity(pg_session: Session) -> None:
    asset_id = _seed_asset_with_future_prices(pg_session, "JOB")
    _seed_recommendation(pg_session, asset_id, "Buy", Decimal("70"), "job1")
    _active_portfolio(pg_session, "ct-job")

    import asyncio
    asyncio.run(run_paper_trading())

    from apps.api.src.db.models import PaperEquitySnapshot
    pg_session.expire_all()
    snaps = list(pg_session.scalars(select(PaperEquitySnapshot)))
    assert len(snaps) == 1


def test_run_paper_trading_job_idempotent(pg_session: Session) -> None:
    asset_id = _seed_asset_with_future_prices(pg_session, "IDEM")
    _seed_recommendation(pg_session, asset_id, "Buy", Decimal("75"), "idem1")
    _active_portfolio(pg_session, "ct-idem")

    import asyncio
    asyncio.run(run_paper_trading())
    asyncio.run(run_paper_trading())
    pg_session.expire_all()

    # Same-day equity snapshot upserts → still one row
    from apps.api.src.db.models import PaperEquitySnapshot
    snaps = list(pg_session.scalars(select(PaperEquitySnapshot)))
    assert len(snaps) == 1
    # Second run should skip the buy (already holding → no new rec → no new trade)
    trades = list(pg_session.scalars(select(PaperTrade)))
    assert len(trades) == 1


# ---------------------------------------------------------------------------
# Validation fields on API
# ---------------------------------------------------------------------------


def test_portfolio_detail_includes_validation(pg_session: Session) -> None:
    from fastapi.testclient import TestClient
    from apps.api.src.main import app

    asset_id = _seed_asset_with_prices(
        pg_session, "VAL", n_bars=10,
        open_price=Decimal("100"), step=Decimal("1"),
    )
    p = _active_portfolio(pg_session, "ct-val")

    client = TestClient(app)
    # Snapshot twice at different dates to build a curve → drawdown math
    # runs. First snapshot now, second after manually shifted date.
    from apps.api.src.db.models import PaperEquitySnapshot
    pg_session.add(PaperEquitySnapshot(
        portfolio_id=p.id,
        snapshot_date=BASE_TS,
        cash=Decimal("1200"),
        positions_value=Decimal("0"),
        total_equity=Decimal("1200"),
        unrealized_pnl=Decimal("0"),
        realized_pnl_cumulative=Decimal("0"),
    ))
    pg_session.add(PaperEquitySnapshot(
        portfolio_id=p.id,
        snapshot_date=BASE_TS + dt.timedelta(days=3),
        cash=Decimal("1000"),
        positions_value=Decimal("0"),
        total_equity=Decimal("1000"),
        unrealized_pnl=Decimal("0"),
        realized_pnl_cumulative=Decimal("0"),
    ))
    pg_session.commit()

    resp = client.get(f"/api/paper/portfolios/{p.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "validation" in data
    dd = data["validation"]["drawdown"]
    assert dd["max_drawdown_pct"] is not None
    # (1000 - 1200) / 1200 = -0.1666...
    assert Decimal(dd["max_drawdown_pct"]) < Decimal("0")
    assert dd["max_drawdown_duration_days"] == 3

    # Confidence validation block always present
    assert "confidence_validation" in data["validation"]
    labels = [b["bucket"] for b in data["validation"]["confidence_validation"]]
    assert labels == ["Low (0-30)", "Medium (30-60)", "High (60-100)", "Unknown"]


# ---------------------------------------------------------------------------
# P0-3B — double-fill prevention (in-run dedup + migration 097 index)
# ---------------------------------------------------------------------------


def test_tied_generated_at_recs_emit_single_buy(pg_session: Session) -> None:
    """Two Buy recs for the same asset with IDENTICAL generated_at tie at
    max-ts in _latest_buy_candidates' join — the duplicated candidate list
    must still emit exactly ONE open_buy (pending-buy guard)."""
    asset_id = _seed_asset_with_prices(pg_session, "DUPC")
    ts = dt.datetime(2026, 6, 1, 22, 30, tzinfo=dt.timezone.utc)
    for snap in ("dupc-a", "dupc-b"):
        pg_session.add(Recommendation(
            asset_id=asset_id, action="Buy", conviction=Decimal("80"),
            model_version="0.1.0", snapshot_hash=snap,
            rationale='{"snapshot_hash":"' + snap + '"}',
            generated_at=ts,
        ))
    pg_session.commit()
    p = _active_portfolio(pg_session, "ct-dup-cand")

    skips: list[dict] = []
    decisions = generate_decisions(
        pg_session, p, AutoTradeConfig(), now=BASE_TS, skips_out=skips,
    )
    buys = [d for d in decisions if d.kind == "open_buy"]
    assert len(buys) == 1
    assert buys[0].asset_id == asset_id
    assert any(s["reason"] == "duplicate_candidate_in_run" for s in skips)


def test_duplicate_position_rows_emit_single_sell(pg_session: Session) -> None:
    """Two open position rows for the same asset (the 06-04..06-10 artifact
    shape) + a Sell rec → exactly ONE close_sell decision per run."""
    asset_id = _seed_asset_with_prices(pg_session, "DUPP")
    _seed_recommendation(pg_session, asset_id, "Sell", Decimal("80"), "dupp-s")
    p = _active_portfolio(pg_session, "ct-dup-pos")
    for _ in range(2):
        pg_session.add(PaperPosition(
            portfolio_id=p.id, asset_id=asset_id,
            quantity=Decimal("5"), avg_cost=Decimal("100"),
            is_open=True, opened_at=BASE_TS,
        ))
    pg_session.commit()

    decisions = generate_decisions(pg_session, p, AutoTradeConfig(), now=BASE_TS)
    sells = [d for d in decisions if d.kind == "close_sell"]
    assert len(sells) == 1
    assert sells[0].asset_id == asset_id


def test_single_position_sell_behavior_unchanged(pg_session: Session) -> None:
    """Regression: one open position + Sell rec still emits exactly one
    close_sell with full quantity (pre-P0-3B behavior preserved)."""
    asset_id = _seed_asset_with_prices(pg_session, "SELL1")
    _seed_recommendation(pg_session, asset_id, "Sell", Decimal("80"), "sell1-s")
    p = _active_portfolio(pg_session, "ct-sell-one")
    pg_session.add(PaperPosition(
        portfolio_id=p.id, asset_id=asset_id,
        quantity=Decimal("7"), avg_cost=Decimal("100"),
        is_open=True, opened_at=BASE_TS,
    ))
    pg_session.commit()

    decisions = generate_decisions(pg_session, p, AutoTradeConfig(), now=BASE_TS)
    sells = [d for d in decisions if d.kind == "close_sell"]
    assert len(sells) == 1
    assert sells[0].quantity == Decimal("7")


def _mk_trade(pg_session, p, asset_id, rec_id, *, side="buy",
              fill_ts=None, reason="auto_trader: test fill"):
    from apps.api.src.db.models import PaperTrade as _PT
    t = _PT(
        portfolio_id=p.id, asset_id=asset_id, side=side,
        quantity=Decimal("1"), fill_price=Decimal("100"),
        fill_ts=fill_ts or dt.datetime(2026, 6, 12, tzinfo=dt.timezone.utc),
        submitted_at=dt.datetime(2026, 6, 11, 23, 59, tzinfo=dt.timezone.utc),
        reason=reason, recommendation_id=rec_id,
    )
    pg_session.add(t)
    return t


def test_index_blocks_duplicate_autotrader_fill(pg_session: Session) -> None:
    """Migration 097: second auto_trader fill with the same
    (portfolio, recommendation, side) on/after 2026-06-11 is rejected."""
    from sqlalchemy.exc import IntegrityError

    asset_id = _seed_asset_with_prices(pg_session, "IDX1")
    rec_id = _seed_recommendation(pg_session, asset_id, "Buy", Decimal("80"), "idx1")
    p = _active_portfolio(pg_session, "ct-idx-dup")

    _mk_trade(pg_session, p, asset_id, rec_id)
    pg_session.commit()
    _mk_trade(pg_session, p, asset_id, rec_id)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_index_allows_distinct_recommendation(pg_session: Session) -> None:
    """Re-entry on a NEW recommendation_id is never blocked."""
    asset_id = _seed_asset_with_prices(pg_session, "IDX2")
    rec_a = _seed_recommendation(pg_session, asset_id, "Buy", Decimal("80"), "idx2a")
    rec_b = _seed_recommendation(pg_session, asset_id, "Buy", Decimal("80"), "idx2b")
    p = _active_portfolio(pg_session, "ct-idx-ok")

    _mk_trade(pg_session, p, asset_id, rec_a)
    _mk_trade(pg_session, p, asset_id, rec_b)
    pg_session.commit()  # both insert cleanly


def test_index_ignores_null_rec_and_non_autotrader(pg_session: Session) -> None:
    """NULL recommendation_id and non-auto_trader reasons stay
    unconstrained (manual/replay fills)."""
    asset_id = _seed_asset_with_prices(pg_session, "IDX3")
    rec_id = _seed_recommendation(pg_session, asset_id, "Buy", Decimal("80"), "idx3")
    p = _active_portfolio(pg_session, "ct-idx-null")

    _mk_trade(pg_session, p, asset_id, None)
    _mk_trade(pg_session, p, asset_id, None)
    _mk_trade(pg_session, p, asset_id, rec_id, reason="replay: backfill")
    _mk_trade(pg_session, p, asset_id, rec_id, reason="replay: backfill")
    pg_session.commit()  # all four insert cleanly


def test_index_excludes_pre_20260611_window(pg_session: Session) -> None:
    """Fills inside the corrupted 06-04..06-10 window are NOT constrained
    (repair is P0-3C; the index must not block on legacy duplicates)."""
    asset_id = _seed_asset_with_prices(pg_session, "IDX4")
    rec_id = _seed_recommendation(pg_session, asset_id, "Buy", Decimal("80"), "idx4")
    p = _active_portfolio(pg_session, "ct-idx-old")

    old = dt.datetime(2026, 6, 8, tzinfo=dt.timezone.utc)
    _mk_trade(pg_session, p, asset_id, rec_id, fill_ts=old)
    _mk_trade(pg_session, p, asset_id, rec_id, fill_ts=old)
    pg_session.commit()  # legacy-window duplicates tolerated


def test_execute_decisions_converts_integrity_error_to_rejection(
    pg_session: Session,
) -> None:
    """P0-3B.1 — a migration-097 idempotency violation on one decision is
    contained by the per-decision SAVEPOINT: that decision lands in
    run.rejected, sibling valid trades in the SAME run still commit."""
    from apps.api.src.domain.paper_trading.auto_trader import (
        AutoTradeDecision,
        execute_decisions,
    )

    june = dt.datetime(2026, 6, 12, tzinfo=dt.timezone.utc)

    def _seed_june_asset(symbol: str) -> str:
        asset = Asset(symbol=symbol, asset_class="equity",
                      exchange="NASDAQ", currency="USD")
        pg_session.add(asset)
        pg_session.flush()
        for i in range(5):
            p = Decimal("100")
            pg_session.add(PriceBar(
                asset_id=asset.id, timeframe="1d",
                ts=june + dt.timedelta(days=i),
                open=p, high=p + Decimal("0.5"), low=p - Decimal("0.5"),
                close=p, adjusted_close=p, volume=1_000_000, provider="test",
            ))
        pg_session.commit()
        return asset.id

    a_id = _seed_june_asset("SVPA")
    b_id = _seed_june_asset("SVPB")
    rec_a = _seed_recommendation(pg_session, a_id, "Buy", Decimal("80"), "svp-a")
    rec_b = _seed_recommendation(pg_session, b_id, "Buy", Decimal("80"), "svp-b")
    p = _active_portfolio(pg_session, "ct-savepoint", cash="100000")

    # Pre-existing committed auto_trader fill for (portfolio, rec_a, buy)
    # inside the index window -> the re-execution below must collide.
    _mk_trade(pg_session, p, a_id, rec_a,
              fill_ts=june, reason="auto_trader: prior fill")
    pg_session.commit()

    decisions = [
        AutoTradeDecision(kind="open_buy", asset_id=a_id,
                          recommendation_id=rec_a,
                          usd_amount=Decimal("1000"), reason="dup attempt"),
        AutoTradeDecision(kind="open_buy", asset_id=b_id,
                          recommendation_id=rec_b,
                          usd_amount=Decimal("1000"), reason="valid buy"),
    ]
    run = execute_decisions(
        pg_session, p, decisions,
        submitted_at=dt.datetime(2026, 6, 11, 12, tzinfo=dt.timezone.utc),
    )
    pg_session.commit()  # session must still be usable after the violation

    assert len(run.executed) == 1
    assert len(run.rejected) == 1
    assert "idempotency_unique_violation" in run.rejected[0]["reason"]
    trades_a = pg_session.scalars(
        select(PaperTrade).where(PaperTrade.asset_id == a_id)
    ).all()
    trades_b = pg_session.scalars(
        select(PaperTrade).where(PaperTrade.asset_id == b_id)
    ).all()
    assert len(trades_a) == 1   # only the pre-existing fill; dup blocked
    assert len(trades_b) == 1   # sibling valid trade survived


# ---------------------------------------------------------------------------
# P0-3B.3 — engine-sell-day idempotency (migration 098)
# ---------------------------------------------------------------------------


def test_engine_sell_index_blocks_same_day_duplicate(pg_session: Session) -> None:
    """Second engine sell with the same (portfolio, asset, fill_ts) is
    rejected — exit-cycle reasons carry no recommendation_id, so this is
    the only guard for that path."""
    from sqlalchemy.exc import IntegrityError

    asset_id = _seed_asset_with_prices(pg_session, "XSD1")
    p = _active_portfolio(pg_session, "ct-xsell-dup")
    june = dt.datetime(2026, 6, 12, tzinfo=dt.timezone.utc)

    _mk_trade(pg_session, p, asset_id, None, side="sell",
              fill_ts=june, reason="exit_cycle: take_profit(0.09 >= 0.08)")
    pg_session.commit()
    _mk_trade(pg_session, p, asset_id, None, side="sell",
              fill_ts=june, reason="exit_cycle: take_profit(0.09 >= 0.08)")
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_engine_sell_index_blocks_autotrader_norec_dup(pg_session: Session) -> None:
    """auto_trader max_holding sells (recommendation_id NULL — invisible
    to migration 097) are covered by the 098 sell-day index."""
    from sqlalchemy.exc import IntegrityError

    asset_id = _seed_asset_with_prices(pg_session, "XSD2")
    p = _active_portfolio(pg_session, "ct-xsell-at")
    june = dt.datetime(2026, 6, 12, tzinfo=dt.timezone.utc)

    _mk_trade(pg_session, p, asset_id, None, side="sell",
              fill_ts=june, reason="auto_trader: max_holding_days=10 exceeded (held 11d)")
    pg_session.commit()
    _mk_trade(pg_session, p, asset_id, None, side="sell",
              fill_ts=june, reason="auto_trader: max_holding_days=10 exceeded (held 11d)")
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_engine_sell_index_allows_later_exit(pg_session: Session) -> None:
    """Re-exit after a re-entry fills on a different bar -> different
    fill_ts -> allowed."""
    asset_id = _seed_asset_with_prices(pg_session, "XSD3")
    p = _active_portfolio(pg_session, "ct-xsell-later")
    d1 = dt.datetime(2026, 6, 12, tzinfo=dt.timezone.utc)
    d2 = dt.datetime(2026, 6, 19, tzinfo=dt.timezone.utc)

    _mk_trade(pg_session, p, asset_id, None, side="sell",
              fill_ts=d1, reason="exit_cycle: stop_loss(-0.05 <= -0.04)")
    _mk_trade(pg_session, p, asset_id, None, side="sell",
              fill_ts=d2, reason="exit_cycle: stop_loss(-0.06 <= -0.04)")
    pg_session.commit()  # both insert cleanly


def test_engine_sell_index_ignores_manual_and_legacy(pg_session: Session) -> None:
    """Manual/replay sell reasons stay unconstrained; legacy-window
    (06-04..06-10) engine sell duplicates stay tolerated until repair."""
    asset_id = _seed_asset_with_prices(pg_session, "XSD4")
    p = _active_portfolio(pg_session, "ct-xsell-ok")
    june = dt.datetime(2026, 6, 12, tzinfo=dt.timezone.utc)
    legacy = dt.datetime(2026, 6, 8, tzinfo=dt.timezone.utc)

    # manual reason, duplicated on the same day -> not constrained
    _mk_trade(pg_session, p, asset_id, None, side="sell",
              fill_ts=june, reason="manual: operator close")
    _mk_trade(pg_session, p, asset_id, None, side="sell",
              fill_ts=june, reason="manual: operator close")
    # engine reason inside the corrupted legacy window -> not constrained
    _mk_trade(pg_session, p, asset_id, None, side="sell",
              fill_ts=legacy, reason="exit_cycle: max_hold(12d >= 10d)")
    _mk_trade(pg_session, p, asset_id, None, side="sell",
              fill_ts=legacy, reason="exit_cycle: max_hold(12d >= 10d)")
    pg_session.commit()  # all four insert cleanly
