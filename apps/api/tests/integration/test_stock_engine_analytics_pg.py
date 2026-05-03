"""Integration: stock-engine analytics endpoints against Postgres."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, CandidateIdea
from apps.api.src.domain.stock_engine.analytics import (
    blocked_alpha,
    regime_pressure,
    rejection_analytics,
    score_distribution,
    sector_preview,
    threshold_sensitivity,
)
from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _asset(
    pg_session: Session, symbol: str, sector: str = "tech",
    asset_class: str = "equity",
) -> Asset:
    a = Asset(
        symbol=symbol, asset_class=asset_class, exchange="NASDAQ",
        currency="USD", sector=sector,
    )
    pg_session.add(a)
    pg_session.flush()
    pg_session.commit()
    return a


def _cand(
    pg_session: Session,
    *,
    asset: Asset,
    as_of: dt.date,
    status: str,
    action: str | None = None,
    rejection_reason: str | None = None,
    composite: Decimal | None = None,
    confidence: Decimal | None = None,
    model_version: str | None = None,
) -> CandidateIdea:
    row = CandidateIdea(
        as_of_date=as_of, asset_id=asset.id,
        model_version=model_version or MODEL_VERSION,
        engine="stock_swing",
        status=status, action=action,
        rejection_reason=rejection_reason,
        composite_score=composite,
        confidence=confidence,
        factor_breakdown={}, regime_snapshot={},
    )
    pg_session.add(row)
    pg_session.commit()
    return row


# ---------------------------------------------------------------------------
# 1. rejection_analytics
# ---------------------------------------------------------------------------


def test_rejection_analytics_counts_per_day(pg_session: Session) -> None:
    a = _asset(pg_session, "RA", sector="tech")
    b = _asset(pg_session, "RB", sector="fin")
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 15),
          status="accepted", action="Buy", composite=Decimal("0.4"))
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 16),
          status="rejected", rejection_reason="regime_off",
          composite=Decimal("0.5"))
    _cand(pg_session, asset=b, as_of=dt.date(2026, 4, 16),
          status="rejected", rejection_reason="liquidity_fail",
          composite=Decimal("-0.1"))

    out = rejection_analytics(
        pg_session, from_date=dt.date(2026, 4, 15), to_date=dt.date(2026, 4, 16),
    )
    assert out["totals"] == {"total": 3, "accepted": 1, "rejected": 2}
    assert out["by_reason"]["regime_off"] == 1
    assert out["by_reason"]["liquidity_fail"] == 1
    per_day = {d["as_of_date"]: d for d in out["per_day"]}
    assert per_day["2026-04-15"]["accepted"] == 1
    assert per_day["2026-04-16"]["rejected"] == 2


def test_rejection_analytics_filter_by_sector(pg_session: Session) -> None:
    a = _asset(pg_session, "FS_TECH", sector="tech")
    b = _asset(pg_session, "FS_FIN", sector="fin")
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 15),
          status="rejected", rejection_reason="regime_off",
          composite=Decimal("0.3"))
    _cand(pg_session, asset=b, as_of=dt.date(2026, 4, 15),
          status="rejected", rejection_reason="regime_off",
          composite=Decimal("0.2"))

    out = rejection_analytics(
        pg_session, from_date=dt.date(2026, 4, 15),
        to_date=dt.date(2026, 4, 15), sector="tech",
    )
    assert out["totals"]["total"] == 1
    assert out["by_sector"][0]["sector"] == "tech"


def test_rejection_analytics_filter_by_symbol(pg_session: Session) -> None:
    a = _asset(pg_session, "FS_A")
    b = _asset(pg_session, "FS_B")
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 15),
          status="rejected", rejection_reason="stale_data")
    _cand(pg_session, asset=b, as_of=dt.date(2026, 4, 15),
          status="rejected", rejection_reason="stale_data")

    out = rejection_analytics(
        pg_session, from_date=dt.date(2026, 4, 15),
        to_date=dt.date(2026, 4, 15), symbol="FS_A",
    )
    assert out["totals"]["total"] == 1


# ---------------------------------------------------------------------------
# 2. blocked_alpha
# ---------------------------------------------------------------------------


def test_blocked_alpha_filters_by_min_score_and_sorts(
    pg_session: Session,
) -> None:
    low = _asset(pg_session, "BLO")
    high = _asset(pg_session, "BHI")
    mid = _asset(pg_session, "BMD")
    _cand(pg_session, asset=low, as_of=dt.date(2026, 4, 15),
          status="rejected", rejection_reason="regime_off",
          composite=Decimal("0.10"))
    _cand(pg_session, asset=high, as_of=dt.date(2026, 4, 15),
          status="rejected", rejection_reason="regime_off",
          composite=Decimal("0.60"))
    _cand(pg_session, asset=mid, as_of=dt.date(2026, 4, 15),
          status="rejected", rejection_reason="earnings_too_close",
          composite=Decimal("0.35"))

    out = blocked_alpha(
        pg_session, from_date=dt.date(2026, 4, 15),
        to_date=dt.date(2026, 4, 15),
        min_score=Decimal("0.25"),
    )
    syms = [r["symbol"] for r in out["items"]]
    assert syms == ["BHI", "BMD"]
    assert out["by_reason"]["regime_off"] == 1
    assert out["by_reason"]["earnings_too_close"] == 1


def test_blocked_alpha_filter_by_reason(pg_session: Session) -> None:
    a = _asset(pg_session, "BAR_A")
    b = _asset(pg_session, "BAR_B")
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 15),
          status="rejected", rejection_reason="regime_off",
          composite=Decimal("0.50"))
    _cand(pg_session, asset=b, as_of=dt.date(2026, 4, 15),
          status="rejected", rejection_reason="liquidity_fail",
          composite=Decimal("0.45"))

    out = blocked_alpha(
        pg_session, from_date=dt.date(2026, 4, 15),
        to_date=dt.date(2026, 4, 15),
        rejection_reason="regime_off", min_score=Decimal("0.25"),
    )
    assert len(out["items"]) == 1
    assert out["items"][0]["symbol"] == "BAR_A"


def test_blocked_alpha_excludes_accepted(pg_session: Session) -> None:
    a = _asset(pg_session, "BAE")
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 15),
          status="accepted", action="Buy", composite=Decimal("0.60"))
    out = blocked_alpha(
        pg_session, from_date=dt.date(2026, 4, 15),
        to_date=dt.date(2026, 4, 15), min_score=Decimal("0.25"),
    )
    assert out["count_matched"] == 0


# ---------------------------------------------------------------------------
# 3. score_distribution
# ---------------------------------------------------------------------------


def test_score_distribution_histogram_and_stats(pg_session: Session) -> None:
    # One asset per data point so the unique (as_of, asset, model) index
    # does not collide.
    for i, (d, score) in enumerate([
        (dt.date(2026, 4, 15), Decimal("-0.9")),
        (dt.date(2026, 4, 15), Decimal("-0.3")),
        (dt.date(2026, 4, 15), Decimal("0.05")),
        (dt.date(2026, 4, 16), Decimal("0.40")),
        (dt.date(2026, 4, 16), Decimal("0.85")),
    ]):
        a = _asset(pg_session, f"SDA{i}")
        _cand(pg_session, asset=a, as_of=d,
              status="accepted", action="Hold",
              composite=score)

    out = score_distribution(
        pg_session, from_date=dt.date(2026, 4, 15),
        to_date=dt.date(2026, 4, 16),
    )
    assert out["totals"]["accepted"] == 5
    # Per-day stats
    per_day = {d["as_of_date"]: d for d in out["per_day"]}
    assert per_day["2026-04-15"]["n"] == 3
    # Histogram sums must equal total
    total_hist = sum(b["count"] for b in out["histogram"]["all"])
    assert total_hist == 5


def test_score_distribution_splits_accepted_rejected(
    pg_session: Session,
) -> None:
    a = _asset(pg_session, "SDR")
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 15),
          status="accepted", action="Buy", composite=Decimal("0.50"))
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 16),
          status="rejected", rejection_reason="regime_off",
          composite=Decimal("0.40"))
    out = score_distribution(
        pg_session, from_date=dt.date(2026, 4, 15),
        to_date=dt.date(2026, 4, 16),
    )
    assert sum(b["count"] for b in out["histogram"]["accepted"]) == 1
    assert sum(b["count"] for b in out["histogram"]["rejected"]) == 1


# ---------------------------------------------------------------------------
# 4. threshold_sensitivity
# ---------------------------------------------------------------------------


def test_threshold_sensitivity_counts_by_grid(pg_session: Session) -> None:
    pts = [
        (Decimal("0.12"), "accepted", "Hold"),
        (Decimal("0.22"), "accepted", "Hold"),
        (Decimal("0.28"), "accepted", "Buy"),
        (Decimal("0.45"), "accepted", "Buy"),
        (Decimal("0.35"), "rejected", None),  # blocked by regime
    ]
    for i, (score, status, action) in enumerate(pts):
        a = _asset(pg_session, f"TS{i}")
        _cand(
            pg_session, asset=a, as_of=dt.date(2026, 4, 15),
            status=status, action=action,
            rejection_reason="regime_off" if status == "rejected" else None,
            composite=score,
        )

    out = threshold_sensitivity(
        pg_session, from_date=dt.date(2026, 4, 15),
        to_date=dt.date(2026, 4, 15),
        thresholds=(Decimal("0.10"), Decimal("0.25"), Decimal("0.40")),
    )
    rows = {Decimal(t["threshold"]): t for t in out["thresholds"]}
    # t=0.10: all 5 have score >= 0.10
    assert rows[Decimal("0.10")]["would_be_buys_by_score"] == 5
    # t=0.25: 3 have score >= 0.25 (0.28, 0.45, 0.35)
    assert rows[Decimal("0.25")]["would_be_buys_by_score"] == 3
    assert rows[Decimal("0.25")]["actually_accepted_buys"] == 2  # 0.28 & 0.45 are Buys
    assert rows[Decimal("0.25")]["rejected_with_sufficient_score"] == 1
    assert rows[Decimal("0.25")]["rejected_breakdown_by_reason"] == {"regime_off": 1}


def test_threshold_sensitivity_is_read_only(pg_session: Session) -> None:
    a = _asset(pg_session, "TS_RO")
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 15),
          status="accepted", action="Hold", composite=Decimal("0.30"))

    threshold_sensitivity(
        pg_session, from_date=dt.date(2026, 4, 15),
        to_date=dt.date(2026, 4, 15),
        thresholds=(Decimal("0.10"),),
    )
    pg_session.expire_all()
    rows = list(pg_session.query(CandidateIdea).all())
    assert len(rows) == 1
    # Action unchanged — analysis does not persist
    assert rows[0].action == "Hold"


# ---------------------------------------------------------------------------
# 5. regime_pressure
# ---------------------------------------------------------------------------


def test_regime_pressure_triggered_day(pg_session: Session) -> None:
    a = _asset(pg_session, "RP_A")
    b = _asset(pg_session, "RP_B")
    # 2026-04-15: all rejected regime_off, max score 0.55 → triggered
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 15),
          status="rejected", rejection_reason="regime_off",
          composite=Decimal("0.55"))
    _cand(pg_session, asset=b, as_of=dt.date(2026, 4, 15),
          status="rejected", rejection_reason="regime_off",
          composite=Decimal("0.20"))
    # 2026-04-16: mixed → not triggered (not all regime_off)
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 16),
          status="accepted", action="Buy", composite=Decimal("0.40"))
    _cand(pg_session, asset=b, as_of=dt.date(2026, 4, 16),
          status="rejected", rejection_reason="regime_off",
          composite=Decimal("0.30"))

    out = regime_pressure(
        pg_session, from_date=dt.date(2026, 4, 15),
        to_date=dt.date(2026, 4, 16), min_top_score=Decimal("0.25"),
    )
    assert out["triggered_day_count"] == 1
    assert out["triggered_days"][0]["as_of_date"] == "2026-04-15"
    assert Decimal(out["triggered_days"][0]["max_composite_score"]) == Decimal("0.55")
    assert Decimal(out["avg_blocked_top_score"]) == Decimal("0.55")


def test_regime_pressure_below_min_top_score_not_triggered(
    pg_session: Session,
) -> None:
    a = _asset(pg_session, "RP_LOW")
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 15),
          status="rejected", rejection_reason="regime_off",
          composite=Decimal("0.10"))
    out = regime_pressure(
        pg_session, from_date=dt.date(2026, 4, 15),
        to_date=dt.date(2026, 4, 15), min_top_score=Decimal("0.25"),
    )
    assert out["triggered_day_count"] == 0


# ---------------------------------------------------------------------------
# 6. sector_preview
# ---------------------------------------------------------------------------


def test_sector_preview_counts_per_sector(pg_session: Session) -> None:
    t1 = _asset(pg_session, "SP_T1", sector="tech")
    t2 = _asset(pg_session, "SP_T2", sector="tech")
    f1 = _asset(pg_session, "SP_F1", sector="fin")
    as_of = dt.date(2026, 4, 17)
    _cand(pg_session, asset=t1, as_of=as_of,
          status="accepted", action="Buy", composite=Decimal("0.50"))
    _cand(pg_session, asset=t2, as_of=as_of,
          status="rejected", rejection_reason="regime_off",
          composite=Decimal("0.60"))
    _cand(pg_session, asset=f1, as_of=as_of,
          status="accepted", action="Hold", composite=Decimal("0.10"))

    out = sector_preview(pg_session, as_of=as_of, min_blocked_score=Decimal("0.25"))
    by_sector = {s["sector"]: s for s in out["sectors"]}
    assert by_sector["tech"]["accepted_buys"] == 1
    assert by_sector["tech"]["rejected_high_score"] == 1
    assert by_sector["fin"]["accepted_buys"] == 0
    assert by_sector["fin"]["accepted_total"] == 1


def test_sector_preview_falls_back_to_asset_class_when_sector_null(
    pg_session: Session,
) -> None:
    # asset with sector=None; asset_class='etf'
    e = Asset(
        symbol="NOSECT", asset_class="etf", exchange="NYSE",
        currency="USD", sector=None,
    )
    pg_session.add(e)
    pg_session.flush()
    pg_session.commit()
    _cand(pg_session, asset=e, as_of=dt.date(2026, 4, 17),
          status="accepted", action="Buy", composite=Decimal("0.30"))

    out = sector_preview(pg_session, as_of=dt.date(2026, 4, 17))
    assert out["sectors"][0]["sector"] == "etf"


def test_sector_preview_empty_when_no_rows(pg_session: Session) -> None:
    out = sector_preview(pg_session)
    assert out["as_of_date"] is None
    assert out["sectors"] == []


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------


def test_rejections_endpoint(pg_session: Session) -> None:
    from apps.api.src.main import app

    a = _asset(pg_session, "EPT_RJ")
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 17),
          status="rejected", rejection_reason="regime_off",
          composite=Decimal("0.30"))

    client = TestClient(app)
    resp = client.get(
        "/api/stock-engine/analytics/rejections?from=2026-04-17&to=2026-04-17"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["totals"]["rejected"] == 1


def test_blocked_alpha_endpoint(pg_session: Session) -> None:
    from apps.api.src.main import app

    a = _asset(pg_session, "EPT_BA")
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 17),
          status="rejected", rejection_reason="regime_off",
          composite=Decimal("0.50"))

    client = TestClient(app)
    resp = client.get(
        "/api/stock-engine/analytics/blocked-alpha"
        "?from=2026-04-17&to=2026-04-17&min_score=0.25"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count_matched"] == 1


def test_score_distribution_endpoint(pg_session: Session) -> None:
    from apps.api.src.main import app
    a = _asset(pg_session, "EPT_SD")
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 17),
          status="accepted", action="Hold", composite=Decimal("0.1"))
    client = TestClient(app)
    resp = client.get(
        "/api/stock-engine/analytics/score-distribution"
        "?from=2026-04-17&to=2026-04-17"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "histogram" in data


def test_threshold_sensitivity_endpoint_custom_grid(pg_session: Session) -> None:
    from apps.api.src.main import app
    a = _asset(pg_session, "EPT_TS")
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 17),
          status="accepted", action="Hold", composite=Decimal("0.30"))
    client = TestClient(app)
    resp = client.get(
        "/api/stock-engine/analytics/threshold-sensitivity"
        "?from=2026-04-17&to=2026-04-17"
        "&thresholds=0.2&thresholds=0.4"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["thresholds"]) == 2


def test_regime_pressure_endpoint(pg_session: Session) -> None:
    from apps.api.src.main import app
    a = _asset(pg_session, "EPT_RP")
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 17),
          status="rejected", rejection_reason="regime_off",
          composite=Decimal("0.4"))
    client = TestClient(app)
    resp = client.get(
        "/api/stock-engine/analytics/regime-pressure"
        "?from=2026-04-17&to=2026-04-17"
    )
    assert resp.status_code == 200
    assert resp.json()["triggered_day_count"] == 1


def test_sector_preview_endpoint(pg_session: Session) -> None:
    from apps.api.src.main import app
    a = _asset(pg_session, "EPT_SP", sector="tech")
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 17),
          status="accepted", action="Buy", composite=Decimal("0.3"))
    client = TestClient(app)
    resp = client.get("/api/stock-engine/analytics/sector-preview?as_of=2026-04-17")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sectors"][0]["sector"] == "tech"
    assert data["sectors"][0]["accepted_buys"] == 1


# ---------------------------------------------------------------------------
# High-vol soft-cap analytics integration
# ---------------------------------------------------------------------------


def test_rejection_analytics_surfaces_high_vol_topn_overflow(
    pg_session: Session,
) -> None:
    """New reason 'high_vol_topn_overflow' must appear naturally in the
    rejection-reason breakdown."""
    a = _asset(pg_session, "HVO_A")
    b = _asset(pg_session, "HVO_B")
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 17),
          status="accepted", action="Buy", composite=Decimal("0.50"))
    _cand(pg_session, asset=b, as_of=dt.date(2026, 4, 17),
          status="rejected", rejection_reason="high_vol_topn_overflow",
          composite=Decimal("0.45"))

    out = rejection_analytics(
        pg_session, from_date=dt.date(2026, 4, 17),
        to_date=dt.date(2026, 4, 17),
    )
    assert out["by_reason"].get("high_vol_topn_overflow") == 1


def test_blocked_alpha_includes_high_vol_overflow(pg_session: Session) -> None:
    """Blocked-alpha view must pick up high_vol_topn_overflow rows too."""
    a = _asset(pg_session, "HVO_BA")
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 17),
          status="rejected", rejection_reason="high_vol_topn_overflow",
          composite=Decimal("0.45"))

    out = blocked_alpha(
        pg_session, from_date=dt.date(2026, 4, 17),
        to_date=dt.date(2026, 4, 17), min_score=Decimal("0.25"),
    )
    assert out["count_matched"] == 1
    assert out["items"][0]["rejection_reason"] == "high_vol_topn_overflow"


def test_threshold_sensitivity_counts_high_vol_overflow_as_blocked(
    pg_session: Session,
) -> None:
    a = _asset(pg_session, "HVO_TS")
    _cand(pg_session, asset=a, as_of=dt.date(2026, 4, 17),
          status="rejected", rejection_reason="high_vol_topn_overflow",
          composite=Decimal("0.40"))
    out = threshold_sensitivity(
        pg_session, from_date=dt.date(2026, 4, 17),
        to_date=dt.date(2026, 4, 17),
        thresholds=(Decimal("0.25"),),
    )
    t = out["thresholds"][0]
    assert t["rejected_with_sufficient_score"] == 1
    assert t["rejected_breakdown_by_reason"]["high_vol_topn_overflow"] == 1
