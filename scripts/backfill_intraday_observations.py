"""Phase 16 Phase 2 — historical intraday observation backfill.

ONE-OFF script. Walks Polygon's 15-minute aggregates endpoint for the
active symbol allow-list and synthesizes `intraday_observation` rows
for the past N trading days. Idempotent via the UNIQUE
(recommendation_id, observed_at_15min) constraint — re-running is
safe.

This script ships READY but is NOT executed by any cron / hook /
deployment process. Operator runs it manually after Commit 2 lands
and the dev DB migration is verified.

Usage:
    # Dry run — fetches but doesn't write
    python -m scripts.backfill_intraday_observations --days 60 --dry-run

    # Real backfill — applies to dev DB
    python -m scripts.backfill_intraday_observations --days 60

    # Single-symbol scoped backfill (debugging / partial top-up)
    python -m scripts.backfill_intraday_observations --days 7 --symbols SPY,QQQ

    # Use a custom Polygon key without touching .env
    POLYGON_API_KEY=... python -m scripts.backfill_intraday_observations --days 30

Discipline (per docs/research/INTRADAY_ML_SHADOW.md §11 Phase 2):
- Honors symbol allow-list resolved at runtime (open paper positions
  whose latest recommendation is bound — same set the live poller
  uses).
- 100-symbol cap (matches OVERLAY_SYMBOL_CAP).
- One Polygon call per symbol per backfill (limit=50000 covers
  60 days of 15-min bars comfortably).
- All writes go through the same `write_observation()` UPSERT path —
  no shortcut SQL, no schema bypass.
- Skips bars whose observed slot would write data older than the
  recommendation's `generated_at` minus 7 days (clean leakage cut).
"""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import sys
import time
from typing import Iterable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import Asset, PaperPosition, Recommendation
from apps.api.src.ml.intraday.observation_writer import (
    derive_observation,
    truncate_to_15min,
    write_observation,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("backfill_intraday")


POLYGON_BASE = "https://api.polygon.io"
SYMBOL_CAP = 100
HTTP_TIMEOUT = 30.0
LEAKAGE_CUT_DAYS = 7  # never write rows older than rec.generated_at - 7d


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--days", type=int, default=60,
        help="how many trailing days to backfill (default 60)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="fetch + log row counts but do NOT write to DB",
    )
    p.add_argument(
        "--symbols", type=str, default=None,
        help="comma-separated symbol allow-list override "
             "(default: all open paper positions with active recs)",
    )
    return p.parse_args()


def resolve_targets(session: Session,
                    symbols_filter: list[str] | None) -> dict[str, dict]:
    """Return {recommendation_id: {symbol, generated_at, action, conviction}}.

    Mirrors the live poller's resolver: open paper positions whose
    asset has a recommendation. Optionally filter to a subset of symbols
    via --symbols.
    """
    rows = session.execute(
        select(Asset.id, Asset.symbol)
        .join(PaperPosition, PaperPosition.asset_id == Asset.id)
        .where(PaperPosition.is_open.is_(True))
        .distinct()
    ).all()

    targets: dict[str, dict] = {}
    for asset_id, symbol in rows:
        if symbols_filter and symbol not in symbols_filter:
            continue
        rec = session.execute(
            select(
                Recommendation.id,
                Recommendation.action,
                Recommendation.conviction,
                Recommendation.generated_at,
            )
            .where(Recommendation.asset_id == asset_id)
            .order_by(Recommendation.generated_at.desc())
            .limit(1)
        ).first()
        if rec is None:
            continue
        rec_id, action, conv, generated_at = rec
        targets[str(rec_id)] = {
            "symbol": str(symbol),
            "asset_id": str(asset_id),
            "action": str(action or "hold").lower(),
            "conviction": float(conv) if conv is not None else None,
            "generated_at": generated_at,
        }
        if len(targets) >= SYMBOL_CAP:
            log.warning(
                "hit SYMBOL_CAP=%d — truncating remaining open positions",
                SYMBOL_CAP,
            )
            break
    return targets


