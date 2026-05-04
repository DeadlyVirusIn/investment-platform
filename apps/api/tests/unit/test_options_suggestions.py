"""Phase 2 — options/daily-suggestions endpoint pins.

Pins:
  1. /api/performance/options/daily-suggestions registered + GET-only.
  2. No INSERT/UPDATE/DELETE in source for options router.
  3. No options_paper_trade row writes from this router.
  4. Status vocabulary frozen.
  5. Suggestion-type vocabulary frozen.
  6. Liquidity thresholds pinned (min_bid, max_relative_spread,
     min_open_interest, max_quote_age_seconds).
  7. Signal-mapping thresholds pinned (bullish=+0.30, bearish=-0.30,
     high_iv=0.45).
  8. Ranking sorts items by composite_rank_score desc.
  9. Stock signal mapping: CALL + bullish score → directional_call;
     PUT + bearish score → directional_put.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROUTER = Path("apps/api/src/api/performance_paper.py")


def test_route_registered():
    src = ROUTER.read_text(encoding="utf-8")
    assert '@options_router.get("/daily-suggestions")' in src


def test_options_router_prefix_pinned():
    src = ROUTER.read_text(encoding="utf-8")
    assert 'prefix="/performance/options"' in src


def test_main_py_mounts_options_router():
    src = Path("apps/api/src/main.py").read_text(encoding="utf-8")
    assert "performance_options_router" in src


def test_get_only():
    src = ROUTER.read_text(encoding="utf-8")
    for f in ("@router.post", "@router.put",
              "@router.patch", "@router.delete",
              "@options_router.post", "@options_router.put",
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
    """Hard pin: options shadow endpoint MUST never write to
    options_paper_trade."""
    src = ROUTER.read_text(encoding="utf-8")
    forbidden = (
        "INSERT INTO options_paper_trade",
        "OptionsPaperTrade(",
        "submit_options_trade",
    )
    for f in forbidden:
        assert f not in src, f"forbidden options-execution token: {f}"


def test_status_vocabulary_pinned():
    src = ROUTER.read_text(encoding="utf-8")
    for s in ("shadow_candidate", "liquidity_blocked", "data_blocked"):
        assert f'"{s}"' in src


def test_suggestion_type_vocabulary_pinned():
    src = ROUTER.read_text(encoding="utf-8")
    for s in ("directional_call", "directional_put",
              "volatility_play", "spread_candidate"):
        assert f'"{s}"' in src


def test_liquidity_thresholds_pinned():
    src = ROUTER.read_text(encoding="utf-8")
    assert "_OPT_MIN_BID = 0.05" in src
    assert "_OPT_MAX_RELATIVE_SPREAD = 0.20" in src
    assert "_OPT_MIN_OPEN_INTEREST = 100" in src
    assert "_OPT_MAX_QUOTE_AGE_SECONDS = 600" in src


def test_signal_mapping_thresholds_pinned():
    src = ROUTER.read_text(encoding="utf-8")
    assert "_OPT_SIGNAL_BULLISH = 0.30" in src
    assert "_OPT_SIGNAL_BEARISH = -0.30" in src
    assert "_OPT_HIGH_IV_THRESHOLD = 0.45" in src


# ---------------------------------------------------------------------------
# Pure-helper unit tests
# ---------------------------------------------------------------------------
def test_classify_suggestion_call_bullish():
    from apps.api.src.api.performance_paper import _classify_suggestion
    assert _classify_suggestion("CALL", 0.5, 0.20) == "directional_call"


def test_classify_suggestion_put_bearish():
    from apps.api.src.api.performance_paper import _classify_suggestion
    assert _classify_suggestion("PUT", -0.5, 0.20) == "directional_put"


def test_classify_suggestion_high_iv_volatility_play():
    from apps.api.src.api.performance_paper import _classify_suggestion
    # No directional alignment + high IV → volatility_play.
    assert _classify_suggestion("CALL", -0.10, 0.50) == "volatility_play"


def test_classify_suggestion_default_spread_candidate():
    from apps.api.src.api.performance_paper import _classify_suggestion
    # No directional, low IV → spread_candidate.
    assert _classify_suggestion("CALL", 0.0, 0.20) == "spread_candidate"


def test_liquidity_score_passes_clean_quote():
    from apps.api.src.api.performance_paper import _opt_liquidity_score
    score, fails = _opt_liquidity_score(
        bid=1.20, ask=1.24, mid=1.22,
        oi=500, quote_age=12,
    )
    assert fails == []
    assert 0.0 <= score <= 1.0


def test_liquidity_score_rejects_low_oi():
    from apps.api.src.api.performance_paper import _opt_liquidity_score
    score, fails = _opt_liquidity_score(
        bid=1.20, ask=1.24, mid=1.22,
        oi=50, quote_age=12,
    )
    assert "oi_below_floor" in fails


def test_liquidity_score_rejects_wide_spread():
    from apps.api.src.api.performance_paper import _opt_liquidity_score
    score, fails = _opt_liquidity_score(
        bid=1.00, ask=2.00, mid=1.50,
        oi=500, quote_age=12,
    )
    assert "spread_too_wide" in fails


def test_liquidity_score_rejects_stale_quote():
    from apps.api.src.api.performance_paper import _opt_liquidity_score
    score, fails = _opt_liquidity_score(
        bid=1.20, ask=1.24, mid=1.22,
        oi=500, quote_age=999,
    )
    assert "quote_too_stale" in fails


# ---------------------------------------------------------------------------
# In-process behavior
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
    r = client.get("/api/performance/options/daily-suggestions?limit=5")
    assert r.status_code == 200


def test_endpoint_pins_required_response_keys(client):
    r = client.get("/api/performance/options/daily-suggestions?limit=5")
    body = r.json()
    for k in (
        "as_of_date", "reviewed_contracts", "underlyings_covered",
        "count", "items", "summary", "by_underlying",
        "by_suggestion_type", "vocabulary", "thresholds", "notice",
    ):
        assert k in body, f"missing top-level key: {k}"


def test_endpoint_summary_keys_pinned(client):
    r = client.get("/api/performance/options/daily-suggestions?limit=5")
    s = r.json()["summary"]
    for k in (
        "total", "shadow_candidate", "liquidity_blocked",
        "data_blocked", "liquidity_pass_rate",
    ):
        assert k in s


def test_items_ranked_desc(client):
    r = client.get("/api/performance/options/daily-suggestions?limit=200")
    items = r.json()["items"]
    scores = [it["composite_rank_score"] for it in items]
    assert scores == sorted(scores, reverse=True)
    # Ranks assigned 1..N.
    assert [it["rank"] for it in items] == list(range(1, len(items) + 1))


def test_per_item_required_fields(client):
    r = client.get("/api/performance/options/daily-suggestions?limit=5")
    for it in r.json()["items"]:
        for k in (
            "underlying", "option_symbol", "expiry", "strike",
            "option_type", "bid", "ask", "mid", "spread", "iv",
            "open_interest", "volume", "delta", "quote_age_seconds",
            "liquidity_score", "liquidity_failures",
            "stock_signal", "suggestion_type", "status",
            "composite_rank_score", "rank",
        ):
            assert k in it, f"options item missing {k}"


def test_invalid_date_rejected(client):
    r = client.get(
        "/api/performance/options/daily-suggestions?as_of=not-a-date"
    )
    assert "error" in r.json()


def test_underlying_filter_works(client):
    r = client.get(
        "/api/performance/options/daily-suggestions?underlying=SPY"
    )
    body = r.json()
    for it in body["items"]:
        assert it["underlying"] == "SPY"


def test_options_paper_trade_count_zero(client):
    """Sanity: while the endpoint runs, options_paper_trade stays 0."""
    from sqlalchemy import text
    from apps.api.src.db import SessionLocal
    with SessionLocal() as s:
        n = s.execute(text(
            "SELECT count(*) FROM options_paper_trade"
        )).scalar() or 0
    assert n == 0
