"""Phase 11D unit tests — pure feature functions + builder.

Covers:
  * Per-feature deterministic compute paths
  * Missing-data → None + flag (NEVER fabricated values)
  * Skew / term-structure / wall-strike / GEX correctness
  * `build_feature_row` aggregates flags, dedups, never returns NaN
  * Boundary grep — no V2 / equity / strategy imports
"""

from __future__ import annotations

import datetime as dt
import importlib
import math
import re
from decimal import Decimal
from pathlib import Path

import pytest

from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.features import compute as F
from apps.api.src.options.features.engine import build_feature_row


# ---------------------------------------------------------------------------
# Quote factory
# ---------------------------------------------------------------------------

def _q(
    *,
    option_type: str = "PUT",
    strike: float = 440.0,
    expiry: dt.date | None = None,
    bid: float | None = 1.50,
    ask: float | None = 1.55,
    volume: int = 100,
    open_interest: int = 1000,
    delta: float | None = -0.20,
    gamma: float | None = 0.02,
    iv: float | None = 0.20,
    snapshot_at_utc: dt.datetime | None = None,
) -> OptionChainQuote:
    expiry = expiry or dt.date(2026, 6, 17)
    snapshot_at_utc = snapshot_at_utc or dt.datetime(
        2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc,
    )
    mid = (bid + ask) / 2 if (bid is not None and ask is not None) else None
    return OptionChainQuote(
        snapshot_at_utc=snapshot_at_utc,
        underlying="SPY",
        expiry=expiry,
        strike=Decimal(str(strike)),
        option_type=option_type,
        option_symbol=f"SPY{expiry.strftime('%y%m%d')}{option_type[0]}{int(strike*1000):08d}",
        bid=Decimal(str(bid)) if bid is not None else None,
        ask=Decimal(str(ask)) if ask is not None else None,
        mid=Decimal(str(mid)) if mid is not None else None,
        last=None,
        volume=volume,
        open_interest=open_interest,
        delta=Decimal(str(delta)) if delta is not None else None,
        gamma=Decimal(str(gamma)) if gamma is not None else None,
        theta=Decimal("-0.05"),
        vega=Decimal("0.10"),
        iv=Decimal(str(iv)) if iv is not None else None,
        quote_age_seconds=2,
        provider="thetadata",
    )


# ===========================================================================
# Put/Call ratios
# ===========================================================================

def test_pcr_volume_basic_ratio():
    quotes = [
        _q(option_type="CALL", strike=460, volume=100),
        _q(option_type="PUT",  strike=440, volume=200),
    ]
    out = F.put_call_volume_ratio(quotes)
    assert out.value == Decimal("2")
    assert out.flags == ()


def test_pcr_oi_basic_ratio():
    quotes = [
        _q(option_type="CALL", strike=460, open_interest=500),
        _q(option_type="PUT",  strike=440, open_interest=1500),
    ]
    out = F.put_call_oi_ratio(quotes)
    assert out.value == Decimal("3")


def test_pcr_no_quotes_flag():
    out = F.put_call_volume_ratio([])
    assert out.value is None
    assert F.FLAG_NO_QUOTES in out.flags


def test_pcr_zero_call_volume_returns_none_with_flag():
    quotes = [
        _q(option_type="CALL", strike=460, volume=0),
        _q(option_type="PUT",  strike=440, volume=200),
    ]
    out = F.put_call_volume_ratio(quotes)
    assert out.value is None
    assert F.FLAG_NO_VOLUME in out.flags


# ===========================================================================
# ATM IV
# ===========================================================================

def test_atm_iv_picks_30d_expiry_and_atm_strike():
    as_of = dt.date(2026, 5, 18)
    spot = Decimal("450")
    e30 = as_of + dt.timedelta(days=30)
    e60 = as_of + dt.timedelta(days=60)
    quotes = [
        _q(option_type="CALL", strike=440, expiry=e30, iv=0.18),
        _q(option_type="CALL", strike=450, expiry=e30, iv=0.20),    # ATM
        _q(option_type="CALL", strike=460, expiry=e30, iv=0.22),
        _q(option_type="CALL", strike=450, expiry=e60, iv=0.25),
    ]
    out = F.atm_iv(quotes, as_of=as_of, spot=spot)
    assert out.value == Decimal("0.20")
    assert out.flags == ()


