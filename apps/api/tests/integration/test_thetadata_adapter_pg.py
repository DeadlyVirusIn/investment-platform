"""Phase 11O.1 - Adapter + chain_ingest + Postgres integration."""

from __future__ import annotations

import datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.options.data.chain_ingest import ingest_chain_snapshot
from apps.api.src.options.data_provider.thetadata_adapter import (
    ThetaDataAdapter,
    ThetaDataConfig,
)


pytestmark = pytest.mark.integration


def _payload() -> dict:
    expiry = "2026-06-18"
    return {
        "underlying_price": 442.50,
        "interest_rate": 0.05,
        "dividend_yield": 0.0,
        "rows": [
            {
                "expiry": expiry, "strike": 440, "option_type": "PUT",
                "option_symbol": "SPY260618P00440000",
                "bid": 1.20, "ask": 1.25, "mid": 1.225, "last": 1.20,
                "volume": 100, "open_interest": 1000,
                "delta": -0.30, "gamma": 0.02, "theta": -0.05,
                "vega": 0.10, "iv": 0.20, "quote_age_seconds": 2,
            },
            {
                "expiry": expiry, "strike": 435, "option_type": "PUT",
                "option_symbol": "SPY260618P00435000",
                "bid": 0.55, "ask": 0.60, "mid": 0.575, "last": 0.55,
                "volume": 80, "open_interest": 1000,
                "delta": -0.18, "gamma": 0.018, "theta": -0.04,
                "vega": 0.09, "iv": 0.21, "quote_age_seconds": 2,
            },
        ],
    }


@pytest.fixture
def session_factory(pg_engine):
    return sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )


def _adapter(payload):
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json=payload),
    )
    cfg = ThetaDataConfig(
        base_url="http://127.0.0.1:25510",
        max_retries=0, rate_limit_qps=1000.0,
    )
    client = httpx.Client(
        transport=transport, base_url=cfg.base_url,
        headers={"Accept": "application/json"}, timeout=cfg.timeout_seconds,
    )
    return ThetaDataAdapter(
        config=cfg, http_client=client, sleeper=lambda _s: None,
    )


def test_adapter_with_mock_transport_inserts_into_options_chain_snapshot(
    pg_session, session_factory,
):
    adapter = _adapter(_payload())
    summary = ingest_chain_snapshot(
        underlying="SPY",
        snapshot_at_utc=datetime.datetime(
            2026, 4, 27, 14, 0, tzinfo=datetime.timezone.utc,
        ),
        adapter=adapter,
        session_factory=session_factory,
    )
    assert summary.status == "ok"
    assert summary.n_inserted == 2
    n = pg_session.execute(text(
        "SELECT COUNT(*) FROM options_chain_snapshot WHERE underlying='SPY'"
    )).scalar_one()
    assert n == 2


def test_adapter_idempotent_repeat_call_inserts_zero_extra(
    pg_session, session_factory,
):
    adapter = _adapter(_payload())
    snap = datetime.datetime(
        2026, 4, 27, 14, 0, tzinfo=datetime.timezone.utc,
    )
    s1 = ingest_chain_snapshot(
        underlying="SPY", snapshot_at_utc=snap,
        adapter=adapter, session_factory=session_factory,
    )
    s2 = ingest_chain_snapshot(
        underlying="SPY", snapshot_at_utc=snap,
        adapter=adapter, session_factory=session_factory,
    )
    assert s1.n_inserted == 2
    assert s2.n_inserted == 0
    assert s2.n_skipped_existing == 2


def test_adapter_partial_chain_inserts_partial_rows(
    pg_session, session_factory,
):
    payload = _payload()
    payload["partial"] = True
    payload["partial_reason"] = "expiry-2026-07-18 unavailable"
    adapter = _adapter(payload)
    summary = ingest_chain_snapshot(
        underlying="SPY",
        snapshot_at_utc=datetime.datetime(
            2026, 4, 27, 14, 0, tzinfo=datetime.timezone.utc,
        ),
        adapter=adapter,
        session_factory=session_factory,
    )
    assert summary.status == "partial"
    assert summary.n_inserted == 2
