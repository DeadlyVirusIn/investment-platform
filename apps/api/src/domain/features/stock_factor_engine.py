"""Stock engine factor pipeline.

Pure computation layer followed by a DB-facing orchestrator. Everything is
deterministic. Features at date ``as_of`` use only bars with
``ts < datetime(as_of, 00:00, UTC)`` — strict anti-lookahead: the ``as_of``
day's bar is excluded.

Cross-sectional transforms (z-score of residual momenta, percentile rank
within sector) run across the universe active on ``as_of`` after
per-asset raw values are computed. Assets flagged ``enough_data=False`` or
``stale_data=True`` are excluded from the cross-section denominators but
still written with NULLs on the z-scored fields.

Sector default: ``asset.sector or asset.asset_class``. Stated default —
when ``sector`` is NULL the asset's ``asset_class`` is used as bucket key.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, PriceBar, UniverseMembership

BENCHMARK_SYMBOL = "SPY"

MIN_BARS_ENOUGH = 200       # for SMA200
STALE_DAYS = 5              # parity with recommendation_engine.STALE_DAYS

# Feature list — update FEATURE_SET_HASH automatically when this changes.
FEATURE_SET: tuple[str, ...] = (
    "residual_momentum_20d",
    "residual_momentum_60d",
    "sector_relative_rank",
    "trend_strength_20d",
    "price_vs_200sma",
    "atr_percent_14",
    "earnings_proximity_days",
    "avg_dollar_volume_20d",
)
FEATURE_SET_HASH: str = hashlib.sha256(
    "|".join(FEATURE_SET).encode("utf-8")
).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Data views
# ---------------------------------------------------------------------------


@dataclass
class BarView:
    ts: dt.datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None


@dataclass
class RawFeatures:
    """Per-asset features computed without cross-section transforms."""
    asset_id: str
    enough_data: bool
    stale_data: bool
    # Raw values (not z-scored)
    residual_return_20d: float | None = None   # simple return diff (asset - SPY)
    residual_return_60d: float | None = None
    return_60d: float | None = None            # raw 60d return (for sector rank)
    trend_strength_20d: float | None = None
    price_vs_200sma: float | None = None
    atr_percent_14: float | None = None
    avg_dollar_volume_20d: float | None = None
    earnings_proximity_days: int | None = None  # NULL until earnings feed wired


@dataclass
class SnapshotRow:
    """Finalized row ready to persist into factor_snapshot."""
    as_of_date: dt.date
    asset_id: str
    residual_momentum_20d: Decimal | None = None
    residual_momentum_60d: Decimal | None = None
    sector_relative_rank: Decimal | None = None
    trend_strength_20d: Decimal | None = None
    price_vs_200sma: Decimal | None = None
    atr_percent_14: Decimal | None = None
    earnings_proximity_days: int | None = None
    avg_dollar_volume_20d: Decimal | None = None
    enough_data: bool = True
    stale_data: bool = False
    feature_set_hash: str = FEATURE_SET_HASH
    notes: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Small numeric helpers
# ---------------------------------------------------------------------------


def _f(v: Decimal | float | int) -> float:
    return float(v)


def _simple_return(prices: Sequence[Decimal], lookback: int) -> float | None:
    if len(prices) < lookback + 1:
        return None
    prev = _f(prices[-lookback - 1])
    curr = _f(prices[-1])
    if prev <= 0:
        return None
    return (curr - prev) / prev


def sma(prices: Sequence[Decimal], n: int) -> float | None:
    if len(prices) < n or n <= 0:
        return None
    return sum(_f(p) for p in prices[-n:]) / n


def atr(bars: Sequence[BarView], period: int = 14) -> float | None:
    if len(bars) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(bars)):
        h, lo = _f(bars[i].high), _f(bars[i].low)
        prev_close = _f(bars[i - 1].close)
        tr = max(h - lo, abs(h - prev_close), abs(lo - prev_close))
        trs.append(tr)
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def avg_dollar_volume(bars: Sequence[BarView], n: int = 20) -> float | None:
    if len(bars) < n:
        return None
    tail = bars[-n:]
    vals: list[float] = []
    for b in tail:
        if b.volume is None or b.volume <= 0:
            continue
        vals.append(_f(b.close) * float(b.volume))
    if not vals:
        return None
    return sum(vals) / len(vals)


def zscore_list(values: Sequence[float | None]) -> list[float | None]:
    """Population z-score across the non-null entries; None slots preserved."""
    xs = [v for v in values if v is not None]
    if len(xs) < 2:
        return [None] * len(values)
    mean = sum(xs) / len(xs)
    var = sum((x - mean) ** 2 for x in xs) / len(xs)
    sd = var ** 0.5
    if sd == 0:
        return [0.0 if v is not None else None for v in values]
    return [None if v is None else (v - mean) / sd for v in values]


def percentile_rank_within_group(values: Sequence[float | None]) -> list[float | None]:
    """Mid-rank percentile: (# strictly less + 0.5 * # equal) / N.

    Returns 0.5 when the group has a single non-null value (median default).
    None inputs → None outputs.
    """
    xs = [v for v in values if v is not None]
    n = len(xs)
    if n == 0:
        return [None] * len(values)
    if n == 1:
        return [0.5 if v is not None else None for v in values]
    out: list[float | None] = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        lt = sum(1 for x in xs if x < v)
        eq = sum(1 for x in xs if x == v)
        out.append((lt + 0.5 * eq) / n)
    return out


# ---------------------------------------------------------------------------
# Per-asset raw compute
# ---------------------------------------------------------------------------


def _is_stale(latest_bar_ts: dt.datetime | None, as_of: dt.date) -> bool:
    if latest_bar_ts is None:
        return False
    latest_date = latest_bar_ts.date()
    age_days = (as_of - latest_date).days
    return age_days > STALE_DAYS


def compute_raw_features(
    asset_id: str,
    asset_bars: Sequence[BarView],
    spy_bars: Sequence[BarView],
    as_of: dt.date,
) -> RawFeatures:
    """Compute raw (non-cross-sectional) features from pre-as_of bars."""
    if not asset_bars:
        return RawFeatures(asset_id=asset_id, enough_data=False, stale_data=False)

    latest_ts = asset_bars[-1].ts
    stale = _is_stale(latest_ts, as_of)
    enough = len(asset_bars) >= MIN_BARS_ENOUGH

    closes = [b.close for b in asset_bars]
    spy_closes = [b.close for b in spy_bars] if spy_bars else []

    ret20 = _simple_return(closes, 20)
    ret60 = _simple_return(closes, 60)
    spy20 = _simple_return(spy_closes, 20) if spy_closes else None
    spy60 = _simple_return(spy_closes, 60) if spy_closes else None

    resid20 = None if (ret20 is None or spy20 is None) else ret20 - spy20
    resid60 = None if (ret60 is None or spy60 is None) else ret60 - spy60

    sma20_ = sma(closes, 20)
    sma200_ = sma(closes, 200)
    atr14 = atr(asset_bars, period=14)
    close_now = _f(closes[-1]) if closes else None

    trend_strength = None
    if sma20_ is not None and atr14 is not None and atr14 > 0 and close_now is not None:
        trend_strength = (close_now - sma20_) / atr14

    price_vs_200 = None
    if sma200_ is not None and sma200_ > 0 and close_now is not None:
        price_vs_200 = (close_now - sma200_) / sma200_

    atr_pct = None
    if atr14 is not None and close_now is not None and close_now > 0:
        atr_pct = atr14 / close_now

    adv20 = avg_dollar_volume(asset_bars, n=20)

    return RawFeatures(
        asset_id=asset_id,
        enough_data=enough,
        stale_data=stale,
        residual_return_20d=resid20,
        residual_return_60d=resid60,
        return_60d=ret60,
        trend_strength_20d=trend_strength,
        price_vs_200sma=price_vs_200,
        atr_percent_14=atr_pct,
        avg_dollar_volume_20d=adv20,
        earnings_proximity_days=None,  # populated when earnings feed ships
    )


# ---------------------------------------------------------------------------
# Cross-section assembly
# ---------------------------------------------------------------------------


def _coerce_dec(v: float | None) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(round(v, 6)))
    except Exception:  # noqa: BLE001
        return None


def _coerce_dec_int(v: float | None) -> Decimal | None:
    if v is None:
        return None
    return Decimal(str(round(v, 2)))


def finalize_snapshots(
    raws: Sequence[RawFeatures],
    sector_by_asset: dict[str, str],
    as_of: dt.date,
) -> list[SnapshotRow]:
    """Take per-asset raws, apply cross-section transforms, emit snapshot rows.

    Assets with ``enough_data=False`` or ``stale_data=True`` are excluded
    from z-score / sector-rank denominators but still produce a row with
    NULL cross-section fields + raw fields where computable.
    """
    # Eligible cohort for cross-section math
    eligible = [r for r in raws if r.enough_data and not r.stale_data]

    # Z-score residual momentums over the eligible cohort
    rm20_inputs = [r.residual_return_20d for r in eligible]
    rm60_inputs = [r.residual_return_60d for r in eligible]
    rm20_z = zscore_list(rm20_inputs)
    rm60_z = zscore_list(rm60_inputs)
    z20_by_asset = {r.asset_id: z for r, z in zip(eligible, rm20_z)}
    z60_by_asset = {r.asset_id: z for r, z in zip(eligible, rm60_z)}

    # Sector-relative percentile rank on raw 60d return within each sector
    by_sector: dict[str, list[RawFeatures]] = {}
    for r in eligible:
        bucket = sector_by_asset.get(r.asset_id, "unknown")
        by_sector.setdefault(bucket, []).append(r)

    sector_rank_by_asset: dict[str, float | None] = {}
    for bucket, cohort in by_sector.items():
        vals = [r.return_60d for r in cohort]
        ranks = percentile_rank_within_group(vals)
        for r, rank in zip(cohort, ranks):
            sector_rank_by_asset[r.asset_id] = rank

    out: list[SnapshotRow] = []
    for r in raws:
        row = SnapshotRow(
            as_of_date=as_of,
            asset_id=r.asset_id,
            enough_data=r.enough_data,
            stale_data=r.stale_data,
            feature_set_hash=FEATURE_SET_HASH,
            trend_strength_20d=_coerce_dec(r.trend_strength_20d),
            price_vs_200sma=_coerce_dec(r.price_vs_200sma),
            atr_percent_14=_coerce_dec(r.atr_percent_14),
            avg_dollar_volume_20d=_coerce_dec_int(r.avg_dollar_volume_20d),
            earnings_proximity_days=r.earnings_proximity_days,
        )
        if r.enough_data and not r.stale_data:
            row.residual_momentum_20d = _coerce_dec(z20_by_asset.get(r.asset_id))
            row.residual_momentum_60d = _coerce_dec(z60_by_asset.get(r.asset_id))
            row.sector_relative_rank = _coerce_dec(sector_rank_by_asset.get(r.asset_id))
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# DB-facing orchestrator
# ---------------------------------------------------------------------------


def _bars_upto(
    session: Session, asset_id: str, as_of: dt.date,
) -> list[BarView]:
    """All daily bars with ``ts < datetime(as_of, 00:00, UTC)``."""
    upper = dt.datetime.combine(as_of, dt.time(0, 0, 0), tzinfo=dt.timezone.utc)
    stmt = (
        select(PriceBar)
        .where(
            PriceBar.asset_id == asset_id,
            PriceBar.timeframe == "1d",
            PriceBar.ts < upper,
        )
        .order_by(PriceBar.ts.asc())
    )
    out: list[BarView] = []
    for b in session.scalars(stmt):
        if b.close is None or b.high is None or b.low is None or b.open is None:
            continue
        out.append(BarView(
            ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close,
            volume=b.volume,
        ))
    return out


def _spy_asset_id(session: Session) -> str | None:
    row = session.execute(
        select(Asset.id).where(Asset.symbol == BENCHMARK_SYMBOL)
    ).first()
    return row[0] if row else None


def _sector_bucket(asset: Asset) -> str:
    return asset.sector or asset.asset_class


def _universe_assets(
    session: Session, universe_name: str, as_of: dt.date,
) -> list[Asset]:
    from sqlalchemy import or_

    stmt = (
        select(Asset)
        .join(UniverseMembership, UniverseMembership.asset_id == Asset.id)
        .where(
            UniverseMembership.universe_name == universe_name,
            UniverseMembership.start_date <= as_of,
            or_(
                UniverseMembership.end_date.is_(None),
                UniverseMembership.end_date >= as_of,
            ),
        )
        .order_by(Asset.symbol.asc())
    )
    return list(session.scalars(stmt))


def compute_universe_snapshots(
    session: Session, universe_name: str, as_of: dt.date,
) -> list[SnapshotRow]:
    """Compute factor rows for every asset in ``universe_name`` active on
    ``as_of``. Cross-section transforms applied. SPY is always loaded as
    benchmark regardless of universe membership."""
    assets = _universe_assets(session, universe_name, as_of)
    if not assets:
        return []

    spy_id = _spy_asset_id(session)
    spy_bars: list[BarView] = []
    if spy_id is not None:
        spy_bars = _bars_upto(session, spy_id, as_of)

    raws: list[RawFeatures] = []
    sector_by_asset: dict[str, str] = {}
    for a in assets:
        bars = _bars_upto(session, a.id, as_of)
        raws.append(compute_raw_features(a.id, bars, spy_bars, as_of))
        sector_by_asset[a.id] = _sector_bucket(a)

    return finalize_snapshots(raws, sector_by_asset, as_of)
