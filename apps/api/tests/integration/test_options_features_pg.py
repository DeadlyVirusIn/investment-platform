"""Phase 11D integration test — feature engine end-to-end against Postgres.

Verifies:
  * compute_features_for reads options_chain_snapshot, applies the
    liquidity filter, computes features, UPSERTs options_feature_daily
  * Re-running the engine for the same (as_of_date, underlying) is a
    no-op-on-key (single row remains, columns updated)
  * Missing inputs (no spot, no history) → NULLs + data_quality_flags
    populated, no fabricated values
  * Empty chain → row with NO_QUOTES flag, all features NULL
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db.options_models import (  # noqa: F401 — register on Base
    OptionsChainSnapshot,
    OptionsFeatureDaily,
)
from apps.api.src.options.features.engine import compute_features_for


pytestmark = pytest.mark.integration


@pytest.fixture
def session_factory(pg_engine):
    return sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)


def _insert_chain_row(
    pg_session,
    *,
    underlying: str = "SPY",
    snapshot_at: dt.datetime,
    expiry: dt.date,
    strike: float,
    option_type: str,
    bid: float = 1.50,
    ask: float = 1.55,
    volume: int = 100,
    open_interest: int = 1000,
    delta: float | None = -0.20,
    gamma: float | None = 0.02,
    iv: float | None = 0.20,
    quote_age_seconds: int = 2,
) -> None:
    pg_session.execute(text(
        """
        INSERT INTO options_chain_snapshot
          (snapshot_at_utc, underlying, expiry, strike, option_type,
           option_symbol, bid, ask, mid, last,
           volume, open_interest,
           delta, gamma, theta, vega, iv,
           quote_age_seconds, provider, provider_version)
        VALUES
          (:snapshot_at_utc, :underlying, :expiry, :strike, :option_type,
           :option_symbol, :bid, :ask, :mid, :last,
           :volume, :open_interest,
           :delta, :gamma, :theta, :vega, :iv,
           :quote_age_seconds, :provider, :provider_version)
        """
    ), {
        "snapshot_at_utc": snapshot_at,
        "underlying": underlying,
        "expiry": expiry,
        "strike": Decimal(str(strike)),
        "option_type": option_type,
        "option_symbol": f"{underlying}{expiry.strftime('%y%m%d')}{option_type[0]}{int(strike*1000):08d}",
        "bid": Decimal(str(bid)),
        "ask": Decimal(str(ask)),
        "mid": Decimal(str((bid + ask) / 2)),
        "last": Decimal(str(bid)),
        "volume": volume, "open_interest": open_interest,
        "delta": Decimal(str(delta)) if delta is not None else None,
        "gamma": Decimal(str(gamma)) if gamma is not None else None,
        "theta": Decimal("-0.05"),
        "vega": Decimal("0.10"),
        "iv": Decimal(str(iv)) if iv is not None else None,
        "quote_age_seconds": quote_age_seconds,
        "provider": "thetadata",
        "provider_version": "rest-v1",
    })
    pg_session.commit()


def _seed_iron_condor_chain(pg_session, as_of_date, underlying="SPY", spot=450.0):
    snap = dt.datetime.combine(
        as_of_date, dt.time(14, 0, tzinfo=dt.timezone.utc),
    )
    e30 = as_of_date + dt.timedelta(days=30)
    e90 = as_of_date + dt.timedelta(days=90)
    rows = [
        # 30d
        dict(strike=spot,       option_type="CALL", expiry=e30, delta=0.50, iv=0.20, open_interest=2000),
        dict(strike=spot + 15,  option_type="CALL", expiry=e30, delta=0.25, iv=0.18, open_interest=500),
        dict(strike=spot - 15,  option_type="PUT",  expiry=e30, delta=-0.25, iv=0.28, open_interest=1500),
        dict(strike=spot,       option_type="PUT",  expiry=e30, delta=-0.50, iv=0.22, open_interest=2500),
        # 90d
        dict(strike=spot,       option_type="CALL", expiry=e90, delta=0.50, iv=0.24, open_interest=600),
        dict(strike=spot,       option_type="PUT",  expiry=e90, delta=-0.50, iv=0.26, open_interest=550),
    ]
    for r in rows:
        _insert_chain_row(
            pg_session, underlying=underlying, snapshot_at=snap, **r,
        )


# ===========================================================================
# Happy path
# ===========================================================================

def test_compute_features_inserts_one_row(pg_session, session_factory):
    as_of = dt.date(2026, 5, 18)
    _seed_iron_condor_chain(pg_session, as_of)

    summary = compute_features_for(
        underlying="SPY",
        as_of_date=as_of,
        spot=Decimal("450"),
        iv_history=[Decimal(str(x / 100)) for x in range(15, 50)],
        price_history_fn=lambda sym, d: [Decimal("100")] * 22,
        volume_history_fn=lambda sym, d: ([200] * 10, [300] * 10),
        session_factory=session_factory,
    )
    assert summary.upserted is True
    assert summary.n_chain_rows == 6
    assert summary.n_accepted == 6

    rows = pg_session.execute(text(
        "SELECT as_of_date, underlying, atm_iv, "
        "       skew_25d, term_structure_30_90, "
        "       call_wall_strike, put_wall_strike, "
        "       data_quality_flags "
        "FROM options_feature_daily"
    )).all()
    assert len(rows) == 1
    r = rows[0]
    assert r.as_of_date == as_of
    assert r.underlying == "SPY"
    assert r.atm_iv == Decimal("0.200000")
    assert r.skew_25d == Decimal("0.100000")     # 0.28 − 0.18
    assert r.term_structure_30_90 is not None
    assert r.call_wall_strike == Decimal("450.0000")
    assert r.put_wall_strike == Decimal("450.0000")
    assert r.data_quality_flags == []


# ===========================================================================
# Idempotency — re-run upserts, single row remains
# ===========================================================================

def test_compute_features_is_idempotent(pg_session, session_factory):
    as_of = dt.date(2026, 5, 18)
    _seed_iron_condor_chain(pg_session, as_of)

    for _ in range(3):
        compute_features_for(
            underlying="SPY",
            as_of_date=as_of,
            spot=Decimal("450"),
            iv_history=[Decimal(str(x / 100)) for x in range(15, 50)],
            price_history_fn=lambda sym, d: [Decimal("100")] * 22,
            volume_history_fn=lambda sym, d: ([200] * 10, [300] * 10),
            session_factory=session_factory,
        )

    n = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_feature_daily "
        "WHERE underlying='SPY' AND as_of_date = :d"
    ), {"d": as_of}).scalar_one()
    assert n == 1


# ===========================================================================
# Missing inputs → NULLs + flags
# ===========================================================================

def test_compute_features_no_history_flags_populated(
    pg_session, session_factory,
):
    as_of = dt.date(2026, 5, 18)
    _seed_iron_condor_chain(pg_session, as_of)

    compute_features_for(
        underlying="SPY",
        as_of_date=as_of,
        spot=Decimal("450"),
        iv_history=None,
        price_history_fn=None,
        volume_history_fn=None,
        session_factory=session_factory,
    )
    r = pg_session.execute(text(
        "SELECT iv_rank_252d, iv_percentile_252d, realized_vol_20d, vrp_30d, "
        "       unusual_call_volume_z, unusual_put_volume_z, "
        "       data_quality_flags "
        "FROM options_feature_daily WHERE underlying='SPY'"
    )).one()
    assert r.iv_rank_252d is None
    assert r.iv_percentile_252d is None
    assert r.realized_vol_20d is None
    assert r.vrp_30d is None
    assert r.unusual_call_volume_z is None
    assert r.unusual_put_volume_z is None
    flags = r.data_quality_flags
    assert "INSUFFICIENT_IV_HISTORY" in flags
    assert "NO_PRICE_HISTORY" in flags
    assert "INSUFFICIENT_VOLUME_HISTORY" in flags


def test_compute_features_no_spot_flags_no_atm(pg_session, session_factory):
    as_of = dt.date(2026, 5, 18)
    _seed_iron_condor_chain(pg_session, as_of)
    compute_features_for(
        underlying="SPY",
        as_of_date=as_of,
        spot=None,                    # ← deliberately missing
        iv_history=[Decimal(str(x / 100)) for x in range(15, 50)],
        price_history_fn=lambda s, d: [Decimal("100")] * 22,
        volume_history_fn=lambda s, d: ([200] * 10, [300] * 10),
        session_factory=session_factory,
    )
    r = pg_session.execute(text(
        "SELECT atm_iv, term_structure_30_90, data_quality_flags "
        "FROM options_feature_daily"
    )).one()
    assert r.atm_iv is None
    assert r.term_structure_30_90 is None
    assert "NO_SPOT" in r.data_quality_flags


# ===========================================================================
# Empty chain — write NULL row + NO_QUOTES flag (do NOT silently skip)
# ===========================================================================

def test_compute_features_empty_chain_writes_no_quotes_row(
    pg_session, session_factory,
):
    as_of = dt.date(2026, 5, 18)
    # Seed nothing
    summary = compute_features_for(
        underlying="SPY",
        as_of_date=as_of,
        spot=Decimal("450"),
        session_factory=session_factory,
    )
    assert summary.n_chain_rows == 0
    assert summary.n_accepted == 0
    r = pg_session.execute(text(
        "SELECT atm_iv, put_call_volume_ratio, data_quality_flags "
        "FROM options_feature_daily"
    )).one()
    assert r.atm_iv is None
    assert r.put_call_volume_ratio is None
    assert "NO_QUOTES" in r.data_quality_flags


# ===========================================================================
# Liquidity filter is re-applied — wide-spread rows excluded from features
# ===========================================================================

def test_compute_features_excludes_filter_rejected_rows(
    pg_session, session_factory,
):
    as_of = dt.date(2026, 5, 18)
    snap = dt.datetime.combine(
        as_of, dt.time(14, 0, tzinfo=dt.timezone.utc),
    )
    e30 = as_of + dt.timedelta(days=30)
    # One clean call, one wide-spread call (>$0.10)
    _insert_chain_row(
        pg_session, snapshot_at=snap, expiry=e30, strike=450,
        option_type="CALL", bid=1.50, ask=1.55,
        delta=0.50, iv=0.20, open_interest=1000,
    )
    _insert_chain_row(
        pg_session, snapshot_at=snap, expiry=e30, strike=460,
        option_type="CALL", bid=1.50, ask=2.00,    # spread = 0.50
        delta=0.25, iv=0.18, open_interest=500,
    )
    summary = compute_features_for(
        underlying="SPY",
        as_of_date=as_of,
        spot=Decimal("450"),
        session_factory=session_factory,
    )
    assert summary.n_chain_rows == 2
    assert summary.n_accepted == 1
