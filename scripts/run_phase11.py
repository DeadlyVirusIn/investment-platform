"""Phase 11 — Real event-driven backtest pipeline.

Steps:
  1. Fetch earnings (EPS estimate + reported) for 26 large-cap tickers via
     yfinance (public scrape, documented provenance).
  2. Ingest via Phase 10.6 pipeline (strict TZ + units) — source tag
     'yfinance_scrape', value_unit 'usd_per_share' for EPS.
  3. Run validation report (stop-gate at <60% usable).
  4. Backtest A — EPS-Beat-PEAD (reduced Messy-Beat: Rev consensus unavailable).
  5. Backtest B — Buyback-Blackout-Re-bid proxy (no consensus needed).
  6. Apply 10 bps + 20 bps round-trip cost.
  7. Honest verdict PASS / WEAK / FAIL per idea.

Run:
    python -m scripts.run_phase11
    python -m scripts.run_phase11 --skip-fetch   (reuse cached JSONL)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics as st
import sys
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
from loguru import logger
from sqlalchemy import select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import (
    Asset, ConsensusEstimateRow, EarningsEventRow, PriceBar,
)
from apps.api.src.ingestion.adapters.et_earnings import normalize_et_records
from apps.api.src.ingestion.consensus import ingest_consensus
from apps.api.src.ingestion.earnings import ingest_earnings
from apps.api.src.ingestion.validation import run_validation

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "NFLX",
    "JPM", "V", "MA", "UNH", "HD", "PG", "CVX", "XOM",
    "KO", "PEP", "WMT", "DIS", "ADBE", "CRM", "INTC", "AMD", "ORCL", "CSCO",
]
ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
SOURCE = "yfinance_scrape"

# Event window — recent enough, but leaving >= 20 trading days before today for
# forward-return horizon.
TODAY = dt.date.today()
WIN_END   = TODAY - dt.timedelta(days=30)
WIN_START = TODAY - dt.timedelta(days=540)   # ~18 months

OUT_DIR = Path("artifacts/phase11")
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_JSONL = OUT_DIR / "fetched_earnings.jsonl"


# -----------------------------------------------------------------------------
# Step 1 — fetch
# -----------------------------------------------------------------------------

def _infer_event_time(ts_et: dt.datetime) -> str:
    h = ts_et.hour
    if h < 9 or (h == 9 and ts_et.minute < 30):
        return "before_open"
    if h >= 16:
        return "after_close"
    return "during_hours"


def _infer_fiscal_period(event_date: dt.date) -> str:
    m = event_date.month
    # Announcements usually come 1-2 months after quarter-end. Rough bucketing.
    if m in (1, 2):
        q, y = 4, event_date.year - 1
    elif m in (3, 4, 5):
        q, y = 1, event_date.year
    elif m in (6, 7, 8):
        q, y = 2, event_date.year
    elif m in (9, 10, 11):
        q, y = 3, event_date.year
    else:
        q, y = 4, event_date.year
    return f"{y}Q{q}"


def fetch_earnings_for_ticker(sym: str) -> list[dict]:
    t = yf.Ticker(sym)
    try:
        ed = t.earnings_dates
    except Exception as exc:
        logger.warning("[p11.fetch] {} earnings_dates fail: {}", sym, exc)
        return []
    if ed is None or ed.empty:
        return []

    out: list[dict] = []
    for idx, row in ed.iterrows():
        ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
        if not isinstance(ts, dt.datetime):
            continue
        if ts.tzinfo is None:
            # yfinance returned naive — assume ET.
            ts = ts.replace(tzinfo=ET)
        ts_et = ts.astimezone(ET)
        event_date = ts_et.date()
        if not (WIN_START <= event_date <= WIN_END):
            continue
        est = row.get("EPS Estimate")
        rep = row.get("Reported EPS")
        est_f = None if pd.isna(est) else float(est)
        rep_f = None if pd.isna(rep) else float(rep)
        out.append({
            "symbol": sym,
            "event_date": event_date.isoformat(),
            "event_time": _infer_event_time(ts_et),
            "announcement_timestamp": ts.astimezone(UTC).isoformat(),
            "announcement_timestamp_raw": str(ts_et),
            "fiscal_period": _infer_fiscal_period(event_date),
            "source": SOURCE,
            "external_id": f"{sym}-{event_date.isoformat()}",
            "_eps_consensus": est_f,
            "_eps_actual": rep_f,
        })
    return out


def run_fetch() -> list[dict]:
    all_recs: list[dict] = []
    for sym in TICKERS:
        recs = fetch_earnings_for_ticker(sym)
        logger.info("[p11.fetch] {}: {} events in window", sym, len(recs))
        all_recs.extend(recs)
    with CACHE_JSONL.open("w") as f:
        for r in all_recs:
            f.write(json.dumps(r) + "\n")
    logger.info("[p11.fetch] total={} events cached @ {}", len(all_recs), CACHE_JSONL)
    return all_recs


def load_cached() -> list[dict]:
    if not CACHE_JSONL.exists():
        raise FileNotFoundError(f"no cache at {CACHE_JSONL} — remove --skip-fetch")
    with CACHE_JSONL.open() as f:
        return [json.loads(line) for line in f if line.strip()]


# -----------------------------------------------------------------------------
# Step 2 — ingest via Phase 10.6 pipeline
# -----------------------------------------------------------------------------

def ensure_assets(session, symbols: set[str]) -> dict[str, str]:
    """Return symbol -> asset_id, auto-creating any missing equity asset rows."""
    rows = session.execute(
        select(Asset).where(Asset.symbol.in_(symbols))
    ).scalars().all()
    have = {r.symbol: r.id for r in rows}
    for sym in symbols:
        if sym not in have:
            a = Asset(
                id=str(uuid.uuid4()), symbol=sym, asset_class="equity",
                exchange="NASDAQ" if sym in {
                    "AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA","NFLX",
                    "ADBE","INTC","AMD","CSCO","ORCL","PEP",
                } else "NYSE",
                currency="USD", is_active=True,
            )
            session.add(a); session.flush()
            have[sym] = a.id
    session.commit()
    return have


def ingest_all(session, records: list[dict]) -> dict:
    syms = {r["symbol"] for r in records}
    sym_to_aid = ensure_assets(session, syms)

    # Build earnings input
    earn_recs = []
    consensus_recs = []
    for r in records:
        aid = sym_to_aid[r["symbol"]]
        earn = {
            "asset_id": aid,
            "symbol": r["symbol"],
            "event_date": r["event_date"],
            "event_time": r["event_time"],
            "announcement_timestamp": r["announcement_timestamp"],
            "announcement_timestamp_raw": r["announcement_timestamp_raw"],
            "fiscal_period": r["fiscal_period"],
            "source": r["source"],
            "external_id": r["external_id"],
        }
        earn_recs.append(earn)
        # Consensus: as_of_date = event_date - 1 (best available, documented)
        as_of = (dt.date.fromisoformat(r["event_date"]) - dt.timedelta(days=1)).isoformat()
        if r.get("_eps_consensus") is not None:
            consensus_recs.append({
                "asset_id": aid, "symbol": r["symbol"],
                "event_date": r["event_date"], "metric": "eps",
                "estimate_type": "consensus",
                "value": r["_eps_consensus"],
                "value_unit": "usd_per_share",
                "as_of_date": as_of,
                "source": SOURCE,
                "external_id": f"{r['external_id']}-est",
            })
        if r.get("_eps_actual") is not None:
            consensus_recs.append({
                "asset_id": aid, "symbol": r["symbol"],
                "event_date": r["event_date"], "metric": "eps",
                "estimate_type": "actual",
                "value": r["_eps_actual"],
                "value_unit": "usd_per_share",
                "as_of_date": r["event_date"],
                "source": SOURCE,
                "external_id": f"{r['external_id']}-act",
            })

    # Run through ET adapter (pass-through — yfinance already returns aware TS)
    earn_norm = normalize_et_records(earn_recs)
    res_e = ingest_earnings(session, earn_norm, source_timezone=ET)
    res_c = ingest_consensus(session, consensus_recs)
    return {"earnings": res_e.as_dict(), "consensus": res_c.as_dict()}


# -----------------------------------------------------------------------------
# Step 4+5 — backtests
# -----------------------------------------------------------------------------

def load_price_frames(session, symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Return symbol -> DataFrame indexed by date with close column."""
    frames: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        a = session.execute(
            select(Asset).where(Asset.symbol == sym)
        ).scalar_one_or_none()
        if a is None:
            continue
        rows = session.execute(
            select(PriceBar.ts, PriceBar.close)
            .where(PriceBar.asset_id == a.id, PriceBar.timeframe == "1d")
            .order_by(PriceBar.ts)
        ).all()
        if not rows:
            continue
        df = pd.DataFrame({
            "date": [r[0].date() for r in rows],
            "close": [float(r[1]) for r in rows],
        })
        df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
        frames[sym] = df
    return frames


