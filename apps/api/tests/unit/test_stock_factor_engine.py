"""Unit tests: stock_factor_engine pure functions + cross-section."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.api.src.domain.features.stock_factor_engine import (
    FEATURE_SET,
    FEATURE_SET_HASH,
    BarView,
    MIN_BARS_ENOUGH,
    RawFeatures,
    _is_stale,
    atr,
    avg_dollar_volume,
    compute_raw_features,
    finalize_snapshots,
    percentile_rank_within_group,
    sma,
    zscore_list,
)


BASE_TS = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)


def _bar_series(closes: list[float], vol: int | None = 1_000_000) -> list[BarView]:
    return [
        BarView(
            ts=BASE_TS + dt.timedelta(days=i),
            open=Decimal(str(c)),
            high=Decimal(str(c * 1.01)),
            low=Decimal(str(c * 0.99)),
            close=Decimal(str(c)),
            volume=vol,
        )
        for i, c in enumerate(closes)
    ]


# ---------------------------------------------------------------------------
# Feature-set hash contract
# ---------------------------------------------------------------------------


def test_feature_set_hash_is_stable_len16() -> None:
    assert len(FEATURE_SET_HASH) == 16
    assert len(FEATURE_SET) == 8


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------


def test_sma_basic() -> None:
    prices = [Decimal(str(v)) for v in range(1, 11)]  # 1..10
    assert sma(prices, 5) == 8.0     # (6+7+8+9+10)/5
    assert sma(prices, 10) == 5.5


def test_sma_returns_none_when_short() -> None:
    assert sma([Decimal("1"), Decimal("2")], 5) is None


def test_atr_positive_on_nonflat_bars() -> None:
    bars = _bar_series([100.0 + i for i in range(20)])
    a = atr(bars, period=14)
    assert a is not None
    assert a > 0


def test_atr_returns_none_when_short() -> None:
    assert atr(_bar_series([100.0] * 14), period=14) is None


def test_avg_dollar_volume_basic() -> None:
    bars = _bar_series([100.0] * 20, vol=1_000)
    adv = avg_dollar_volume(bars, n=20)
    assert adv == 100.0 * 1_000


def test_avg_dollar_volume_none_on_short() -> None:
    assert avg_dollar_volume(_bar_series([100.0] * 10), n=20) is None


def test_avg_dollar_volume_skips_nonpositive() -> None:
    # All volumes <=0 → None
    bars = _bar_series([100.0] * 20, vol=0)
    assert avg_dollar_volume(bars, n=20) is None


# ---------------------------------------------------------------------------
# zscore_list
# ---------------------------------------------------------------------------


def test_zscore_list_zero_mean_unit_std() -> None:
    out = zscore_list([1.0, 2.0, 3.0, 4.0, 5.0])
    assert out is not None
    assert abs(out[2]) < 1e-9        # middle value is 0
    assert out[0] < 0
    assert out[-1] > 0


def test_zscore_list_preserves_nones() -> None:
    out = zscore_list([None, 1.0, 2.0, None, 3.0])
    assert out[0] is None
    assert out[3] is None


def test_zscore_list_single_value_returns_all_none() -> None:
    assert zscore_list([5.0]) == [None]


def test_zscore_list_zero_std_returns_zeros() -> None:
    out = zscore_list([2.0, 2.0, 2.0])
    assert out == [0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# percentile_rank_within_group
# ---------------------------------------------------------------------------


def test_percentile_rank_mid() -> None:
    out = percentile_rank_within_group([1.0, 2.0, 3.0, 4.0, 5.0])
    assert out[0] == 0.1           # 0 strictly less, 1 equal, / 5
    assert out[-1] == 0.9
    assert out[2] == 0.5


def test_percentile_rank_single_returns_half() -> None:
    assert percentile_rank_within_group([7.0]) == [0.5]


def test_percentile_rank_preserves_nones() -> None:
    out = percentile_rank_within_group([None, 1.0, 2.0])
    assert out[0] is None
    assert out[1] < out[2]


def test_percentile_rank_all_none_returns_all_none() -> None:
    assert percentile_rank_within_group([None, None]) == [None, None]


# ---------------------------------------------------------------------------
# _is_stale
# ---------------------------------------------------------------------------


def test_is_stale_when_latest_older_than_5_days() -> None:
    latest = dt.datetime(2026, 4, 10, tzinfo=dt.timezone.utc)
    assert _is_stale(latest, dt.date(2026, 4, 17)) is True


def test_is_stale_false_when_within_5_days() -> None:
    latest = dt.datetime(2026, 4, 15, tzinfo=dt.timezone.utc)
    assert _is_stale(latest, dt.date(2026, 4, 17)) is False


def test_is_stale_false_when_missing_latest() -> None:
    assert _is_stale(None, dt.date(2026, 4, 17)) is False


# ---------------------------------------------------------------------------
# compute_raw_features
# ---------------------------------------------------------------------------


def _rising_series(n: int, start: float = 100.0, step: float = 0.2) -> list[BarView]:
    return _bar_series([start + i * step for i in range(n)])


def test_raw_features_happy_path_with_enough_history() -> None:
    asset = _rising_series(MIN_BARS_ENOUGH + 10, step=0.3)
    spy = _rising_series(MIN_BARS_ENOUGH + 10, step=0.1)
    r = compute_raw_features("a1", asset, spy, dt.date(2025, 8, 1))
    assert r.enough_data is True
    assert r.stale_data is False          # latest bar is 209 days past 2025-01-01 start
    assert r.residual_return_20d is not None
    assert r.residual_return_60d is not None
    assert r.trend_strength_20d is not None
    assert r.price_vs_200sma is not None
    assert r.atr_percent_14 is not None
    assert r.avg_dollar_volume_20d is not None
    assert r.earnings_proximity_days is None  # not yet wired


def test_raw_features_marks_enough_data_false_when_short() -> None:
    asset = _rising_series(100)
    spy = _rising_series(100)
    r = compute_raw_features("a1", asset, spy, dt.date(2025, 5, 1))
    assert r.enough_data is False
    assert r.price_vs_200sma is None      # SMA200 needs 200 bars


def test_raw_features_empty_bars_all_none() -> None:
    r = compute_raw_features("a1", [], [], dt.date(2026, 4, 19))
    assert r.enough_data is False
    assert r.stale_data is False
    assert r.residual_return_20d is None
    assert r.trend_strength_20d is None


def test_raw_features_stale_when_latest_bar_old() -> None:
    # Bars end at day 0; as_of far in future → stale
    asset = _rising_series(MIN_BARS_ENOUGH + 5)
    spy = _rising_series(MIN_BARS_ENOUGH + 5)
    latest_bar_date = asset[-1].ts.date()
    as_of = latest_bar_date + dt.timedelta(days=20)
    r = compute_raw_features("a1", asset, spy, as_of)
    assert r.stale_data is True


def test_raw_residual_return_sign_matches_outperformance() -> None:
    # Asset returns 20% over 20 days, SPY flat → residual_20d positive
    asset = _bar_series([100.0] * 20 + [120.0])
    spy = _bar_series([100.0] * 21)
    r = compute_raw_features("a1", asset, spy, dt.date(2026, 4, 19))
    assert r.residual_return_20d is not None
    assert r.residual_return_20d > 0


# ---------------------------------------------------------------------------
# finalize_snapshots — cross-section transforms
# ---------------------------------------------------------------------------


def _raw(
    asset_id: str, ret60: float | None, ret20: float | None = None,
    enough: bool = True, stale: bool = False,
) -> RawFeatures:
    return RawFeatures(
        asset_id=asset_id,
        enough_data=enough,
        stale_data=stale,
        residual_return_20d=ret20,
        residual_return_60d=ret60,
        return_60d=ret60,
        trend_strength_20d=0.5,
        price_vs_200sma=0.02,
        atr_percent_14=0.015,
        avg_dollar_volume_20d=1_000_000.0,
    )


def test_finalize_zscores_eligible_cohort() -> None:
    raws = [
        _raw("a", ret60=0.01, ret20=0.01),
        _raw("b", ret60=0.05, ret20=0.05),
        _raw("c", ret60=0.09, ret20=0.09),
    ]
    sectors = {"a": "equity", "b": "equity", "c": "equity"}
    rows = finalize_snapshots(raws, sectors, dt.date(2026, 4, 19))
    by_id = {r.asset_id: r for r in rows}
    assert by_id["a"].residual_momentum_60d < by_id["c"].residual_momentum_60d
    # Mean ~0 after z-score
    avg = sum(float(r.residual_momentum_60d) for r in rows) / 3
    assert abs(avg) < 1e-6


def test_finalize_excludes_ineligible_from_cross_section() -> None:
    raws = [
        _raw("a", ret60=0.01, ret20=0.01),
        _raw("b", ret60=0.05, ret20=0.05),
        _raw("stale", ret60=0.99, ret20=0.99, stale=True),
    ]
    sectors = {"a": "equity", "b": "equity", "stale": "equity"}
    rows = finalize_snapshots(raws, sectors, dt.date(2026, 4, 19))
    by_id = {r.asset_id: r for r in rows}
    # Stale row must have NULL z-scores despite having raw values
    assert by_id["stale"].residual_momentum_60d is None
    assert by_id["stale"].residual_momentum_20d is None
    assert by_id["stale"].sector_relative_rank is None
    # Eligible rows still get z-scores
    assert by_id["a"].residual_momentum_60d is not None


def test_finalize_sector_rank_within_bucket() -> None:
    raws = [
        _raw("eq1", ret60=0.01),
        _raw("eq2", ret60=0.05),
        _raw("eq3", ret60=0.09),
        _raw("etf1", ret60=-0.02),
        _raw("etf2", ret60=0.03),
    ]
    sectors = {"eq1": "equity", "eq2": "equity", "eq3": "equity",
               "etf1": "etf", "etf2": "etf"}
    rows = finalize_snapshots(raws, sectors, dt.date(2026, 4, 19))
    by_id = {r.asset_id: r for r in rows}
    # Within equity bucket, eq3 is the top → rank highest
    assert by_id["eq3"].sector_relative_rank > by_id["eq1"].sector_relative_rank
    # Within etf bucket, etf2 is top of 2 → rank > 0.5
    assert by_id["etf2"].sector_relative_rank > by_id["etf1"].sector_relative_rank


def test_finalize_preserves_raw_fields_even_when_ineligible() -> None:
    raws = [_raw("a", ret60=0.01, enough=False)]
    rows = finalize_snapshots(raws, {"a": "equity"}, dt.date(2026, 4, 19))
    r = rows[0]
    assert r.enough_data is False
    assert r.trend_strength_20d is not None
    assert r.residual_momentum_20d is None       # cross-section fields NULL
    assert r.sector_relative_rank is None


def test_finalize_empty_universe_returns_empty() -> None:
    assert finalize_snapshots([], {}, dt.date(2026, 4, 19)) == []


def test_finalize_single_asset_gets_mid_rank_and_zero_z() -> None:
    raws = [_raw("solo", ret60=0.05, ret20=0.05)]
    rows = finalize_snapshots(raws, {"solo": "equity"}, dt.date(2026, 4, 19))
    r = rows[0]
    # Only 1 value → z-score undefined (None) per zscore_list contract
    assert r.residual_momentum_60d is None
    # Sector rank defaults to 0.5 (median) for single-member group
    assert r.sector_relative_rank == Decimal("0.5")
