"""Options feature engine orchestrator (Phase 11D).

Reads accepted chain quotes for one (as_of_date, underlying) from
options_chain_snapshot, computes the locked feature set via pure
functions in `features.compute`, and UPSERTs one row per
(as_of_date, underlying) into options_feature_daily.

Strict invariants:
  * Reads ONLY from options_chain_snapshot (no equity / V2 tables).
  * Re-applies the same liquidity filter used at ingest time, so a
    feature row is computed against the exact same accepted set the
    downstream paper-trading layer would see.
  * Missing/insufficient data → NULL field + entry in data_quality_flags.
    NEVER fabricates values.
  * Last price is NEVER used for feature decisions; mid (or bid/ask)
    is the source of truth.
  * No strategy logic, no trade creation.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Iterable, Sequence

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import SessionLocal
from apps.api.src.options.data.liquidity_filter import filter_chain
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.features import compute as F


# ---------------------------------------------------------------------------
# Defaults — chain snapshot used per (as_of_date) is the LATEST per
# (underlying, expiry, strike, option_type) on that day.
# ---------------------------------------------------------------------------

PriceHistoryFn = Callable[[str, datetime.date], Sequence[Decimal] | None]
"""(symbol, as_of_date) → list of trailing daily closes (oldest first)
or None if unavailable."""

IVHistoryFn = Callable[[str, datetime.date], Sequence[Decimal] | None]
"""(symbol, as_of_date) → list of trailing daily ATM IV values."""

VolumeHistoryFn = Callable[[str, datetime.date], tuple[Sequence[int], Sequence[int]] | None]
"""(symbol, as_of_date) → (call_vols, put_vols) trailing daily totals."""


# ---------------------------------------------------------------------------
# Feature row dataclass — fields mirror options_feature_daily columns
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FeatureRow:
    as_of_date: datetime.date
    underlying: str
    # Phase 11D feature set
    atm_iv: Decimal | None
    iv_rank_252d: Decimal | None
    iv_percentile_252d: Decimal | None
    realized_vol_20d: Decimal | None
    vrp_30d: Decimal | None
    skew_25d: Decimal | None
    term_structure_30_90: Decimal | None
    put_call_volume_ratio: Decimal | None
    put_call_oi_ratio: Decimal | None
    unusual_call_volume_z: Decimal | None
    unusual_put_volume_z: Decimal | None
    gamma_exposure_proxy: Decimal | None
    call_wall_strike: Decimal | None
    put_wall_strike: Decimal | None
    data_quality_flags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ComputeSummary:
    underlying: str
    as_of_date: datetime.date
    n_chain_rows: int
    n_accepted: int
    flags: tuple[str, ...]
    upserted: bool


# ---------------------------------------------------------------------------
# DB helpers — read latest snapshot per natural key for the given day
# ---------------------------------------------------------------------------

_LATEST_SNAPSHOT_SQL = text(
    """
    SELECT DISTINCT ON
       (underlying, expiry, strike, option_type)
       snapshot_at_utc, underlying, expiry, strike, option_type,
       option_symbol, bid, ask, mid, last,
       volume, open_interest,
       delta, gamma, theta, vega, iv,
       quote_age_seconds, provider, provider_version
    FROM options_chain_snapshot
    WHERE underlying = :underlying
      AND snapshot_at_utc::date = :as_of_date
    ORDER BY underlying, expiry, strike, option_type,
             snapshot_at_utc DESC
    """
)


_UPSERT_FEATURE_SQL = text(
    """
    INSERT INTO options_feature_daily (
        as_of_date, underlying,
        atm_iv,
        iv_rank_252d, iv_percentile_252d,
        realized_vol_20d, vrp_30d,
        skew_25d, term_structure_30_90,
        put_call_volume_ratio, put_call_oi_ratio,
        unusual_call_volume_z, unusual_put_volume_z,
        gamma_exposure_proxy,
        call_wall_strike, put_wall_strike,
        data_quality_flags
    ) VALUES (
        :as_of_date, :underlying,
        :atm_iv,
        :iv_rank_252d, :iv_percentile_252d,
        :realized_vol_20d, :vrp_30d,
        :skew_25d, :term_structure_30_90,
        :put_call_volume_ratio, :put_call_oi_ratio,
        :unusual_call_volume_z, :unusual_put_volume_z,
        :gamma_exposure_proxy,
        :call_wall_strike, :put_wall_strike,
        CAST(:data_quality_flags AS jsonb)
    )
    ON CONFLICT ON CONSTRAINT ux_options_feature_daily_natural_key
    DO UPDATE SET
        atm_iv                  = EXCLUDED.atm_iv,
        iv_rank_252d            = EXCLUDED.iv_rank_252d,
        iv_percentile_252d      = EXCLUDED.iv_percentile_252d,
        realized_vol_20d        = EXCLUDED.realized_vol_20d,
        vrp_30d                 = EXCLUDED.vrp_30d,
        skew_25d                = EXCLUDED.skew_25d,
        term_structure_30_90    = EXCLUDED.term_structure_30_90,
        put_call_volume_ratio   = EXCLUDED.put_call_volume_ratio,
        put_call_oi_ratio       = EXCLUDED.put_call_oi_ratio,
        unusual_call_volume_z   = EXCLUDED.unusual_call_volume_z,
        unusual_put_volume_z    = EXCLUDED.unusual_put_volume_z,
        gamma_exposure_proxy    = EXCLUDED.gamma_exposure_proxy,
        call_wall_strike        = EXCLUDED.call_wall_strike,
        put_wall_strike         = EXCLUDED.put_wall_strike,
        data_quality_flags      = EXCLUDED.data_quality_flags
    """
)


def _row_to_quote(row) -> OptionChainQuote:
    return OptionChainQuote(
        snapshot_at_utc=row.snapshot_at_utc,
        underlying=row.underlying,
        expiry=row.expiry,
        strike=row.strike,
        option_type=row.option_type,
        option_symbol=row.option_symbol,
        bid=row.bid, ask=row.ask, mid=row.mid, last=row.last,
        volume=row.volume, open_interest=row.open_interest,
        delta=row.delta, gamma=row.gamma,
        theta=row.theta, vega=row.vega, iv=row.iv,
        quote_age_seconds=row.quote_age_seconds,
        provider=row.provider,
        provider_version=row.provider_version,
    )


def _read_quotes(
    session: Session,
    underlying: str,
    as_of_date: datetime.date,
) -> list[OptionChainQuote]:
    rows = session.execute(
        _LATEST_SNAPSHOT_SQL,
        {"underlying": underlying, "as_of_date": as_of_date},
    ).all()
    return [_row_to_quote(r) for r in rows]


# ---------------------------------------------------------------------------
# Pure feature builder — exposed for unit testing without a DB session
# ---------------------------------------------------------------------------

def build_feature_row(
    *,
    underlying: str,
    as_of_date: datetime.date,
    quotes: Sequence[OptionChainQuote],
    spot: Decimal | None,
    iv_history: Sequence[Decimal] | None,
    price_history: Sequence[Decimal] | None,
    call_volume_history: Sequence[int] | None,
    put_volume_history: Sequence[int] | None,
) -> FeatureRow:
    """Compute the full Phase 11D feature row from inputs.

    Pure: no DB, no I/O. Deterministic for fixed inputs.
    """
    flags: list[str] = []

    pcr_v = F.put_call_volume_ratio(quotes); flags.extend(pcr_v.flags)
    pcr_oi = F.put_call_oi_ratio(quotes);   flags.extend(pcr_oi.flags)

    atm = F.atm_iv(quotes, as_of=as_of_date, spot=spot)
    flags.extend(atm.flags)

    if iv_history is None:
        flags.append(F.FLAG_INSUFFICIENT_IV_HISTORY)
        ivr = F.FeatureValue(None)
        ivp = F.FeatureValue(None)
    else:
        ivr = F.iv_rank(atm.value, iv_history); flags.extend(ivr.flags)
        ivp = F.iv_percentile(atm.value, iv_history); flags.extend(ivp.flags)

    rv = F.realized_vol(price_history); flags.extend(rv.flags)
    vrp_v = F.vrp(atm.value, rv.value); flags.extend(vrp_v.flags)

    skew = F.skew_25_delta(quotes, as_of=as_of_date); flags.extend(skew.flags)
    term = F.term_structure(quotes, as_of=as_of_date, spot=spot)
    flags.extend(term.flags)

    if call_volume_history is None:
        flags.append(F.FLAG_INSUFFICIENT_VOL_HIST)
        ucv = F.FeatureValue(None)
        upv = F.FeatureValue(None)
    else:
        ucv = F.unusual_call_volume_z(quotes, call_volume_history)
        flags.extend(ucv.flags)
        upv = F.unusual_put_volume_z(quotes, put_volume_history or [])
        flags.extend(upv.flags)

    gex = F.gamma_exposure_proxy(quotes); flags.extend(gex.flags)
    walls = F.wall_strikes(quotes);       flags.extend(walls.flags)

    return FeatureRow(
        as_of_date=as_of_date,
        underlying=underlying,
        atm_iv=atm.value,
        iv_rank_252d=ivr.value,
        iv_percentile_252d=ivp.value,
        realized_vol_20d=rv.value,
        vrp_30d=vrp_v.value,
        skew_25d=skew.value,
        term_structure_30_90=term.value,
        put_call_volume_ratio=pcr_v.value,
        put_call_oi_ratio=pcr_oi.value,
        unusual_call_volume_z=ucv.value,
        unusual_put_volume_z=upv.value,
        gamma_exposure_proxy=gex.value,
        call_wall_strike=walls.call_wall,
        put_wall_strike=walls.put_wall,
        data_quality_flags=_dedup_in_order(flags),
    )


def _dedup_in_order(items: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return tuple(out)


# ---------------------------------------------------------------------------
# DB-bound orchestrator
# ---------------------------------------------------------------------------

def compute_features_for(
    *,
    underlying: str,
    as_of_date: datetime.date,
    spot: Decimal | None = None,
    iv_history: Sequence[Decimal] | None = None,
    price_history_fn: PriceHistoryFn | None = None,
    iv_history_fn: IVHistoryFn | None = None,
    volume_history_fn: VolumeHistoryFn | None = None,
    session_factory=SessionLocal,
) -> ComputeSummary:
    """Compute one feature row for one (underlying, as_of_date) and
    upsert it into options_feature_daily.

    The history sources are injectable callables; defaults are None,
    which produces NULLs + data_quality flags rather than fabricated
    values. This keeps the engine boundary-clean (no equity imports).
    """
    with session_factory() as session:
        raw = _read_quotes(session, underlying, as_of_date)
        n_chain_rows = len(raw)
        # Re-apply liquidity filter — features only consider accepted quotes
        accepted = filter_chain(raw).accepted

        price_hist = price_history_fn(underlying, as_of_date) if price_history_fn else None
        iv_hist = iv_history if iv_history is not None else (
            iv_history_fn(underlying, as_of_date) if iv_history_fn else None
        )
        vol_hist = volume_history_fn(underlying, as_of_date) if volume_history_fn else None
        call_vols = vol_hist[0] if vol_hist else None
        put_vols  = vol_hist[1] if vol_hist else None

        row = build_feature_row(
            underlying=underlying,
            as_of_date=as_of_date,
            quotes=accepted,
            spot=spot,
            iv_history=iv_hist,
            price_history=price_hist,
            call_volume_history=call_vols,
            put_volume_history=put_vols,
        )

        if not accepted:
            # No accepted quotes — write a row with everything NULL +
            # NO_QUOTES flag, so downstream OOS monitoring can detect
            # the gap rather than guess.
            row = FeatureRow(
                as_of_date=as_of_date,
                underlying=underlying,
                atm_iv=None, iv_rank_252d=None, iv_percentile_252d=None,
                realized_vol_20d=None, vrp_30d=None, skew_25d=None,
                term_structure_30_90=None,
                put_call_volume_ratio=None, put_call_oi_ratio=None,
                unusual_call_volume_z=None, unusual_put_volume_z=None,
                gamma_exposure_proxy=None,
                call_wall_strike=None, put_wall_strike=None,
                data_quality_flags=(F.FLAG_NO_QUOTES,),
            )

        _upsert(session, row)
        session.commit()

        logger.info(
            "options feature engine: {} @ {} accepted={}/{} flags={}",
            underlying, as_of_date,
            len(accepted), n_chain_rows, list(row.data_quality_flags),
        )
        return ComputeSummary(
            underlying=underlying,
            as_of_date=as_of_date,
            n_chain_rows=n_chain_rows,
            n_accepted=len(accepted),
            flags=row.data_quality_flags,
            upserted=True,
        )


def _upsert(session: Session, row: FeatureRow) -> None:
    import json
    session.execute(
        _UPSERT_FEATURE_SQL,
        {
            "as_of_date": row.as_of_date,
            "underlying": row.underlying,
            "atm_iv": row.atm_iv,
            "iv_rank_252d": row.iv_rank_252d,
            "iv_percentile_252d": row.iv_percentile_252d,
            "realized_vol_20d": row.realized_vol_20d,
            "vrp_30d": row.vrp_30d,
            "skew_25d": row.skew_25d,
            "term_structure_30_90": row.term_structure_30_90,
            "put_call_volume_ratio": row.put_call_volume_ratio,
            "put_call_oi_ratio": row.put_call_oi_ratio,
            "unusual_call_volume_z": row.unusual_call_volume_z,
            "unusual_put_volume_z": row.unusual_put_volume_z,
            "gamma_exposure_proxy": row.gamma_exposure_proxy,
            "call_wall_strike": row.call_wall_strike,
            "put_wall_strike": row.put_wall_strike,
            "data_quality_flags": json.dumps(list(row.data_quality_flags)),
        },
    )