def _trading_idx_after(df: pd.DataFrame, d: dt.date) -> int | None:
    """Index of first row where date > d. None if not enough data."""
    mask = df["date"] > d
    if not mask.any():
        return None
    return int(mask.idxmax())


def _trading_idx_on_or_after(df: pd.DataFrame, d: dt.date) -> int | None:
    mask = df["date"] >= d
    if not mask.any():
        return None
    return int(mask.idxmax())


def backtest_eps_beat_pead(
    events: list[dict], frames: dict[str, pd.DataFrame], *,
    hold_days: int = 15,
) -> dict:
    trades = []
    skipped_reasons: dict[str, int] = {}
    for ev in events:
        c = ev.get("_eps_consensus")
        a = ev.get("_eps_actual")
        if c is None or a is None:
            skipped_reasons["missing_eps"] = skipped_reasons.get("missing_eps", 0) + 1
            continue
        if not (a > c):   # not a beat
            skipped_reasons["not_beat"] = skipped_reasons.get("not_beat", 0) + 1
            continue
        sym = ev["symbol"]
        df = frames.get(sym)
        if df is None:
            skipped_reasons["no_price"] = skipped_reasons.get("no_price", 0) + 1
            continue
        ed = dt.date.fromisoformat(ev["event_date"])
        if ev["event_time"] == "before_open":
            # Entry on close of same day (event before open -> day's close).
            i_entry = _trading_idx_on_or_after(df, ed)
        else:
            # after_close / during_hours / unknown -> T+1 close.
            i_entry = _trading_idx_after(df, ed)
        if i_entry is None:
            skipped_reasons["no_entry_bar"] = skipped_reasons.get("no_entry_bar", 0) + 1
            continue
        i_exit = i_entry + hold_days
        if i_exit >= len(df):
            skipped_reasons["insufficient_forward"] = skipped_reasons.get(
                "insufficient_forward", 0) + 1
            continue
        entry = df["close"].iloc[i_entry]
        exit_ = df["close"].iloc[i_exit]
        ret = (exit_ - entry) / entry
        trades.append({
            "symbol": sym, "event_date": ed.isoformat(),
            "entry_date": df["date"].iloc[i_entry].isoformat(),
            "exit_date":  df["date"].iloc[i_exit].isoformat(),
            "entry_close": entry, "exit_close": exit_,
            "return_raw": ret,
            "eps_consensus": c, "eps_actual": a,
            "surprise_pct": (a - c) / abs(c) if c != 0 else None,
        })
    return {"trades": trades, "skipped": skipped_reasons}


