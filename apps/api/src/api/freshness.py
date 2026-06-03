"""Phase 15i.C — GET /api/freshness (read-only).

Single-pane freshness summary aggregating six channels
(`recommendations`, `portfolio`, `events`, `options`, `risk`,
`ml`) plus an `overall` worst-of across the four PRIMARY
channels (recommendations, portfolio, events, risk). Options +
ml are informational and never flip `overall` to stale on their
own.

Strict invariants:
  * READ-ONLY. No INSERT/UPDATE/DELETE issued from this module.
  * Defensive per-channel readers — a missing table or a query
    error returns `status: "unknown"` for that channel and the
    endpoint still returns 200 with the full skeleton.
  * No fabricated timestamps. When a channel has no source-of-
    truth column we expose, return `status: "unknown"` with a
    plain message — never invent an `as_of`.
  * Calm, institutional copy. NEVER emit "PIPELINE FAILED",
    "ERROR", "CRITICAL", "SYSTEM DOWN" or operator-vocabulary.

SLA tiers (carried forward from `docs/ux/PHASE_15g_freshness_audit.md` §5):
  recommendations  fresh < 16h  | degraded 16-30h | stale > 30h
  portfolio        fresh < 30m intraday / < 16h overnight |
                   degraded 30m-4h / 16-30h | stale > 4h / > 30h
  events           fresh < 6h   | degraded 6-24h  | stale > 24h
  options          fresh < 6h   | degraded 6-24h  | stale > 24h
  risk             fresh < 30m mkt hrs | degraded 30m-4h | stale > 4h
  ml               fresh < 7d   | degraded 7-14d  | stale > 14d
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from apps.api.src.db import SessionLocal


router = APIRouter(tags=["freshness"])


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PRIMARY_CHANNELS = ("recommendations", "portfolio", "events", "risk")
_INFORMATIONAL_CHANNELS = ("options", "ml")
_ALL_CHANNELS = _PRIMARY_CHANNELS + _INFORMATIONAL_CHANNELS

_STATUS_FRESH = "fresh"
_STATUS_DEGRADED = "degraded"
_STATUS_STALE = "stale"
_STATUS_UNKNOWN = "unknown"

# Worst-of ordering: higher index = "worse".
_STATUS_RANK = {
    _STATUS_FRESH: 0,
    _STATUS_DEGRADED: 1,
    _STATUS_STALE: 2,
    # Unknown does NOT participate in worst-of for `overall` —
    # see §7.4 — so we don't include it in this rank table.
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _today_et() -> dt.date:
    """Current trading date in America/New_York. Falls back to UTC
    today if zoneinfo cannot resolve the zone (e.g. missing tzdata
    on Windows test runners)."""
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        return dt.datetime.now(dt.timezone.utc).date()


def _hours_since(ts: dt.datetime | None) -> float | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return (_now_utc() - ts).total_seconds() / 3600.0


def _iso(ts: dt.datetime | None) -> str | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return ts.isoformat()


def _is_market_hours(now_utc: dt.datetime) -> bool:
    """Heuristic 9:30-16:00 ET, Mon-Fri. Used by portfolio + risk
    channels to apply the tighter intraday SLA."""
    try:
        from zoneinfo import ZoneInfo
        local = now_utc.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        return False
    if local.weekday() >= 5:
        return False
    minutes = local.hour * 60 + local.minute
    return (9 * 60 + 30) <= minutes <= (16 * 60)


def _human_age(hours: float | None) -> str:
    """Human-friendly age string used for message interpolation."""
    if hours is None:
        return "unknown"
    if hours < 1:
        mins = max(0, int(round(hours * 60)))
        return f"{mins}m"
    if hours < 48:
        return f"{int(round(hours))}h"
    days = hours / 24.0
    return f"{int(round(days))}d"


# ---------------------------------------------------------------------------
# Per-channel SLA classifiers
# ---------------------------------------------------------------------------


def _classify_recommendations(hours: float | None) -> str:
    # RC4: recommendations regenerate on a ~24h cadence (daily 02:30 UTC
    # job). The prior 16h fresh threshold was tighter than the cadence,
    # so a perfectly healthy daily cycle read 'degraded' for ~8h every
    # day. Align to 24h + ~2h grace; degraded out to ~2x cadence.
    if hours is None:
        return _STATUS_UNKNOWN
    if hours < 26:
        return _STATUS_FRESH
    if hours <= 50:
        return _STATUS_DEGRADED
    return _STATUS_STALE


def _classify_portfolio(hours: float | None, market_hours: bool) -> str:
    if hours is None:
        return _STATUS_UNKNOWN
    if market_hours:
        if hours <= 0.5:
            return _STATUS_FRESH
        if hours <= 4:
            return _STATUS_DEGRADED
        return _STATUS_STALE
    # overnight tier
    if hours < 16:
        return _STATUS_FRESH
    if hours <= 30:
        return _STATUS_DEGRADED
    return _STATUS_STALE


def _classify_events(hours: float | None) -> str:
    if hours is None:
        return _STATUS_UNKNOWN
    if hours < 6:
        return _STATUS_FRESH
    if hours <= 24:
        return _STATUS_DEGRADED
    return _STATUS_STALE


def _hours_since_last_close(now_utc: dt.datetime) -> float | None:
    """Hours since the most recent weekday 16:00 ET close (walks back over
    weekends). None if the tz database is unavailable."""
    try:
        from zoneinfo import ZoneInfo
        local = now_utc.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        return None
    close = local.replace(hour=16, minute=0, second=0, microsecond=0)
    if local < close:
        close = close - dt.timedelta(days=1)
    while close.weekday() >= 5:          # skip Sat/Sun back to Friday
        close = close - dt.timedelta(days=1)
    return max(0.0, (local - close).total_seconds() / 3600.0)


# Span of a single trading session (~6.5h) + small buffer. A chain snapshot
# captured anytime during the last session is at most ~this many hours older
# than the last close.
_OPTIONS_SESSION_SPAN_H = 7.0


def _classify_options(hours: float | None, now_utc: dt.datetime) -> str:
    """Market-aware options-chain freshness.

    During market hours the chain is expected to be recent, so genuine
    intraday staleness still degrades health (fresh <6h, degraded 6-12h,
    stale >12h). When the market is CLOSED the chain naturally ages
    overnight/over weekends; a snapshot from the most recent session is
    fresh — staleness is measured relative to the last close, not wall clock.
    """
    if hours is None:
        return _STATUS_UNKNOWN

    if _is_market_hours(now_utc):
        if hours < 6:
            return _STATUS_FRESH
        if hours <= 12:
            return _STATUS_DEGRADED
        return _STATUS_STALE

    since_close = _hours_since_last_close(now_utc)
    if since_close is None:                      # tz fallback → flat rule
        if hours < 6:
            return _STATUS_FRESH
        if hours <= 24:
            return _STATUS_DEGRADED
        return _STATUS_STALE

    # Fresh: snapshot from the last session. Degraded: missed by up to a
    # session-day. Stale: older than ~two sessions.
    if hours <= since_close + _OPTIONS_SESSION_SPAN_H:
        return _STATUS_FRESH
    if hours <= since_close + _OPTIONS_SESSION_SPAN_H + 24.0:
        return _STATUS_DEGRADED
    return _STATUS_STALE


def _classify_risk(hours: float | None, market_hours: bool) -> str:
    if hours is None:
        return _STATUS_UNKNOWN
    # During market hours we apply the tighter risk SLA. Outside
    # market hours we treat the same window as portfolio overnight,
    # so 4h+ of staleness flags as degraded rather than stale.
    if market_hours:
        if hours <= 0.5:
            return _STATUS_FRESH
        if hours <= 4:
            return _STATUS_DEGRADED
        return _STATUS_STALE
    if hours < 16:
        return _STATUS_FRESH
    if hours <= 30:
        return _STATUS_DEGRADED
    return _STATUS_STALE


def _classify_ml(hours: float | None) -> str:
    if hours is None:
        return _STATUS_UNKNOWN
    days = hours / 24.0
    if days < 7:
        return _STATUS_FRESH
    if days <= 14:
        return _STATUS_DEGRADED
    return _STATUS_STALE


# ---------------------------------------------------------------------------
# Per-channel message builders (calm institutional copy only)
# ---------------------------------------------------------------------------


def _msg_recommendations(status: str, as_of_iso: str | None,
                          hours: float | None) -> str:
    if status == _STATUS_FRESH:
        return f"Signals refreshed {as_of_iso}"
    if status == _STATUS_DEGRADED:
        return "Signals from yesterday's close — awaiting next refresh"
    if status == _STATUS_STALE:
        return (
            f"Recommendations based on last completed cycle "
            f"({as_of_iso}). Today's pipeline has not yet produced "
            f"new state."
        )
    return "Recommendation source unavailable"


def _msg_portfolio(status: str, as_of_iso: str | None,
                    hours: float | None) -> str:
    if status == _STATUS_FRESH:
        return f"Account valued {as_of_iso}"
    if status == _STATUS_DEGRADED:
        return f"Account snapshot delayed — last update {as_of_iso}"
    if status == _STATUS_STALE:
        return (
            f"Account snapshot {_human_age(hours)} stale — "
            f"last refresh did not propagate"
        )
    return "Portfolio source unavailable"


def _msg_events(status: str, as_of_iso: str | None,
                 hours: float | None) -> str:
    if status == _STATUS_FRESH:
        return f"Catalysts refreshed {as_of_iso}"
    if status == _STATUS_DEGRADED:
        return (
            f"Catalyst feed delayed — last update "
            f"{_human_age(hours)} ago"
        )
    if status == _STATUS_STALE:
        return "Catalyst feed delayed more than 24h"
    return "Event source unavailable"


def _msg_options(status: str, as_of_iso: str | None,
                  hours: float | None) -> str:
    if status == _STATUS_FRESH:
        return "Options snapshot fresh"
    if status == _STATUS_DEGRADED:
        return (
            f"Options snapshot delayed — last update "
            f"{_human_age(hours)} ago"
        )
    if status == _STATUS_STALE:
        return "Options snapshot more than 24h stale"
    return "Options snapshot source not connected"


def _msg_risk(status: str, as_of_iso: str | None,
               hours: float | None) -> str:
    if status == _STATUS_FRESH:
        return "Risk snapshot fresh"
    if status in (_STATUS_DEGRADED, _STATUS_STALE):
        return "Risk snapshot derived from delayed portfolio source"
    return "Risk source unavailable"


def _msg_ml(status: str, as_of_iso: str | None,
             hours: float | None) -> str:
    days = int(round((hours or 0) / 24.0))
    if status == _STATUS_FRESH:
        return f"Model trained {days}d ago"
    if status == _STATUS_DEGRADED:
        return (
            f"Model trained {days}d ago — "
            f"retraining cadence elapsing"
        )
    if status == _STATUS_STALE:
        return f"Model retraining overdue ({days}d since last train)"
    return "Model lifecycle source unavailable"


# ---------------------------------------------------------------------------
# Per-channel readers — defensive, READ-ONLY
# ---------------------------------------------------------------------------


def _safe_max_ts(session: Session, sql: str) -> dt.datetime | None:
    """Run `SELECT MAX(...) FROM ...` defensively. Any failure
    (table missing, permission denied, dialect quirk) returns
    None — the caller will surface the channel as unknown."""
    try:
        row = session.execute(text(sql)).first()
    except SQLAlchemyError:
        return None
    except Exception:
        return None
    if row is None or row[0] is None:
        return None
    val = row[0]
    if isinstance(val, dt.datetime):
        return val
    if isinstance(val, dt.date):
        # Promote a bare DATE to UTC midnight so the age math works.
        return dt.datetime(
            val.year, val.month, val.day,
            tzinfo=dt.timezone.utc,
        )
    return None


def _read_recommendations(session: Session) -> dt.datetime | None:
    return _safe_max_ts(
        session,
        "SELECT MAX(generated_at) FROM recommendation",
    )


def _read_portfolio(session: Session) -> dt.datetime | None:
    """Portfolio valuation freshness = newest live equity snapshot's
    recorded_at (the wall-clock instant the book was valued).

    RC2: do NOT gate on whole-pipeline paper_run_log.status='success'.
    pipeline_status flips to 'partial' if ANY step warns (e.g. an
    incidental FRED/macro or shadow-eval warn), so that filter starves
    this channel even when the portfolio step itself valued the book.
    RC3: do NOT use snapshot_date — it is a DATE, promoted to UTC
    midnight, inflating age by up to +24h vs the real valuation time.
    Phase L M079: live-only for canonical freshness."""
    return _safe_max_ts(
        session,
        "SELECT MAX(recorded_at) FROM paper_equity_snapshot "
        "WHERE source = 'live'",
    )


def _read_events() -> dt.datetime | None:
    """Events are computed live per request by /api/market/events.
    There is no persisted source-of-truth column in the repo for a
    last-fetch timestamp. Per the contract: return None so the
    channel surfaces as 'unknown' rather than fabricating now()."""
    return None


def _read_options(session: Session) -> dt.datetime | None:
    return _safe_max_ts(
        session,
        "SELECT MAX(snapshot_at_utc) FROM options_chain_snapshot",
    )


def _read_ml(session: Session) -> dt.datetime | None:
    return _safe_max_ts(
        session,
        "SELECT MAX(created_at) FROM ml_model_run",
    )


# ---------------------------------------------------------------------------
# Channel evaluation
# ---------------------------------------------------------------------------


def _channel(status: str, as_of: dt.datetime | None,
              message: str) -> dict[str, Any]:
    return {
        "status": status,
        "as_of": _iso(as_of),
        "last_run_id": None,
        "message": message,
    }


def _evaluate_channels(session: Session | None,
                        now: dt.datetime) -> dict[str, dict[str, Any]]:
    market_hours = _is_market_hours(now)
    out: dict[str, dict[str, Any]] = {}

    # ---- recommendations ----
    rec_ts = _read_recommendations(session) if session is not None else None
    rec_hours = _hours_since(rec_ts)
    rec_status = _classify_recommendations(rec_hours)
    out["recommendations"] = _channel(
        rec_status, rec_ts,
        _msg_recommendations(rec_status, _iso(rec_ts), rec_hours),
    )

    # ---- portfolio ----
    port_ts = _read_portfolio(session) if session is not None else None
    port_hours = _hours_since(port_ts)
    port_status = _classify_portfolio(port_hours, market_hours)
    out["portfolio"] = _channel(
        port_status, port_ts,
        _msg_portfolio(port_status, _iso(port_ts), port_hours),
    )

    # ---- events ----
    ev_ts = _read_events()
    ev_hours = _hours_since(ev_ts)
    ev_status = _classify_events(ev_hours)
    out["events"] = _channel(
        ev_status, ev_ts,
        _msg_events(ev_status, _iso(ev_ts), ev_hours),
    )

    # ---- options ----
    opt_ts = _read_options(session) if session is not None else None
    opt_hours = _hours_since(opt_ts)
    opt_status = _classify_options(opt_hours, now)
    out["options"] = _channel(
        opt_status, opt_ts,
        _msg_options(opt_status, _iso(opt_ts), opt_hours),
    )

    # ---- risk (derived from portfolio source) ----
    risk_ts = port_ts
    risk_hours = port_hours
    risk_status = _classify_risk(risk_hours, market_hours)
    out["risk"] = _channel(
        risk_status, risk_ts,
        _msg_risk(risk_status, _iso(risk_ts), risk_hours),
    )

    # ---- ml ----
    ml_ts = _read_ml(session) if session is not None else None
    ml_hours = _hours_since(ml_ts)
    ml_status = _classify_ml(ml_hours)
    out["ml"] = _channel(
        ml_status, ml_ts,
        _msg_ml(ml_status, _iso(ml_ts), ml_hours),
    )
    return out


def _aggregate_overall(channels: dict[str, dict[str, Any]]) -> str:
    """Worst-of across the four PRIMARY channels. Options + ml are
    informational and excluded. Unknown does NOT downgrade `overall`
    — if every primary is unknown we return 'unknown'."""
    primary_known = [
        channels[name]["status"]
        for name in _PRIMARY_CHANNELS
        if channels[name]["status"] in _STATUS_RANK
    ]
    if not primary_known:
        return _STATUS_UNKNOWN
    worst = max(primary_known, key=lambda s: _STATUS_RANK[s])
    return worst


def _last_successful_cycle_at(
    channels: dict[str, dict[str, Any]],
) -> str | None:
    """MAX of the (recommendations, portfolio) `as_of` timestamps,
    when at least one is present. Returns ISO-8601 UTC string or
    None when neither channel has ever produced a usable timestamp."""
    candidates: list[dt.datetime] = []
    for name in ("recommendations", "portfolio"):
        iso = channels.get(name, {}).get("as_of")
        if not iso:
            continue
        try:
            ts = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        candidates.append(ts)
    if not candidates:
        return None
    return _iso(max(candidates))


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/freshness")
def freshness() -> dict[str, Any]:
    """Read-only freshness summary across the six channels."""
    now = _now_utc()
    trading_date = _today_et()

    session: Optional[Session] = None
    try:
        session = SessionLocal()
    except Exception:
        session = None

    try:
        channels = _evaluate_channels(session, now)
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass

    return {
        "trading_date": trading_date.isoformat(),
        "last_successful_cycle_at": _last_successful_cycle_at(channels),
        "overall": _aggregate_overall(channels),
        "channels": channels,
    }
