"""QW3.1 — recursive (repaint) detector for options feature rows.

Recursive/repaint bias = the feature row computed for as_of=T changes when
data for strictly-later dates (T+1..T+N) is appended. The options feature
engine reads its chain day-bounded (snapshot_at_utc::date = as_of_date), so
the as_of=T row must be recompute-stable.

Two checks:
  1. recompute-stability — compute the T row, append later-dated chain, recompute
     the T row, assert identical (Decimal-tolerant; flags order-insensitive).
  2. reader as_of contract — the engine hands injected history readers the
     decision date (T), so a reader that bounds on its as_of arg gets the
     correct cutoff. (Production wires NO history fns — defaults None — so there
     is no live recursive-history surface today; this guards future wiring.)

Detector only — no engine/production change.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db.options_models import OptionsChainSnapshot
from apps.api.src.options.features.engine import compute_features_for

pytestmark = pytest.mark.integration

T = dt.date(2026, 6, 15)
UND = "SPY"
EXP = dt.date(2026, 7, 18)
SPOT = Decimal("440")

_NUMERIC_FIELDS = (
    "atm_iv", "iv_rank_252d", "iv_percentile_252d", "realized_vol_20d",
    "vrp_30d", "skew_25d", "term_structure_30_90", "put_call_volume_ratio",
    "put_call_oi_ratio", "unusual_call_volume_z", "unusual_put_volume_z",
    "gamma_exposure_proxy", "call_wall_strike", "put_wall_strike",
)


def _seed_chain(pg_session: Session, on_date: dt.date,
                strikes=(435, 440, 445)) -> None:
    snap = dt.datetime(on_date.year, on_date.month, on_date.day, 14, 0,
                       tzinfo=dt.timezone.utc)
    for k in strikes:
        for ot in ("PUT", "CALL"):
            pg_session.add(OptionsChainSnapshot(
                snapshot_at_utc=snap, underlying=UND, expiry=EXP,
                strike=Decimal(str(k)), option_type=ot,
                option_symbol=f"{UND}260718{ot[0]}{int(k * 1000):08d}",
                bid=Decimal("1.10"), ask=Decimal("1.30"), mid=Decimal("1.20"),
                last=Decimal("1.20"), volume=500, open_interest=2000,
                delta=Decimal("-0.30") if ot == "PUT" else Decimal("0.30"),
                gamma=Decimal("0.02"), theta=Decimal("-0.05"),
                vega=Decimal("0.10"), iv=Decimal("0.20"),
                quote_age_seconds=2, provider="qw3-test",
            ))


def _read_feature_row(pg_session: Session, as_of: dt.date):
    return pg_session.execute(text(
        """
        SELECT atm_iv, iv_rank_252d, iv_percentile_252d, realized_vol_20d,
               vrp_30d, skew_25d, term_structure_30_90, put_call_volume_ratio,
               put_call_oi_ratio, unusual_call_volume_z, unusual_put_volume_z,
               gamma_exposure_proxy, call_wall_strike, put_wall_strike,
               data_quality_flags
          FROM options_feature_daily
         WHERE as_of_date = :d AND underlying = :u
        """
    ), {"d": as_of, "u": UND}).mappings().first()


def _assert_rows_equal(a, b, *, tol=Decimal("0.000001")) -> None:
    assert a is not None and b is not None
    for f in _NUMERIC_FIELDS:
        av, bv = a[f], b[f]
        if av is None or bv is None:
            assert av is None and bv is None, f"{f}: NULL drift {av!r} vs {bv!r}"
        else:
            assert abs(Decimal(str(av)) - Decimal(str(bv))) <= tol, \
                f"{f}: repaint {av!r} -> {bv!r}"
    # data_quality_flags order-insensitive
    assert set(a["data_quality_flags"] or []) == set(b["data_quality_flags"] or []), \
        f"flags drift {a['data_quality_flags']} vs {b['data_quality_flags']}"


def test_options_feature_row_is_recompute_stable(pg_session: Session, pg_engine) -> None:
    """The as_of=T feature row must not change when strictly-later chain data
    is appended (no repaint)."""
    SF = sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)
    _seed_chain(pg_session, T)
    pg_session.commit()

    compute_features_for(underlying=UND, as_of_date=T, spot=SPOT, session_factory=SF)
    v1 = _read_feature_row(pg_session, T)

    # Append STRICTLY-LATER dates only (never a same-day refresh of T).
    _seed_chain(pg_session, T + dt.timedelta(days=1))
    _seed_chain(pg_session, T + dt.timedelta(days=2))
    pg_session.commit()

    compute_features_for(underlying=UND, as_of_date=T, spot=SPOT, session_factory=SF)
    v2 = _read_feature_row(pg_session, T)

    _assert_rows_equal(v1, v2)


def test_engine_hands_readers_the_decision_date(pg_session: Session, pg_engine) -> None:
    """Any injected history reader receives as_of=T, so a reader that bounds
    on its as_of argument gets the correct cutoff (future-proofs wiring)."""
    SF = sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)
    _seed_chain(pg_session, T)
    pg_session.commit()

    seen: dict[str, dt.date] = {}

    def spy_price(sym: str, as_of: dt.date):
        seen["price"] = as_of
        return [Decimal("100")] * 22

    def spy_vol(sym: str, as_of: dt.date):
        seen["vol"] = as_of
        return ([200] * 10, [300] * 10)

    compute_features_for(
        underlying=UND, as_of_date=T, spot=SPOT,
        price_history_fn=spy_price, volume_history_fn=spy_vol,
        session_factory=SF,
    )
    assert seen.get("price") == T
    assert seen.get("vol") == T
