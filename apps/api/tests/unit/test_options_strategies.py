"""Phase 2 — options/strategy-suggestions endpoint pins.

Pins:
  1. Route registered + GET-only.
  2. No INSERT/UPDATE/DELETE in source.
  3. No options_paper_trade row writes.
  4. Strategy vocabulary frozen.
  5. IV bucketing thresholds pinned (low<0.25, high>0.45).
  6. Direction thresholds pinned (+0.30 / -0.30).
  7. Spread leg distance pinned (3-10% from ATM).
  8. Pure-helper unit tests for direction, IV bucket, leg builders.
  9. Strategy mapping deterministic per spec table.
 10. Live behavior: 200 + ranked items + strategy distribution.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROUTER = Path("apps/api/src/api/performance_paper.py")


# ---------------------------------------------------------------------------
# Source-grep pins
# ---------------------------------------------------------------------------
def test_route_registered():
    src = ROUTER.read_text(encoding="utf-8")
    assert '@options_router.get("/strategy-suggestions")' in src


def test_get_only():
    src = ROUTER.read_text(encoding="utf-8")
    for f in ("@options_router.post", "@options_router.put",
              "@options_router.patch", "@options_router.delete"):
        assert f not in src


def test_no_writes_in_source():
    src = ROUTER.read_text(encoding="utf-8")
    pats = (
        re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE),
        re.compile(r"\bUPDATE\s+\w+\s+SET\b", re.IGNORECASE),
        re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    )
    for line in src.splitlines():
        s = line.lstrip()
        if (s.startswith("#") or s.startswith('"')
                or s.startswith("'") or s.startswith("*")):
            continue
        for pat in pats:
            assert not pat.search(line)


def test_no_options_paper_trade_writes():
    src = ROUTER.read_text(encoding="utf-8")
    forbidden = (
        "INSERT INTO options_paper_trade",
        "OptionsPaperTrade(",
        "submit_options_trade",
    )
    for f in forbidden:
        assert f not in src, f"forbidden options-execution token: {f}"


def test_strategy_vocabulary_pinned():
    src = ROUTER.read_text(encoding="utf-8")
    for s in ("long_call", "long_put", "bull_call_spread",
              "bear_put_spread", "put_credit_spread",
              "call_credit_spread", "iron_condor"):
        assert f'"{s}"' in src, f"strategy missing: {s}"


def test_iv_thresholds_pinned():
    src = ROUTER.read_text(encoding="utf-8")
    assert "_IV_LOW = 0.25" in src
    assert "_IV_HIGH = 0.45" in src


def test_spread_distance_thresholds_pinned():
    src = ROUTER.read_text(encoding="utf-8")
    assert "_SPREAD_MIN_PCT = 0.03" in src
    assert "_SPREAD_MAX_PCT = 0.10" in src


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def test_direction_strong_buy():
    from apps.api.src.api.performance_paper import _direction_from_score
    assert _direction_from_score(0.40) == "strong_buy"
    assert _direction_from_score(0.30) == "strong_buy"
    assert _direction_from_score(0.29) == "neutral"


def test_direction_strong_sell():
    from apps.api.src.api.performance_paper import _direction_from_score
    assert _direction_from_score(-0.40) == "strong_sell"
    assert _direction_from_score(-0.30) == "strong_sell"
    assert _direction_from_score(-0.29) == "neutral"


def test_direction_none_score():
    from apps.api.src.api.performance_paper import _direction_from_score
    assert _direction_from_score(None) == "neutral"


def test_iv_bucket_low_medium_high_unknown():
    from apps.api.src.api.performance_paper import _iv_bucket
    assert _iv_bucket(0.10) == "low"
    assert _iv_bucket(0.30) == "medium"
    assert _iv_bucket(0.50) == "high"
    assert _iv_bucket(None) is None


def test_pick_strategy_strong_buy_low_iv_long_call():
    from apps.api.src.api.performance_paper import _pick_strategy
    assert _pick_strategy("strong_buy", "low", "uptrend") == "long_call"


def test_pick_strategy_strong_buy_medium_iv_bull_call_spread():
    from apps.api.src.api.performance_paper import _pick_strategy
    assert _pick_strategy(
        "strong_buy", "medium", "uptrend"
    ) == "bull_call_spread"


def test_pick_strategy_strong_buy_high_iv_put_credit_spread():
    from apps.api.src.api.performance_paper import _pick_strategy
    assert _pick_strategy(
        "strong_buy", "high", "uptrend"
    ) == "put_credit_spread"


def test_pick_strategy_strong_sell_buckets():
    from apps.api.src.api.performance_paper import _pick_strategy
    assert _pick_strategy("strong_sell", "low", "downtrend") == "long_put"
    assert _pick_strategy(
        "strong_sell", "medium", "downtrend"
    ) == "bear_put_spread"
    assert _pick_strategy(
        "strong_sell", "high", "downtrend"
    ) == "call_credit_spread"


def test_pick_strategy_iv_missing_falls_back_directional():
    from apps.api.src.api.performance_paper import _pick_strategy
    assert _pick_strategy("strong_buy", None, "uptrend") == "long_call"
    assert _pick_strategy("strong_sell", None, "downtrend") == "long_put"


def test_pick_strategy_neutral_sideways_high_iv_iron_condor():
    from apps.api.src.api.performance_paper import _pick_strategy
    assert _pick_strategy(
        "neutral", "high", "sideways"
    ) == "iron_condor"


def test_pick_strategy_neutral_no_iv_returns_none():
    from apps.api.src.api.performance_paper import _pick_strategy
    assert _pick_strategy("neutral", None, "uptrend") is None


def test_select_atm_picks_closest_strike():
    from apps.api.src.api.performance_paper import _select_atm
    chain = [
        {"option_type": "CALL", "strike": 100.0, "option_symbol": "X1"},
        {"option_type": "CALL", "strike": 110.0, "option_symbol": "X2"},
        {"option_type": "CALL", "strike": 105.0, "option_symbol": "X3"},
        {"option_type": "PUT", "strike": 100.0, "option_symbol": "Y1"},
    ]
    pick = _select_atm(chain, spot=104.0, option_type="CALL")
    assert pick["strike"] == 105.0


def test_select_otm_above_call():
    from apps.api.src.api.performance_paper import _select_otm
    chain = [
        {"option_type": "CALL", "strike": 100.0, "option_symbol": "C1"},
        {"option_type": "CALL", "strike": 105.0, "option_symbol": "C2"},
        {"option_type": "CALL", "strike": 110.0, "option_symbol": "C3"},
        {"option_type": "CALL", "strike": 120.0, "option_symbol": "C4"},
    ]
    pick = _select_otm(chain, spot=100.0, option_type="CALL", above=True)
    assert pick is not None
    # Band [100*1.03, 100*1.10] = [103, 110]; midpoint 106.5; closest strike 105.
    assert 103 <= pick["strike"] <= 110


def test_select_otm_below_put():
    from apps.api.src.api.performance_paper import _select_otm
    chain = [
        {"option_type": "PUT", "strike": 80.0, "option_symbol": "P1"},
        {"option_type": "PUT", "strike": 90.0, "option_symbol": "P2"},
        {"option_type": "PUT", "strike": 95.0, "option_symbol": "P3"},
        {"option_type": "PUT", "strike": 99.0, "option_symbol": "P4"},
    ]
    pick = _select_otm(chain, spot=100.0, option_type="PUT", above=False)
    assert pick is not None
    # Band [100*0.90, 100*0.97] = [90, 97]; midpoint 93.5.
    assert 90 <= pick["strike"] <= 97


# ---------------------------------------------------------------------------
# Live endpoint
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def client():
    import os
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg://invest:dev_only_password@localhost:54329/"
        "investment_platform",
    )
    from fastapi.testclient import TestClient
    from apps.api.src.main import app
    return TestClient(app)


def test_endpoint_returns_200(client):
    r = client.get(
        "/api/performance/options/strategy-suggestions?limit=10"
    )
    assert r.status_code == 200


def test_endpoint_required_keys(client):
    r = client.get(
        "/api/performance/options/strategy-suggestions?limit=5"
    )
    body = r.json()
    for k in (
        "as_of_date", "underlyings_used",
        "contracts_reviewed", "contracts_passed_liquidity",
        "count", "items", "strategy_distribution", "rejected",
        "vocabulary", "thresholds", "notice",
    ):
        assert k in body, f"missing top-level: {k}"


def test_items_have_legs_and_status(client):
    r = client.get(
        "/api/performance/options/strategy-suggestions?limit=20"
    )
    for it in r.json()["items"]:
        assert it["status"] == "shadow_candidate"
        assert it["strategy"] in (
            "long_call", "long_put", "bull_call_spread",
            "bear_put_spread", "put_credit_spread",
            "call_credit_spread", "iron_condor",
        )
        assert isinstance(it["legs"], list) and len(it["legs"]) >= 1
        for leg in it["legs"]:
            assert leg["action"] in ("buy", "sell")
            assert leg["type"] in ("call", "put")


def test_ranked_by_confidence(client):
    r = client.get(
        "/api/performance/options/strategy-suggestions?limit=200"
    )
    items = r.json()["items"]
    confs = [it["confidence"] for it in items]
    assert confs == sorted(confs, reverse=True)


def test_invalid_date_rejected(client):
    r = client.get(
        "/api/performance/options/strategy-suggestions?as_of=bad"
    )
    assert "error" in r.json()


def test_options_paper_trade_count_zero(client):
    """Endpoint must never insert options_paper_trade rows."""
    from sqlalchemy import text
    from apps.api.src.db import SessionLocal
    with SessionLocal() as s:
        n = s.execute(text(
            "SELECT count(*) FROM options_paper_trade"
        )).scalar() or 0
    assert n == 0