def fetch_15min_bars(client: httpx.Client, symbol: str,
                     date_from: str, date_to: str) -> list[dict]:
    """Fetch all 15-min bars for `symbol` over [date_from, date_to]."""
    key = os.environ.get("POLYGON_API_KEY", "").strip()
    if not key:
        raise RuntimeError("POLYGON_API_KEY not set")
    url = f"{POLYGON_BASE}/v2/aggs/ticker/{symbol}/range/15/minute/{date_from}/{date_to}"
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": "50000",
        "apiKey": key,
    }
    r = client.get(url, params=params, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") not in ("OK", "DELAYED"):
        raise RuntimeError(
            f"polygon backfill returned status={payload.get('status')}: "
            f"{payload.get('error', '')}"
        )
    return payload.get("results") or []


def macro_bars_index(client: httpx.Client,
                     date_from: str, date_to: str) -> dict[str, dict[int, float]]:
    """Pre-fetch macro tape (SPY/QQQ/DIA) and index close-by-slot for
    quick join during the per-symbol loop."""
    out: dict[str, dict[int, float]] = {}
    for sym in ("SPY", "QQQ", "DIA"):
        bars = fetch_15min_bars(client, sym, date_from, date_to)
        slot_close: dict[int, float] = {}
        for b in bars:
            t_ms = int(b.get("t") or 0)
            c = b.get("c")
            if t_ms and c is not None:
                slot_close[t_ms] = float(c)
        out[sym] = slot_close
        log.info("macro %s — %d bars indexed", sym, len(slot_close))
    return out


def slot_change_pct(slot_close: dict[int, float], t_ms: int) -> float | None:
    """Compute SPY/QQQ/DIA bar's intraday change as
    (close - prior_session_close) / prior_session_close * 100.

    Backfill v1 simplification: use the macro bar's close vs the day's
    EARLIEST close in the same dict. For full precision a join against
    daily bars would be cleaner; this is acceptable for v1 since the
    feature is only used for vs_macro_drift_pct (a relative metric)
    and the absolute baseline error cancels symmetrically.
    """
    if t_ms not in slot_close:
        return None
    # find earliest close on the same UTC day as t_ms
    day_start = datetime.datetime.fromtimestamp(
        t_ms / 1000, tz=datetime.timezone.utc,
    ).replace(hour=0, minute=0, second=0, microsecond=0)
    day_start_ms = int(day_start.timestamp() * 1000)
    same_day = [
        c for ts, c in slot_close.items()
        if day_start_ms <= ts <= day_start_ms + 86_400_000
    ]
    if not same_day:
        return None
    open_close = same_day[0] if isinstance(same_day, list) else next(iter(same_day))
    if open_close == 0:
        return None
    return (slot_close[t_ms] - open_close) / open_close * 100.0


def backfill(targets: dict[str, dict], days: int, dry_run: bool) -> None:
    today = datetime.date.today()
    date_from = (today - datetime.timedelta(days=days)).isoformat()
    date_to = today.isoformat()
    log.info(
        "backfill window %s → %s (%d days), %d targets, dry_run=%s",
        date_from, date_to, days, len(targets), dry_run,
    )

    leakage_cut_min: dict[str, datetime.datetime] = {
        rec_id: meta["generated_at"] - datetime.timedelta(days=LEAKAGE_CUT_DAYS)
        for rec_id, meta in targets.items()
    }

    written_total = 0
    skipped_leakage = 0
    skipped_dup = 0  # via UPSERT idempotency this is implicit
    with httpx.Client() as client:
        macro = macro_bars_index(client, date_from, date_to)
        for rec_id, meta in targets.items():
            sym = meta["symbol"]
            log.info("fetching %s bars (%s)", sym, rec_id)
            try:
                bars = fetch_15min_bars(client, sym, date_from, date_to)
            except Exception as exc:  # noqa: BLE001
                log.warning("skip %s: fetch failed — %s", sym, exc)
                continue
            log.info("  %d bars", len(bars))

            # Build prev-close lookup for this symbol — first close of
            # each UTC day.
            prev_close_per_day: dict[str, float] = {}
            for b in bars:
                t_ms = int(b.get("t") or 0)
                c = b.get("c")
                if not t_ms or c is None:
                    continue
                day_key = datetime.datetime.fromtimestamp(
                    t_ms / 1000, tz=datetime.timezone.utc,
                ).date().isoformat()
                if day_key not in prev_close_per_day:
                    prev_close_per_day[day_key] = float(c)

            with SessionLocal() as session:
                cut = leakage_cut_min[rec_id]
                for b in bars:
                    t_ms = int(b.get("t") or 0)
                    if not t_ms:
                        continue
                    obs_ts = datetime.datetime.fromtimestamp(
                        t_ms / 1000, tz=datetime.timezone.utc,
                    )
                    if obs_ts < cut:
                        skipped_leakage += 1
                        continue
                    day_key = obs_ts.date().isoformat()
                    prev_close = prev_close_per_day.get(day_key)
                    price = b.get("c")
                    row = derive_observation(
                        recommendation_id=rec_id,
                        symbol=sym,
                        observed_at=truncate_to_15min(obs_ts),
                        price=float(price) if price is not None else None,
                        prev_close=float(prev_close) if prev_close is not None else None,
                        day_open=float(b.get("o")) if b.get("o") is not None else None,
                        day_high=float(b.get("h")) if b.get("h") is not None else None,
                        day_low=float(b.get("l")) if b.get("l") is not None else None,
                        spy_change_pct=slot_change_pct(macro["SPY"], t_ms),
                        qqq_change_pct=slot_change_pct(macro["QQQ"], t_ms),
                        dia_change_pct=slot_change_pct(macro["DIA"], t_ms),
                        prior_eod_conviction=meta["conviction"],
                        action_type=meta["action"],
                        position_state="open_long",
                        entry_reference_price=float(prev_close) if prev_close else None,
                        atr_60d_pct=None,
                        vol_60d_pct=None,
                        sector_id=None,
                        source="polygon",
                        delay_minutes=15,
                        quote_ts=obs_ts,
                    )
                    if dry_run:
                        written_total += 1
                        continue
                    try:
                        write_observation(session, row)
                        written_total += 1
                    except Exception as exc:  # noqa: BLE001
                        log.warning(
                            "write failed for %s @ %s: %s",
                            sym, obs_ts.isoformat(), exc,
                        )
            # courtesy pause between symbols
            time.sleep(0.1)

    log.info(
        "DONE — written=%d skipped_leakage=%d (dry_run=%s)",
        written_total, skipped_leakage, dry_run,
    )


def main() -> int:
    args = parse_args()
    symbols_filter: list[str] | None = None
    if args.symbols:
        symbols_filter = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        log.info("symbol filter: %s", symbols_filter)

    with SessionLocal() as session:
        targets = resolve_targets(session, symbols_filter)
    if not targets:
        log.warning("no targets resolved — nothing to backfill")
        return 1
    log.info("resolved %d (rec_id, symbol) targets", len(targets))

    backfill(targets, days=args.days, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