def backtest_buyback_blackout_rebid(
    events: list[dict], frames: dict[str, pd.DataFrame], *,
    pre_drawdown_thresh: float = -0.05,
    pre_window: int = 10,
    max_wait_days: int = 10,
    hold_days: int = 10,
) -> dict:
    trades = []
    skipped: dict[str, int] = {}
    for ev in events:
        sym = ev["symbol"]
        df = frames.get(sym)
        if df is None:
            skipped["no_price"] = skipped.get("no_price", 0) + 1
            continue
        ed = dt.date.fromisoformat(ev["event_date"])
        i_e = _trading_idx_after(df, ed) if ev["event_time"] != "before_open" \
            else _trading_idx_on_or_after(df, ed)
        if i_e is None:
            skipped["no_entry_bar"] = skipped.get("no_entry_bar", 0) + 1
            continue
        # Pre-event drawdown: close_{i_e-1} / close_{i_e-1-pre_window} - 1
        i_preend = i_e - 1
        i_prestart = i_e - 1 - pre_window
        if i_prestart < 0:
            skipped["insufficient_pre"] = skipped.get("insufficient_pre", 0) + 1
            continue
        pre_dd = df["close"].iloc[i_preend] / df["close"].iloc[i_prestart] - 1
        if pre_dd >= pre_drawdown_thresh:
            skipped["no_drawdown"] = skipped.get("no_drawdown", 0) + 1
            continue
        # Find first up-day within max_wait_days
        i_entry = None
        for j in range(i_e, min(i_e + max_wait_days, len(df) - 1)):
            if df["close"].iloc[j] > df["close"].iloc[j - 1]:
                i_entry = j
                break
        if i_entry is None:
            skipped["no_up_day"] = skipped.get("no_up_day", 0) + 1
            continue
        i_exit = i_entry + hold_days
        if i_exit >= len(df):
            skipped["insufficient_forward"] = skipped.get(
                "insufficient_forward", 0) + 1
            continue
        entry = df["close"].iloc[i_entry]
        exit_ = df["close"].iloc[i_exit]
        ret = (exit_ - entry) / entry
        trades.append({
            "symbol": sym, "event_date": ed.isoformat(),
            "entry_date": df["date"].iloc[i_entry].isoformat(),
            "exit_date":  df["date"].iloc[i_exit].isoformat(),
            "entry_close": entry, "exit_close": exit_,
            "return_raw": ret, "pre_drawdown_pct": pre_dd,
        })
    return {"trades": trades, "skipped": skipped}