def test_atm_iv_no_spot_flag():
    out = F.atm_iv([_q()], as_of=dt.date(2026, 5, 18), spot=None)
    assert out.value is None
    assert F.FLAG_NO_SPOT in out.flags


# ===========================================================================
# IV rank + percentile
# ===========================================================================

def test_iv_rank_simple_min_max_normalization():
    history = [Decimal(str(x / 100)) for x in range(10, 40)]   # 0.10..0.39
    out = F.iv_rank(Decimal("0.25"), history)
    # IVR = (0.25 − 0.10) / (0.39 − 0.10) ≈ 0.5172
    assert out.value is not None
    assert abs(float(out.value) - (0.15 / 0.29)) < 1e-9


def test_iv_percentile_counts_strictly_below():
    history = [Decimal(str(x / 100)) for x in range(10, 40)]
    out = F.iv_percentile(Decimal("0.25"), history)
    assert out.value is not None
    # 0.10..0.24 strictly below 0.25 = 15 values; total = 30 → 0.5
    assert abs(float(out.value) - 0.5) < 1e-9


def test_iv_rank_short_history_returns_none_with_flag():
    out = F.iv_rank(Decimal("0.25"), [Decimal("0.20")] * 10)
    assert out.value is None
    assert F.FLAG_INSUFFICIENT_IV_HISTORY in out.flags


# ===========================================================================
# Realized vol + VRP
# ===========================================================================

def test_realized_vol_constant_series_is_zero():
    closes = [Decimal("100")] * 25
    out = F.realized_vol(closes)
    assert out.value == Decimal("0")


def test_realized_vol_log_returns_then_annualized():
    """Build closes with stdev of log returns ≈ 0.01; expect rv ≈ 0.01·√252."""
    closes = [Decimal("100")]
    for i in range(1, 22):
        # alternating ±1% returns
        mult = 1.01 if i % 2 == 1 else (1 / 1.01)
        closes.append(closes[-1] * Decimal(str(mult)))
    out = F.realized_vol(closes)
    assert out.value is not None
    # log(1.01) ≈ 0.00995; stdev of alternating ±0.00995 ≈ 0.00995 (n-1 sample)
    expected = 0.00995 * math.sqrt(252)
    assert abs(float(out.value) - expected) < 0.05


def test_realized_vol_no_history_flags_no_price_history():
    out = F.realized_vol(None)
    assert out.value is None
    assert F.FLAG_NO_PRICE_HISTORY in out.flags


def test_vrp_subtracts_realized_from_iv():
    out = F.vrp(Decimal("0.20"), Decimal("0.15"))
    assert out.value == Decimal("0.05")


def test_vrp_none_inputs_return_none():
    assert F.vrp(None, Decimal("0.15")).value is None
    assert F.vrp(Decimal("0.20"), None).value is None


# ===========================================================================
# Skew (25-delta put IV − 25-delta call IV)
# ===========================================================================

def test_skew_25d_picks_correct_quotes():
    as_of = dt.date(2026, 5, 18)
    e30 = as_of + dt.timedelta(days=30)
    quotes = [
        _q(option_type="PUT",  strike=435, expiry=e30, delta=-0.25, iv=0.30),
        _q(option_type="PUT",  strike=440, expiry=e30, delta=-0.40, iv=0.28),
        _q(option_type="CALL", strike=465, expiry=e30, delta=0.25,  iv=0.18),
        _q(option_type="CALL", strike=470, expiry=e30, delta=0.10,  iv=0.16),
    ]
    out = F.skew_25_delta(quotes, as_of=as_of)
    assert out.value == Decimal("0.30") - Decimal("0.18")
    assert out.flags == ()


