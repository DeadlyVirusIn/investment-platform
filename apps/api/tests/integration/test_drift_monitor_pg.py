"""Priority 4 — SQL-first drift monitor.

Pins: PSI math on known shifts, minimum-sample gate → insufficient_data
(never an invented verdict), missingness deltas, provider freshness
budgets, bounded JSON-safe report shape for Trust Center consumption.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, PriceBar
from apps.api.src.domain.monitoring.drift import (
    MIN_SAMPLE,
    DriftReport,
    provider_freshness_checks,
    psi,
    run_drift_report,
)

pytestmark = pytest.mark.integration

NOW = dt.datetime(2026, 7, 10, 12, 0, tzinfo=dt.timezone.utc)


def test_psi_zero_for_identical_and_large_for_shifted() -> None:
    ref = [float(i % 100) for i in range(1000)]
    same = psi(ref, list(ref))
    shifted = psi(ref, [v + 60.0 for v in ref])
    assert same is not None and same < 0.01
    assert shifted is not None and shifted > 0.25
    assert psi([], ref) is None                    # empty side
    assert psi([5.0] * 50, ref) is None            # no reference spread


def test_provider_freshness_budget(pg_session: Session) -> None:
    a = Asset(symbol=f"DRF{uuid.uuid4().hex[:4].upper()}",
              asset_class="equity", currency="USD")
    pg_session.add(a)
    pg_session.flush()
    for provider, days_old in (("fresh-prov", 1), ("stale-prov", 10)):
        ts = NOW - dt.timedelta(days=days_old)
        pg_session.add(PriceBar(
            asset_id=a.id, timeframe="1d", ts=ts,
            open=Decimal("1"), high=Decimal("1"), low=Decimal("1"),
            close=Decimal("1"), adjusted_close=Decimal("1"),
            provider=provider,
        ))
    pg_session.commit()

    checks = {c.name: c for c in provider_freshness_checks(pg_session, NOW)}
    assert checks["provider_freshness:fresh-prov"].status == "ok"
    assert checks["provider_freshness:stale-prov"].status == "alert"


def test_report_gates_and_shape(pg_session: Session) -> None:
    # Empty DB windows: every sampled check must say insufficient_data or
    # unavailable — never ok/warn/alert without data.
    report = run_drift_report(pg_session, now=NOW)
    assert isinstance(report, DriftReport)
    payload = report.to_dict()
    json.dumps(payload)                                # JSON-safe
    assert payload["overall"] in ("insufficient_data", "unavailable")
    sampled = [c for c in payload["checks"]
               if c["name"].startswith(("feature_psi", "missingness",
                                        "score_distribution"))]
    assert sampled, "sampled checks missing from report"
    for c in sampled:
        assert c["status"] in ("insufficient_data", "unavailable")
        assert c["n_current"] < MIN_SAMPLE
    assert payload["checks_truncated"] >= 0
    assert len(json.dumps(payload)) < 20_000           # bounded