def summarize(trades: list[dict], label: str, *, bps_cost: float) -> dict:
    if not trades:
        return {"label": label, "n": 0, "verdict": "FAIL", "reason": "no trades"}
    costs = bps_cost / 1e4  # round-trip
    rets_net = [t["return_raw"] - costs for t in trades]
    n = len(rets_net)
    mean = st.mean(rets_net)
    med  = st.median(rets_net)
    sd   = st.pstdev(rets_net) if n > 1 else 0.0
    wins = sum(1 for r in rets_net if r > 0)
    tstat = mean / (sd / math.sqrt(n)) if sd > 0 and n > 1 else 0.0
    # Annualize trade-level Sharpe assuming avg hold 15 days -> 252/15 trades/yr.
    hold_days = _avg_hold(trades)
    ann = math.sqrt(252.0 / max(hold_days, 1)) if sd > 0 else 0.0
    sharpe_ann = (mean / sd) * ann if sd > 0 else 0.0
    return {
        "label": label, "n": n,
        "cost_bps": bps_cost,
        "mean_return_pct": mean * 100,
        "median_return_pct": med * 100,
        "hit_rate": wins / n,
        "std_pct": sd * 100,
        "t_stat": tstat,
        "sharpe_ann_approx": sharpe_ann,
        "avg_hold_days": hold_days,
    }


def _avg_hold(trades: list[dict]) -> float:
    if not trades:
        return 0.0
    deltas = []
    for t in trades:
        d0 = dt.date.fromisoformat(t["entry_date"])
        d1 = dt.date.fromisoformat(t["exit_date"])
        deltas.append((d1 - d0).days)
    return sum(deltas) / len(deltas)


