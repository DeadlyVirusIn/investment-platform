"""Phase 15i.C — unit tests for GET /api/freshness.

Validates:
  * Response shape always contains the required top-level keys
    (trading_date, last_successful_cycle_at, overall, channels)
    plus all six channels under `channels`.
  * The endpoint stays 200 even when EVERY per-channel reader
    raises (the "all unknown" graceful-degradation contract).
  * Forbidden operator copy ("PIPELINE FAILED" etc.) never
    leaks into any message string.
  * Worst-of aggregation logic for `overall` excludes
    informational channels (options, ml).
"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient


REQUIRED_TOP_KEYS = {
    "trading_date",
    "last_successful_cycle_at",
    "overall",
    "channels",
}

REQUIRED_CHANNELS = {
    "recommendations", "portfolio", "events",
    "options", "risk", "ml",
}

# Banned operator vocabulary — must not appear in any message.
BANNED_PHRASES = (
    "PIPELINE FAILED",
    "ERROR",
    "CRITICAL",
    "SYSTEM DOWN",
)

CHANNEL_REQUIRED_FIELDS = {"status", "as_of", "last_run_id", "message"}
ALLOWED_STATUSES = {"fresh", "degraded", "stale", "unknown"}
ALLOWED_OVERALL = ALLOWED_STATUSES  # overall reuses the same vocabulary


def _client_with_no_db(monkeypatch) -> TestClient:
    """Force every per-channel reader to fail by stubbing out
    SessionLocal so the endpoint takes the all-unknown path
    without touching a real database."""
    from apps.api.src.api import freshness

    class _BoomSession:
        def __enter__(self):  # pragma: no cover — defensive only
            raise RuntimeError("no db in unit test")

        def close(self):  # pragma: no cover — defensive only
            return None

    def _boom():
        raise RuntimeError("no db in unit test")

    monkeypatch.setattr(freshness, "SessionLocal", _boom)

    from apps.api.src.main import app
    return TestClient(app)


def test_freshness_returns_full_skeleton_when_all_unknown(monkeypatch):
    client = _client_with_no_db(monkeypatch)
    r = client.get("/api/freshness")
    assert r.status_code == 200, r.text
    body = r.json()

    # Top-level keys all present.
    assert REQUIRED_TOP_KEYS.issubset(body.keys()), body

    # `trading_date` is an ISO date.
    dt.date.fromisoformat(body["trading_date"])

    # All six channels exist with the required fields.
    chans = body["channels"]
    assert REQUIRED_CHANNELS.issubset(chans.keys()), chans

    for name, payload in chans.items():
        assert CHANNEL_REQUIRED_FIELDS.issubset(payload.keys()), (
            name, payload,
        )
        assert payload["status"] in ALLOWED_STATUSES, (name, payload)

    # All-unknown path: every channel should be unknown because
    # the database is unreachable; events is structurally unknown
    # (no persisted source-of-truth column).
    for name in REQUIRED_CHANNELS:
        assert chans[name]["status"] == "unknown", (name, chans[name])

    # Overall should also be 'unknown' when every primary channel
    # is unknown — never crash, never default to 'stale'.
    assert body["overall"] == "unknown"

    # last_successful_cycle_at is null when no channel has a ts.
    assert body["last_successful_cycle_at"] is None


def test_freshness_messages_never_use_operator_vocabulary(monkeypatch):
    client = _client_with_no_db(monkeypatch)
    r = client.get("/api/freshness")
    assert r.status_code == 200
    body = r.json()
    for name, payload in body["channels"].items():
        msg = (payload.get("message") or "").upper()
        for banned in BANNED_PHRASES:
            assert banned not in msg, (name, banned, msg)


def test_overall_aggregation_excludes_informational_channels(monkeypatch):
    """When the four primary channels are all fresh, the overall
    must be fresh — even if options or ml are stale."""
    from apps.api.src.api import freshness

    chans = {
        "recommendations": {
            "status": "fresh", "as_of": None,
            "last_run_id": None, "message": "",
        },
        "portfolio": {
            "status": "fresh", "as_of": None,
            "last_run_id": None, "message": "",
        },
        "events": {
            "status": "fresh", "as_of": None,
            "last_run_id": None, "message": "",
        },
        "risk": {
            "status": "fresh", "as_of": None,
            "last_run_id": None, "message": "",
        },
        "options": {
            "status": "stale", "as_of": None,
            "last_run_id": None, "message": "",
        },
        "ml": {
            "status": "stale", "as_of": None,
            "last_run_id": None, "message": "",
        },
    }
    assert freshness._aggregate_overall(chans) == "fresh"

    # Flip one primary to stale → overall stale.
    chans["portfolio"]["status"] = "stale"
    assert freshness._aggregate_overall(chans) == "stale"

    # Reset to all degraded primary, options/ml stale → degraded.
    for n in ("recommendations", "portfolio", "events", "risk"):
        chans[n]["status"] = "degraded"
    assert freshness._aggregate_overall(chans) == "degraded"


def test_overall_is_unknown_when_all_primary_unknown(monkeypatch):
    from apps.api.src.api import freshness
    chans = {
        n: {
            "status": "unknown", "as_of": None,
            "last_run_id": None, "message": "",
        }
        for n in (
            "recommendations", "portfolio", "events",
            "options", "risk", "ml",
        )
    }
    assert freshness._aggregate_overall(chans) == "unknown"


def test_classifiers_handle_none_gracefully():
    from apps.api.src.api import freshness as f
    assert f._classify_recommendations(None) == "unknown"
    assert f._classify_portfolio(None, True) == "unknown"
    assert f._classify_events(None) == "unknown"
    assert f._classify_options(None) == "unknown"
    assert f._classify_risk(None, False) == "unknown"
    assert f._classify_ml(None) == "unknown"


def test_classifiers_apply_correct_thresholds():
    from apps.api.src.api import freshness as f
    # recommendations: <26 fresh, 26-50 degraded, >50 stale (RC4 —
    # aligned to the ~24h daily recommendation cadence + grace).
    assert f._classify_recommendations(1.0) == "fresh"
    assert f._classify_recommendations(20.0) == "fresh"
    assert f._classify_recommendations(40.0) == "degraded"
    assert f._classify_recommendations(60.0) == "stale"

    # ml: <7d fresh, 7-14d degraded, >14d stale
    assert f._classify_ml(24.0) == "fresh"
    assert f._classify_ml(7 * 24 + 1) == "degraded"
    assert f._classify_ml(15 * 24.0) == "stale"

    # events: <6h fresh, 6-24h degraded, >24h stale
    assert f._classify_events(1.0) == "fresh"
    assert f._classify_events(12.0) == "degraded"
    assert f._classify_events(48.0) == "stale"