def test_skew_25d_missing_25d_call_flags():
    as_of = dt.date(2026, 5, 18)
    e30 = as_of + dt.timedelta(days=30)
    quotes = [
        _q(option_type="PUT",  strike=435, expiry=e30, delta=-0.25, iv=0.30),
        _q(option_type="CALL", strike=470, expiry=e30, delta=0.05,  iv=0.16),  # too far from 0.25
    ]
    out = F.skew_25_delta(quotes, as_of=as_of)
    assert out.value is None
    assert F.FLAG_NO_25D_CALL in out.flags


# ===========================================================================
# Term structure (30/90 IV ratio)
# ===========================================================================

def test_term_structure_in_contango_ratio_lt_one():
    as_of = dt.date(2026, 5, 18)
    spot = Decimal("450")
    e30 = as_of + dt.timedelta(days=30)
    e90 = as_of + dt.timedelta(days=90)
    quotes = [
        _q(option_type="CALL", strike=450, expiry=e30, iv=0.18),
        _q(option_type="CALL", strike=450, expiry=e90, iv=0.22),
    ]
    out = F.term_structure(quotes, as_of=as_of, spot=spot)
    assert out.value is not None
    assert abs(float(out.value) - (0.18 / 0.22)) < 1e-9


def test_term_structure_in_backwardation_ratio_gt_one():
    as_of = dt.date(2026, 5, 18)
    spot = Decimal("450")
    e30 = as_of + dt.timedelta(days=30)
    e90 = as_of + dt.timedelta(days=90)
    quotes = [
        _q(option_type="CALL", strike=450, expiry=e30, iv=0.40),
        _q(option_type="CALL", strike=450, expiry=e90, iv=0.20),
    ]
    out = F.term_structure(quotes, as_of=as_of, spot=spot)
    assert float(out.value) > 1.0


def test_term_structure_single_expiry_flags_no_long_leg():
    as_of = dt.date(2026, 5, 18)
    spot = Decimal("450")
    e30 = as_of + dt.timedelta(days=30)
    quotes = [_q(option_type="CALL", strike=450, expiry=e30, iv=0.20)]
    out = F.term_structure(quotes, as_of=as_of, spot=spot)
    assert out.value is None
    assert F.FLAG_NO_90D_EXPIRY in out.flags


# ===========================================================================
# Unusual volume z-score
# ===========================================================================

def test_unusual_volume_z_two_sigma_above_history():
    history = [100] * 20
    # σ = 0; today=200 → since pstdev=0, returns 0 not None (special branch)
    z = F.unusual_volume_z(200, history)
    assert z.value == Decimal("0")


def test_unusual_volume_z_with_real_dispersion():
    history = [100, 110, 90, 105, 95, 100, 110, 90, 100, 105]
    z = F.unusual_volume_z(140, history)
    assert z.value is not None
    assert float(z.value) > 4.0     # well above mean


def test_unusual_volume_z_short_history_flags():
    z = F.unusual_volume_z(100, [50, 60])
    assert z.value is None
    assert F.FLAG_INSUFFICIENT_VOL_HIST in z.flags


# ===========================================================================
# Gamma exposure proxy
# ===========================================================================

def test_gex_calls_positive_puts_negative_sum():
    quotes = [
        _q(option_type="CALL", strike=450, gamma=0.05, open_interest=1000),
        _q(option_type="PUT",  strike=440, gamma=0.04, open_interest=2000),
    ]
    out = F.gamma_exposure_proxy(quotes)
    expected = (Decimal("0.05") * 1000 * 100
                - Decimal("0.04") * 2000 * 100)
    assert out.value == expected


def test_gex_missing_gamma_skips_row():
    quotes = [
        _q(option_type="CALL", strike=450, gamma=None, open_interest=1000),
        _q(option_type="CALL", strike=460, gamma=0.03, open_interest=500),
    ]
    out = F.gamma_exposure_proxy(quotes)
    assert out.value == Decimal("0.03") * 500 * 100


