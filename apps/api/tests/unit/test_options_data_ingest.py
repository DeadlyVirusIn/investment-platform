"""Phase 11C unit tests — data ingest layer (no DB).

Covers:
  * Liquidity filter rejection paths
  * Greeks fallback (stdlib BSM correctness vs Hull textbook example)
  * Adapter contract — mock substitution; normalization
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

from apps.api.src.options.data.liquidity_filter import (
    MAX_BID_ASK_SPREAD_DOLLARS,
    MAX_QUOTE_AGE_SECONDS,
    MIN_OPEN_INTEREST,
    REJECT_ASK_NOT_GREATER_BID,
    REJECT_BID_NONPOSITIVE,
    REJECT_LOW_OPEN_INTEREST,
    REJECT_MISSING_BID_OR_ASK,
    REJECT_MISSING_GREEKS,
    REJECT_MISSING_IV,
    REJECT_STALE_QUOTE,
    REJECT_WIDE_SPREAD,
    evaluate_quote,
    filter_chain,
)
from apps.api.src.options.data_provider.base_adapter import (
    OptionChainQuote,
    PartialChainWarning,
    ProviderError,
    ProviderUnavailable,
)
from apps.api.src.options.data_provider.greeks import (
    Greeks,
    black_scholes_greeks,
    black_scholes_price,
    fill_missing_greeks,
    implied_volatility,
    time_to_expiry_years,
)
from apps.api.src.options.data_provider.thetadata_adapter import (
    ThetaDataAdapter,
)


# ---------------------------------------------------------------------------
# Quote factory
# ---------------------------------------------------------------------------

def _quote(
    *,
    bid: float | None = 1.50,
    ask: float | None = 1.55,
    mid: float | None = 1.525,
    last: float | None = 1.52,
    volume: int | None = 100,
    open_interest: int | None = 1000,
    delta: float | None = -0.20,
    gamma: float | None = 0.02,
    theta: float | None = -0.05,
    vega: float | None = 0.10,
    iv: float | None = 0.18,
    quote_age_seconds: int = 2,
    option_type: str = "PUT",
    strike: float = 440.0,
    expiry: dt.date | None = None,
    underlying: str = "SPY",
    snapshot_at_utc: dt.datetime | None = None,
) -> OptionChainQuote:
    if expiry is None:
        expiry = dt.date(2026, 6, 18)
    if snapshot_at_utc is None:
        snapshot_at_utc = dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc)
    return OptionChainQuote(
        snapshot_at_utc=snapshot_at_utc,
        underlying=underlying,
        expiry=expiry,
        strike=Decimal(str(strike)),
        option_type=option_type,
        option_symbol="SPY260618P00440000",
        bid=Decimal(str(bid)) if bid is not None else None,
        ask=Decimal(str(ask)) if ask is not None else None,
        mid=Decimal(str(mid)) if mid is not None else None,
        last=Decimal(str(last)) if last is not None else None,
        volume=volume,
        open_interest=open_interest,
        delta=Decimal(str(delta)) if delta is not None else None,
        gamma=Decimal(str(gamma)) if gamma is not None else None,
        theta=Decimal(str(theta)) if theta is not None else None,
        vega=Decimal(str(vega)) if vega is not None else None,
        iv=Decimal(str(iv)) if iv is not None else None,
        quote_age_seconds=quote_age_seconds,
        provider="thetadata",
    )


# ===========================================================================
# Liquidity filter
# ===========================================================================

def test_filter_accepts_clean_quote():
    assert evaluate_quote(_quote()) is None


def test_filter_rejects_low_open_interest():
    q = _quote(open_interest=MIN_OPEN_INTEREST - 1)
    assert evaluate_quote(q) == REJECT_LOW_OPEN_INTEREST


def test_filter_rejects_wide_spread():
    q = _quote(bid=1.50, ask=1.50 + float(MAX_BID_ASK_SPREAD_DOLLARS) + 0.01)
    assert evaluate_quote(q) == REJECT_WIDE_SPREAD


def test_filter_rejects_nonpositive_bid():
    q = _quote(bid=0.0, ask=0.05)
    assert evaluate_quote(q) == REJECT_BID_NONPOSITIVE


def test_filter_rejects_ask_not_greater_bid():
    q = _quote(bid=1.50, ask=1.50)
    assert evaluate_quote(q) == REJECT_ASK_NOT_GREATER_BID


def test_filter_rejects_missing_bid_or_ask():
    assert evaluate_quote(_quote(bid=None)) == REJECT_MISSING_BID_OR_ASK
    assert evaluate_quote(_quote(ask=None)) == REJECT_MISSING_BID_OR_ASK


def test_filter_rejects_stale_quote():
    q = _quote(quote_age_seconds=MAX_QUOTE_AGE_SECONDS + 1)
    assert evaluate_quote(q) == REJECT_STALE_QUOTE


def test_filter_optional_iv_required():
    q = _quote(iv=None)
    assert evaluate_quote(q, require_iv=True) == REJECT_MISSING_IV
    assert evaluate_quote(q, require_iv=False) is None


def test_filter_optional_greeks_required():
    q = _quote(delta=None)
    assert evaluate_quote(q, require_greeks=True) == REJECT_MISSING_GREEKS
    assert evaluate_quote(q, require_greeks=False) is None


def test_filter_chain_aggregates_counts():
    quotes = [
        _quote(),                                   # ok
        _quote(open_interest=50),                   # LOW_OI
        _quote(bid=1.5, ask=2.0),                   # WIDE_SPREAD
        _quote(quote_age_seconds=300),              # STALE
        _quote(),                                   # ok
    ]
    out = filter_chain(quotes)
    assert out.n_input == 5
    assert out.n_accepted == 2
    assert out.n_rejected == 3
    assert out.reject_counts.get(REJECT_LOW_OPEN_INTEREST) == 1
    assert out.reject_counts.get(REJECT_WIDE_SPREAD) == 1
    assert out.reject_counts.get(REJECT_STALE_QUOTE) == 1


def test_filter_constants_match_design_locks():
    """v1 frozen constants per OPTIONS_STRATEGY_UNIVERSE.md."""
    assert MIN_OPEN_INTEREST == 500
    assert MAX_BID_ASK_SPREAD_DOLLARS == Decimal("0.10")
    assert MAX_QUOTE_AGE_SECONDS == 60


# ===========================================================================
# Black-Scholes-Merton fallback
# ===========================================================================

def test_bsm_at_the_money_call_pricing():
    """ATM call: BSM price > 0 for any positive vol+time."""
    p = black_scholes_price(
        option_type="CALL", spot=100, strike=100,
        time_years=0.5, iv=0.20, rate=0.05, div_yield=0.0,
    )
    # Hull-style approx: 100*[N(d1) - 0.95*N(d2)]; ~6.89
    assert 5.0 < p < 9.0


def test_bsm_atm_put_price_via_put_call_parity():
    """Put-call parity: C - P = S*exp(-q*T) - K*exp(-r*T)."""
    spot, strike, t, iv, r, q = 100, 100, 0.5, 0.20, 0.05, 0.0
    c = black_scholes_price(
        option_type="CALL", spot=spot, strike=strike,
        time_years=t, iv=iv, rate=r, div_yield=q,
    )
    p = black_scholes_price(
        option_type="PUT", spot=spot, strike=strike,
        time_years=t, iv=iv, rate=r, div_yield=q,
    )
    parity = spot * math.exp(-q * t) - strike * math.exp(-r * t)
    assert abs((c - p) - parity) < 1e-6


def test_bsm_call_delta_in_zero_one_range():
    g = black_scholes_greeks(
        option_type="CALL", spot=100, strike=100,
        time_years=0.5, iv=0.20,
    )
    assert g.delta is not None
    assert 0.0 <= g.delta <= 1.0


def test_bsm_put_delta_in_minus_one_zero_range():
    g = black_scholes_greeks(
        option_type="PUT", spot=100, strike=100,
        time_years=0.5, iv=0.20,
    )
    assert g.delta is not None
    assert -1.0 <= g.delta <= 0.0


def test_bsm_gamma_nonneg():
    g = black_scholes_greeks(
        option_type="CALL", spot=100, strike=100,
        time_years=0.5, iv=0.20,
    )
    assert g.gamma is not None and g.gamma >= 0


def test_bsm_vega_nonneg():
    g = black_scholes_greeks(
        option_type="PUT", spot=100, strike=95,
        time_years=0.5, iv=0.25,
    )
    assert g.vega is not None and g.vega >= 0


def test_bsm_theta_negative_for_long_options():
    """Long options bleed theta — both long calls + long puts have
    negative theta on standard inputs."""
    gc = black_scholes_greeks(
        option_type="CALL", spot=100, strike=100,
        time_years=0.5, iv=0.20,
    )
    gp = black_scholes_greeks(
        option_type="PUT", spot=100, strike=100,
        time_years=0.5, iv=0.20,
    )
    assert gc.theta is not None and gc.theta < 0
    assert gp.theta is not None and gp.theta < 0


def test_bsm_iv_inversion_round_trip():
    """Compute price from known IV; invert to recover IV within tol."""
    iv0 = 0.25
    p = black_scholes_price(
        option_type="CALL", spot=100, strike=100,
        time_years=0.5, iv=iv0,
    )
    iv_solved = implied_volatility(
        option_type="CALL", market_price=p,
        spot=100, strike=100, time_years=0.5,
    )
    assert iv_solved is not None
    assert abs(iv_solved - iv0) < 1e-4


def test_bsm_iv_inversion_returns_none_below_intrinsic():
    """Market price below intrinsic value → arbitrage; returns None."""
    iv = implied_volatility(
        option_type="CALL", market_price=0.5,
        spot=120, strike=100, time_years=0.5,    # intrinsic = 20
    )
    assert iv is None


def test_bsm_degenerate_inputs_return_safe_greeks():
    """Zero IV or zero time → no Greeks, no exceptions."""
    g = black_scholes_greeks(
        option_type="CALL", spot=100, strike=100,
        time_years=0.0, iv=0.20,
    )
    assert g.delta is None and g.gamma is None
    g2 = black_scholes_greeks(
        option_type="PUT", spot=100, strike=100,
        time_years=0.5, iv=0.0,
    )
    assert g2.delta is None and g2.gamma is None


def test_time_to_expiry_floors_at_one_day():
    today = dt.date(2026, 5, 18)
    # Same-day → 1/365 floor
    t = time_to_expiry_years(today, today)
    assert abs(t - 1.0 / 365.0) < 1e-9


def test_fill_missing_greeks_uses_provider_when_present():
    g = fill_missing_greeks(
        option_type="CALL",
        spot=Decimal("100"), strike=Decimal("100"),
        snapshot_date=dt.date(2026, 5, 18),
        expiry_date=dt.date(2026, 11, 14),
        market_price=Decimal("5.00"),
        provider_iv=Decimal("0.20"),
        provider_delta=Decimal("0.55"),
        provider_gamma=Decimal("0.03"),
        provider_theta=Decimal("-0.04"),
        provider_vega=Decimal("0.20"),
    )
    assert g.iv == 0.20
    assert g.delta == 0.55     # provider value preserved


def test_fill_missing_greeks_inverts_iv_when_missing():
    """No provider IV; use market_price to invert IV; compute Greeks."""
    g = fill_missing_greeks(
        option_type="CALL",
        spot=Decimal("100"), strike=Decimal("100"),
        snapshot_date=dt.date(2026, 5, 18),
        expiry_date=dt.date(2026, 11, 14),
        market_price=Decimal("5.50"),
        provider_iv=None,
        provider_delta=None,
        provider_gamma=None,
        provider_theta=None,
        provider_vega=None,
    )
    assert g.iv is not None and 0.05 < g.iv < 0.5
    assert g.delta is not None
    assert g.gamma is not None


def test_fill_missing_greeks_returns_nones_when_no_inputs():
    g = fill_missing_greeks(
        option_type="CALL",
        spot=Decimal("100"), strike=Decimal("100"),
        snapshot_date=dt.date(2026, 5, 18),
        expiry_date=dt.date(2026, 6, 18),
        market_price=None,
        provider_iv=None,
    )
    assert g == Greeks(iv=None, delta=None, gamma=None,
                        theta=None, vega=None)


# ===========================================================================
# Adapter contract — mock-substituted ThetaData
# ===========================================================================

class _MockTheta(ThetaDataAdapter):
    """Test double — substitutes _raw_chain_pull with deterministic data."""

    def __init__(self, raw_dict, raise_exc=None):
        super().__init__()
        self._raw = raw_dict
        self._exc = raise_exc

    def _raw_chain_pull(self, *, symbol, timestamp):
        if self._exc is not None:
            raise self._exc
        return self._raw

    def _raw_health_check(self):
        return None


def test_adapter_returns_normalized_quotes():
    raw = {
        "rows": [
            {
                "expiry": "2026-06-18",
                "strike": 440,
                "option_type": "P",
                "option_symbol": "SPY260618P00440000",
                "bid": 1.50, "ask": 1.55, "mid": 1.525, "last": 1.52,
                "volume": 100, "open_interest": 1000,
                "delta": -0.20, "gamma": 0.02,
                "theta": -0.05, "vega": 0.10, "iv": 0.18,
                "quote_age_seconds": 2,
            },
            {
                "expiry": "2026-06-18",
                "strike": 460,
                "option_type": "C",
                "option_symbol": "SPY260618C00460000",
                "bid": 1.40, "ask": 1.45, "mid": 1.425, "last": 1.41,
                "volume": 90, "open_interest": 800,
                "delta": 0.20, "gamma": 0.02,
                "theta": -0.05, "vega": 0.10, "iv": 0.17,
                "quote_age_seconds": 1,
            },
        ],
        "underlying_price": 450.0,
        "interest_rate": 0.05,
        "dividend_yield": 0.015,
        "partial": False,
    }
    adp = _MockTheta(raw)
    out = adp.get_chain_snapshot(
        symbol="SPY",
        timestamp=dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc),
    )
    assert len(out.quotes) == 2
    types = {q.option_type for q in out.quotes}
    assert types == {"PUT", "CALL"}
    assert out.underlying_price == Decimal("450.0")
    assert out.partial is False


def test_adapter_raises_provider_unavailable_on_connection_error():
    adp = _MockTheta({"rows": []}, raise_exc=ConnectionError("no route"))
    with pytest.raises(ProviderUnavailable):
        adp.get_chain_snapshot(
            symbol="SPY",
            timestamp=dt.datetime(2026, 5, 18, tzinfo=dt.timezone.utc),
        )


def test_adapter_raises_provider_unavailable_on_timeout():
    adp = _MockTheta({"rows": []}, raise_exc=TimeoutError("read timeout"))
    with pytest.raises(ProviderUnavailable):
        adp.get_chain_snapshot(
            symbol="SPY",
            timestamp=dt.datetime(2026, 5, 18, tzinfo=dt.timezone.utc),
        )


def test_adapter_raises_provider_error_on_unexpected():
    adp = _MockTheta({"rows": []}, raise_exc=RuntimeError("garbled"))
    with pytest.raises(ProviderError):
        adp.get_chain_snapshot(
            symbol="SPY",
            timestamp=dt.datetime(2026, 5, 18, tzinfo=dt.timezone.utc),
        )


def test_adapter_raises_partial_chain_warning():
    raw = {
        "rows": [
            {
                "expiry": "2026-06-18", "strike": 440, "option_type": "P",
                "option_symbol": "SPY260618P00440000",
                "bid": 1.5, "ask": 1.55, "mid": 1.525, "last": 1.52,
                "volume": 100, "open_interest": 1000,
                "delta": -0.20, "gamma": 0.02, "theta": -0.05,
                "vega": 0.10, "iv": 0.18, "quote_age_seconds": 1,
            },
        ],
        "underlying_price": 450.0,
        "partial": True,
        "partial_reason": "expiries 2026-09-18 unavailable",
    }
    adp = _MockTheta(raw)
    with pytest.raises(PartialChainWarning):
        adp.get_chain_snapshot(
            symbol="SPY",
            timestamp=dt.datetime(2026, 5, 18, tzinfo=dt.timezone.utc),
        )


def test_adapter_skips_malformed_rows():
    raw = {
        "rows": [
            {"expiry": "2026-06-18", "strike": 440, "option_type": "P",
             "option_symbol": "x", "bid": 1.0, "ask": 1.05, "mid": 1.025,
             "last": 1.0, "volume": 1, "open_interest": 1000,
             "delta": -0.2, "gamma": 0.02, "theta": -0.05, "vega": 0.1,
             "iv": 0.2, "quote_age_seconds": 1},
            {"strike": 440, "option_type": "P"},   # missing expiry
        ],
        "partial": False,
    }
    adp = _MockTheta(raw)
    out = adp.get_chain_snapshot(
        symbol="SPY",
        timestamp=dt.datetime(2026, 5, 18, tzinfo=dt.timezone.utc),
    )
    assert len(out.quotes) == 1


def test_adapter_unknown_provider_raises_in_orchestrator():
    """ingest_chain_snapshot rejects unknown provider name."""
    from apps.api.src.options.data import chain_ingest as ci
    with pytest.raises(ValueError):
        ci._build_adapter("polygon")     # v1 supports thetadata only


# ===========================================================================
# Boundary grep — no V2 / equity / strategy imports
# ===========================================================================

_FORBIDDEN_PATTERNS = [
    r"\bv2_promotion_gates\b",
    r"\bv2_promotion_state\b",
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


def _options_module_sources() -> list[Path]:
    here = Path(__file__).resolve()
    options_dir = here.parent.parent.parent / "src" / "options"
    return list(options_dir.rglob("*.py"))


def test_no_forbidden_imports_in_options_modules():
    for src_path in _options_module_sources():
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


def test_options_modules_import_in_isolation():
    """Importing options modules must NOT pull in V2 / equity modules."""
    import sys
    before = set(sys.modules)
    importlib.import_module("apps.api.src.options.data.liquidity_filter")
    importlib.import_module("apps.api.src.options.data_provider.thetadata_adapter")
    importlib.import_module("apps.api.src.options.data_provider.greeks")
    after = set(sys.modules)
    new_modules = after - before
    forbidden = (
        "v2_promotion_gates", "v2_promotion_state", "v2_promotion_snapshot",
        "v2_oos_monitoring", "v2_stat_validation", "b2_v2_comparison",
        "engine_b", "shadow_strategy",
    )
    for f in forbidden:
        assert not any(f in m for m in new_modules), \
            f"options indirectly pulled in {f}"


def test_no_writes_outside_chain_ingest():
    """Only orchestrator modules perform DB writes. Adapter, filter,
    Greeks, and pure-fn feature compute modules must not contain
    INSERT/UPDATE/DELETE.

    Allowlisted writers (one per phase):
      * options/data/chain_ingest.py        (Phase 11C — INSERT-only)
      * options/features/engine.py          (Phase 11D — UPSERT-only)
    """
    _allowed_writers = {"chain_ingest.py", "engine.py"}
    for src_path in _options_module_sources():
        if src_path.name in _allowed_writers:
            continue
        if src_path.name == "__init__.py":
            continue
        src = src_path.read_text(encoding="utf-8")
        for pat in (r"\bINSERT\b", r"\bUPDATE\s+\w+\s+SET\b",
                     r"\bDELETE\s+FROM\b",
                     r"session\.add\b", r"session\.commit\b",
                     r"session\.delete\b"):
            for line in src.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                # skip docstrings
                if stripped.startswith('"""') or stripped.endswith('"""'):
                    continue
                assert not re.search(pat, line), (
                    f"forbidden mutating pattern {pat!r} "
                    f"in {src_path.name}: {line.strip()}"
                )
