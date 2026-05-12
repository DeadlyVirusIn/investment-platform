"""Phase 16 Phase 2 — derive + persist intraday observations.

Pure-function `derive_observation()` plus UPSERT `write_observation()`
against the `intraday_observation` table. Sole writer of that table.

Discipline (per docs/research/INTRADAY_ML_SHADOW.md):
- No coupling to ORM in the derivation function — all inputs are
  scalars and tiny dicts so unit tests stay trivial.
- Hash-based idempotency: feature_hash = SHA256(feature_dict)[:32]
  is stable for identical inputs and lets the operator audit for
  drift / duplicate writes.
- UNIQUE (recommendation_id, observed_at_15min) UPSERT — re-running
  the same poll cycle produces no duplicate rows. PostgreSQL
  ON CONFLICT DO UPDATE swaps fields if the upstream snapshot
  changed (rare; usually identical within a 15-min slot).
- No trainer / scorer / UI consumes these rows at this phase.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from apps.api.src.db.models import IntradayObservation


# ---------------------------------------------------------------------------
# Time-of-day buckets
# ---------------------------------------------------------------------------

# All buckets keyed in America/New_York wall-clock. Boundaries chosen
# to mirror the operationally meaningful intraday phases:
#   premarket:  04:00–09:30 ET
#   open30:     09:30–10:00 ET (open auction + first 30 min)
#   morning:    10:00–12:00 ET
#   midday:     12:00–14:00 ET
#   afternoon:  14:00–15:30 ET
#   close30:    15:30–16:00 ET (last 30 min + closing auction)
#   afterhours: 16:00–20:00 ET
#   off:        outside the above windows (weekends / 20:00–04:00)
TIME_OF_DAY_BUCKETS = (
    "premarket", "open30", "morning", "midday",
    "afternoon", "close30", "afterhours", "off",
)


def time_of_day_bucket(ts_utc: datetime.datetime) -> str:
    """Return the bucket for a UTC timestamp.

    Pure function. Caller passes a tz-aware UTC datetime; this
    converts to ET via fixed offset (EDT = UTC-4 / EST = UTC-5).
    For Phase 2 v1 we use a simplistic month-based DST proxy — good
    enough for bucket assignment, not for trading decisions. Refine
    later if a precise market-calendar is needed.
    """
    if ts_utc.tzinfo is None:
        # Treat naive as UTC (matches Polygon's `quote_ts` shape).
        ts_utc = ts_utc.replace(tzinfo=datetime.timezone.utc)
    # DST proxy: US/Eastern is EDT (UTC-4) Mar–Nov, EST (UTC-5) Nov–Mar.
    # We use month boundaries; the off-by-2-week edge cases at the
    # DST transitions are acceptable for a 30-min bucket assignment.
    is_dst = 3 <= ts_utc.month <= 10
    et_offset_hours = 4 if is_dst else 5
    et = ts_utc - datetime.timedelta(hours=et_offset_hours)
    # Weekend → off
    if et.weekday() >= 5:
        return "off"
    minutes = et.hour * 60 + et.minute
    if   240 <= minutes < 570:    return "premarket"     # 04:00–09:30
    elif 570 <= minutes < 600:    return "open30"        # 09:30–10:00
    elif 600 <= minutes < 720:    return "morning"       # 10:00–12:00
    elif 720 <= minutes < 840:    return "midday"        # 12:00–14:00
    elif 840 <= minutes < 930:    return "afternoon"     # 14:00–15:30
    elif 930 <= minutes < 960:    return "close30"       # 15:30–16:00
    elif 960 <= minutes < 1200:   return "afterhours"    # 16:00–20:00
    else:                         return "off"


def truncate_to_15min(ts: datetime.datetime) -> datetime.datetime:
    """Floor a tz-aware timestamp to its 15-min slot start (UTC)."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.timezone.utc)
    floor_min = (ts.minute // 15) * 15
    return ts.replace(minute=floor_min, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Pure derivation
# ---------------------------------------------------------------------------


@dataclass
class IntradayObservationRow:
    """In-memory observation row. Caller passes this to write_observation()
    which UPSERTs into the DB. Mirrors the table columns 1:1."""
    recommendation_id: str
    symbol: str
    observed_at_15min: datetime.datetime

    intraday_change_pct:         float | None
    vs_open_pct:                 float | None
    vs_recommendation_entry_pct: float | None
    vs_macro_drift_pct:          float | None
    intraday_range_pct:          float | None
    spy_change_pct:              float | None
    qqq_change_pct:              float | None
    dia_change_pct:              float | None

    time_of_day_bucket:   str
    prior_eod_conviction: float | None
    action_type:          str
    position_state:       str

    atr_60d_pct: float | None
    vol_60d_pct: float | None
    sector_id:   str | None

    source:         str
    delay_minutes:  int
    quote_ts:       datetime.datetime | None
    feature_hash:   str


def _safe_pct(numer: float | None, denom: float | None) -> float | None:
    """Return numer/denom*100 or None if either is missing or denom is 0."""
    if numer is None or denom is None:
        return None
    if float(denom) == 0.0:
        return None
    return (float(numer) / float(denom)) * 100.0


def feature_hash(features: dict[str, Any]) -> str:
    """Stable SHA256(json) → first 32 hex chars. Ignores key order and
    None vs missing distinction so identical observations hash equal."""
    # Drop None values for stable comparison + sort keys.
    norm = {
        k: (float(v) if isinstance(v, (Decimal,)) else v)
        for k, v in features.items()
        if v is not None
    }
    blob = json.dumps(norm, sort_keys=True, separators=(",", ":"),
                      default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def derive_observation(
    *,
    recommendation_id: str,
    symbol: str,
    observed_at: datetime.datetime,
    # Snapshot fields (typically from /api/market/tape entry)
    price: float | None,
    prev_close: float | None,
    day_open: float | None,
    day_high: float | None,
    day_low: float | None,
    # Macro benchmark changes (None when SPY/QQQ/DIA not in cache)
    spy_change_pct: float | None,
    qqq_change_pct: float | None,
    dia_change_pct: float | None,
    # Joined recommendation context
    prior_eod_conviction: float | None,
    action_type: str,
    position_state: str,
    entry_reference_price: float | None,
    # Joined 60d statistics
    atr_60d_pct: float | None,
    vol_60d_pct: float | None,
    sector_id: str | None,
    # Provenance
    source: str = "polygon",
    delay_minutes: int = 15,
    quote_ts: datetime.datetime | None = None,
) -> IntradayObservationRow:
    """Derive a complete IntradayObservationRow from scalar inputs.

    All inputs are scalars or strings — no ORM coupling. The returned
    row is ready to feed into write_observation().

    `observed_at` is floored to the nearest 15-min slot for the
    UNIQUE-constraint key; the raw `quote_ts` (the delayed source ts)
    is preserved separately.
    """
    intraday_change = _safe_pct(
        (price - prev_close) if (price is not None and prev_close is not None) else None,
        prev_close,
    )
    vs_open = _safe_pct(
        (price - day_open) if (price is not None and day_open is not None and day_open != 0) else None,
        day_open,
    )
    vs_entry = _safe_pct(
        (price - entry_reference_price)
        if (price is not None and entry_reference_price is not None) else None,
        entry_reference_price,
    )
    # Macro drift uses SPY as the benchmark.
    if intraday_change is None or spy_change_pct is None:
        vs_macro = None
    else:
        vs_macro = intraday_change - spy_change_pct
    if day_high is not None and day_low is not None and day_open:
        intraday_range = (float(day_high) - float(day_low)) / float(day_open) * 100.0
    else:
        intraday_range = None

    slot = truncate_to_15min(observed_at)
    tod = time_of_day_bucket(slot)

    # Feature dict used for the hash. Keep purely numeric + categorical
    # state — exclude per-cycle provenance + ids.
    feat_dict: dict[str, Any] = {
        "intraday_change_pct":          intraday_change,
        "vs_open_pct":                  vs_open,
        "vs_recommendation_entry_pct":  vs_entry,
        "vs_macro_drift_pct":           vs_macro,
        "intraday_range_pct":           intraday_range,
        "spy_change_pct":               spy_change_pct,
        "qqq_change_pct":               qqq_change_pct,
        "dia_change_pct":               dia_change_pct,
        "time_of_day_bucket":           tod,
        "prior_eod_conviction":         prior_eod_conviction,
        "action_type":                  action_type,
        "position_state":               position_state,
        "atr_60d_pct":                  atr_60d_pct,
        "vol_60d_pct":                  vol_60d_pct,
        "sector_id":                    sector_id,
    }
    fh = feature_hash(feat_dict)

    return IntradayObservationRow(
        recommendation_id=recommendation_id,
        symbol=symbol,
        observed_at_15min=slot,
        intraday_change_pct=intraday_change,
        vs_open_pct=vs_open,
        vs_recommendation_entry_pct=vs_entry,
        vs_macro_drift_pct=vs_macro,
        intraday_range_pct=intraday_range,
        spy_change_pct=spy_change_pct,
        qqq_change_pct=qqq_change_pct,
        dia_change_pct=dia_change_pct,
        time_of_day_bucket=tod,
        prior_eod_conviction=prior_eod_conviction,
        action_type=action_type,
        position_state=position_state,
        atr_60d_pct=atr_60d_pct,
        vol_60d_pct=vol_60d_pct,
        sector_id=sector_id,
        source=source,
        delay_minutes=delay_minutes,
        quote_ts=quote_ts,
        feature_hash=fh,
    )


# ---------------------------------------------------------------------------
# UPSERT writer
# ---------------------------------------------------------------------------


def write_observation(session: Session, row: IntradayObservationRow) -> str:
    """UPSERT one observation. Returns the row id (existing or new).

    PostgreSQL ON CONFLICT (recommendation_id, observed_at_15min) DO
    UPDATE — when the same slot is written twice (e.g. two poll
    cycles inside the same 15-min window), the second write swaps
    the features in place. The feature_hash column tells the operator
    whether the second write was a no-op (same hash) or a real
    refresh (different hash, e.g. mid-slot price moved).
    """
    payload = asdict(row)
    stmt = pg_insert(IntradayObservation).values(**payload)
    # ON CONFLICT — refresh feature columns + feature_hash; preserve id
    # + created_at by NOT listing them in the SET clause.
    excluded = {
        col: stmt.excluded[col]
        for col in payload
        if col not in ("recommendation_id", "observed_at_15min")
    }
    stmt = stmt.on_conflict_do_update(
        constraint="uq_intraday_obs_rec_slot",
        set_=excluded,
    ).returning(IntradayObservation.id)
    result = session.execute(stmt)
    row_id = result.scalar_one()
    session.commit()
    return str(row_id)