def test_gex_no_oi_anywhere_flags():
    quotes = [_q(option_type="CALL", strike=450, gamma=None, open_interest=None)]
    out = F.gamma_exposure_proxy(quotes)
    assert out.value is None
    assert F.FLAG_NO_OPEN_INTEREST in out.flags


# ===========================================================================
# Walls
# ===========================================================================

def test_walls_pick_max_oi_strike_per_side():
    quotes = [
        _q(option_type="CALL", strike=450, open_interest=2000),
        _q(option_type="CALL", strike=460, open_interest=5000),
        _q(option_type="CALL", strike=470, open_interest=1000),
        _q(option_type="PUT",  strike=440, open_interest=3000),
        _q(option_type="PUT",  strike=430, open_interest=7000),
    ]
    out = F.wall_strikes(quotes)
    assert out.call_wall == Decimal("460")
    assert out.put_wall == Decimal("430")
    assert out.flags == ()


def test_walls_one_sided_flags_missing_side():
    quotes = [_q(option_type="CALL", strike=450, open_interest=1000)]
    out = F.wall_strikes(quotes)
    assert out.call_wall == Decimal("450")
    assert out.put_wall is None
    assert F.FLAG_NO_PUTS in out.flags


# ===========================================================================
# build_feature_row aggregator
# ===========================================================================

def test_build_feature_row_full_inputs():
    as_of = dt.date(2026, 5, 18)
    spot = Decimal("450")
    e30 = as_of + dt.timedelta(days=30)
    e90 = as_of + dt.timedelta(days=90)
    quotes = [
        _q(option_type="CALL", strike=450, expiry=e30, delta=0.50, iv=0.20,
           gamma=0.02, open_interest=2000, volume=200),
        _q(option_type="CALL", strike=465, expiry=e30, delta=0.25, iv=0.18,
           gamma=0.01, open_interest=500, volume=50),
        _q(option_type="PUT",  strike=435, expiry=e30, delta=-0.25, iv=0.28,
           gamma=0.01, open_interest=1500, volume=300),
        _q(option_type="PUT",  strike=450, expiry=e30, delta=-0.50, iv=0.22,
           gamma=0.02, open_interest=2500, volume=100),
        _q(option_type="CALL", strike=450, expiry=e90, delta=0.50, iv=0.24,
           gamma=0.01, open_interest=300, volume=20),
    ]
    iv_history = [Decimal(str(x / 100)) for x in range(15, 50)]   # 35 values
    price_history = [Decimal("100")] * 22
    call_vol_history = [200] * 10
    put_vol_history = [300] * 10

    row = build_feature_row(
        underlying="SPY", as_of_date=as_of, quotes=quotes, spot=spot,
        iv_history=iv_history,
        price_history=price_history,
        call_volume_history=call_vol_history,
        put_volume_history=put_vol_history,
    )
    assert row.atm_iv == Decimal("0.20")
    assert row.iv_rank_252d is not None
    assert row.iv_percentile_252d is not None
    assert row.realized_vol_20d == Decimal("0")     # constant series
    assert row.vrp_30d == Decimal("0.20") - Decimal("0")
    assert row.skew_25d == Decimal("0.28") - Decimal("0.18")
    assert row.term_structure_30_90 is not None
    assert row.put_call_volume_ratio is not None
    assert row.put_call_oi_ratio is not None
    assert row.gamma_exposure_proxy is not None
    assert row.call_wall_strike == Decimal("450")
    assert row.put_wall_strike == Decimal("450")
    assert row.unusual_call_volume_z is not None
    assert row.unusual_put_volume_z is not None