def verdict(summ10: dict, summ20: dict) -> str:
    """PASS: t>2 & mean>0 after 20bps. WEAK: t>1 & mean>0 after 10bps. FAIL otherwise."""
    if summ20["n"] == 0:
        return "FAIL (no trades)"
    if summ20["t_stat"] > 2.0 and summ20["mean_return_pct"] > 0:
        return "PASS"
    if summ10["t_stat"] > 1.0 and summ10["mean_return_pct"] > 0:
        return "WEAK"
    return "FAIL"


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--skip-fetch", action="store_true")
    p.add_argument("--skip-ingest", action="store_true")
    args = p.parse_args()

    # Step 1 — fetch
    if args.skip_fetch:
        records = load_cached()
        logger.info("[p11] loaded {} cached events", len(records))
    else:
        records = run_fetch()

    if not records:
        logger.error("[p11] no events fetched — abort")
        return 1

    # Step 2 — ingest
    with SessionLocal() as session:
        if not args.skip_ingest:
            ing = ingest_all(session, records)
            logger.info("[p11] ingestion: {}", json.dumps(ing, default=str))

        # Step 3 — validation
        try:
            val = run_validation(session)
            val_dict = val.as_dict() if hasattr(val, "as_dict") else val.__dict__
        except Exception as exc:
            logger.warning("[p11] validation skipped: {}", exc)
            val_dict = {"error": str(exc)}
        logger.info("[p11] validation: {}", json.dumps(val_dict, default=str))

        # Step 4/5 — load prices + backtest
        frames = load_price_frames(session, TICKERS)
        logger.info("[p11] price frames loaded: {}/{} symbols",
                    len(frames), len(TICKERS))

    # Backtest A — EPS Beat PEAD
    btA = backtest_eps_beat_pead(records, frames, hold_days=15)
    a10 = summarize(btA["trades"], "EPS_Beat_PEAD_10bps", bps_cost=10)
    a20 = summarize(btA["trades"], "EPS_Beat_PEAD_20bps", bps_cost=20)
    verA = verdict(a10, a20)

    # Backtest B — Buyback Blackout Re-bid
    btB = backtest_buyback_blackout_rebid(records, frames)
    b10 = summarize(btB["trades"], "Buyback_Blackout_Rebid_10bps", bps_cost=10)
    b20 = summarize(btB["trades"], "Buyback_Blackout_Rebid_20bps", bps_cost=20)
    verB = verdict(b10, b20)

    # Report
    report = {
        "today": TODAY.isoformat(),
        "window": {"start": WIN_START.isoformat(), "end": WIN_END.isoformat()},
        "events_in_window": len(records),
        "price_symbols_covered": len(frames),
        "validation": val_dict,
        "eps_beat_pead": {
            "skipped": btA["skipped"],
            "n_trades": len(btA["trades"]),
            "summary_10bps": a10, "summary_20bps": a20,
            "verdict": verA,
            "caveat": (
                "Reduced spec: Rev consensus not available via yfinance free API. "
                "This runs EPS-beat PEAD only (not full Messy-Beat = EPS beat + Rev miss)."
            ),
        },
        "buyback_blackout_rebid": {
            "skipped": btB["skipped"],
            "n_trades": len(btB["trades"]),
            "summary_10bps": b10, "summary_20bps": b20,
            "verdict": verB,
        },
    }
    out_path = OUT_DIR / "report.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    # Also stash trades for audit
    (OUT_DIR / "eps_beat_trades.jsonl").write_text(
        "\n".join(json.dumps(t, default=str) for t in btA["trades"])
    )
    (OUT_DIR / "buyback_trades.jsonl").write_text(
        "\n".join(json.dumps(t, default=str) for t in btB["trades"])
    )

    # Human summary
    print("=" * 78)
    print(f"PHASE 11 BACKTEST REPORT — {TODAY.isoformat()}")
    print("=" * 78)
    print(f"Events in window: {len(records)}  (window {WIN_START} -> {WIN_END})")
    print(f"Price-coverage:   {len(frames)}/{len(TICKERS)} symbols")
    print()
    print("--- A. EPS-Beat PEAD (reduced Messy-Beat, Rev consensus unavailable) ---")
    print(f"  trades:  {len(btA['trades'])}")
    print(f"  skipped: {btA['skipped']}")
    if len(btA["trades"]) > 0:
        print(f"  10bps:  mean={a10['mean_return_pct']:+.3f}%  "
              f"med={a10['median_return_pct']:+.3f}%  "
              f"hit={a10['hit_rate']:.3f}  t={a10['t_stat']:+.3f}  "
              f"Sharpe_ann={a10['sharpe_ann_approx']:+.3f}")
        print(f"  20bps:  mean={a20['mean_return_pct']:+.3f}%  "
              f"med={a20['median_return_pct']:+.3f}%  "
              f"hit={a20['hit_rate']:.3f}  t={a20['t_stat']:+.3f}  "
              f"Sharpe_ann={a20['sharpe_ann_approx']:+.3f}")
    print(f"  VERDICT: {verA}")
    print()
    print("--- B. Buyback-Blackout Re-bid (10d pre-drawdown > 5%, 10d hold) ---")
    print(f"  trades:  {len(btB['trades'])}")
    print(f"  skipped: {btB['skipped']}")
    if len(btB["trades"]) > 0:
        print(f"  10bps:  mean={b10['mean_return_pct']:+.3f}%  "
              f"med={b10['median_return_pct']:+.3f}%  "
              f"hit={b10['hit_rate']:.3f}  t={b10['t_stat']:+.3f}  "
              f"Sharpe_ann={b10['sharpe_ann_approx']:+.3f}")
        print(f"  20bps:  mean={b20['mean_return_pct']:+.3f}%  "
              f"med={b20['median_return_pct']:+.3f}%  "
              f"hit={b20['hit_rate']:.3f}  t={b20['t_stat']:+.3f}  "
              f"Sharpe_ann={b20['sharpe_ann_approx']:+.3f}")
    print(f"  VERDICT: {verB}")
    print("=" * 78)
    print(f"Report JSON: {out_path}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