def test_build_feature_row_no_history_flags_set():
    as_of = dt.date(2026, 5, 18)
    quotes = [_q(option_type="CALL", strike=450, iv=0.20)]
    row = build_feature_row(
        underlying="SPY", as_of_date=as_of, quotes=quotes,
        spot=Decimal("450"),
        iv_history=None,
        price_history=None,
        call_volume_history=None,
        put_volume_history=None,
    )
    assert row.iv_rank_252d is None
    assert row.iv_percentile_252d is None
    assert row.realized_vol_20d is None
    assert row.vrp_30d is None
    assert row.unusual_call_volume_z is None
    assert F.FLAG_INSUFFICIENT_IV_HISTORY in row.data_quality_flags
    assert F.FLAG_NO_PRICE_HISTORY in row.data_quality_flags
    assert F.FLAG_INSUFFICIENT_VOL_HIST in row.data_quality_flags


def test_build_feature_row_dedups_flags():
    as_of = dt.date(2026, 5, 18)
    row = build_feature_row(
        underlying="SPY", as_of_date=as_of, quotes=[],
        spot=None, iv_history=None, price_history=None,
        call_volume_history=None, put_volume_history=None,
    )
    seen = list(row.data_quality_flags)
    assert len(seen) == len(set(seen))


# ===========================================================================
# Boundary grep — no V2 / equity / strategy imports
# ===========================================================================

_FORBIDDEN_PATTERNS = [
    r"\bv2_promotion(?!_snapshot)\b",
    r"\bv2_promotion_snapshot\b",
    r"\bv2_oos_monitoring\b",
    r"\bv2_stat_validation\b",
    r"\bb2_v2_comparison\b",
    r"\bengine_b\w*",
    r"\bshadow_strategy\w*",
    r"\bpaper_trade_log\b",
    r"\bdecision_log\b",
    r"\bpaper_shadow_log\b",
    r"\brun_v2_promotion_snapshot\b",
]


def _options_features_sources() -> list[Path]:
    here = Path(__file__).resolve()
    features_dir = here.parent.parent.parent / "src" / "options" / "features"
    return list(features_dir.rglob("*.py"))


def test_no_forbidden_imports_in_features_modules():
    for src_path in _options_features_sources():
        src = src_path.read_text(encoding="utf-8")
        import_lines = [
            ln for ln in src.splitlines()
            if ln.strip().startswith(("import ", "from "))
        ]
        joined = "\n".join(import_lines)
        for pat in _FORBIDDEN_PATTERNS:
            assert not re.search(pat, joined, re.IGNORECASE), (
                f"forbidden pattern {pat!r} in imports of {src_path.name}"
            )


def test_features_modules_import_in_isolation():
    """Importing the feature engine MUST NOT pull in V2 / equity modules."""
    import sys
    before = set(sys.modules)
    importlib.import_module("apps.api.src.options.features.compute")
    importlib.import_module("apps.api.src.options.features.engine")
    after = set(sys.modules)
    new_modules = after - before
    forbidden = (
        "v2_promotion_gates", "v2_promotion_state", "v2_promotion_snapshot",
        "v2_oos_monitoring", "v2_stat_validation", "b2_v2_comparison",
        "engine_b", "shadow_strategy",
    )
    for f in forbidden:
        assert not any(f in m for m in new_modules), \
            f"feature engine indirectly pulled in {f}"


def test_no_strategy_or_trade_creation_in_features():
    """Features layer must NOT contain strategy / trade-creation hooks."""
    for src_path in _options_features_sources():
        if src_path.name == "__init__.py":
            continue
        src = src_path.read_text(encoding="utf-8")
        for pat in (
            r"\bOptionsPaperTrade\b",
            r"\bOptionsPaperTradeLeg\b",
            r"\biron_condor\b",
            r"\bshort_put_credit\b",
            r"\bshort_call_credit\b",
            r"\bstrategy\b\s*=",
            r"\brecommend\w*",
        ):
            for line in src.splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"""'):
                    continue
                assert not re.search(pat, line, re.IGNORECASE), (
                    f"forbidden strategy/trade pattern {pat!r} "
                    f"in {src_path.name}: {line.strip()}"
                )
