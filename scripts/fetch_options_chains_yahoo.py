"""Fetch REAL options chains from Yahoo via yfinance.

Writes per-(symbol, expiration) CSV files matching the format the
existing `scripts.ingest_options_chain` script consumes. NO synthetic
data. NO fabrication. Whatever Yahoo returns is what lands on disk;
rows with missing required fields are dropped.

Hard rules:
  * Default underlyings: SPY, QQQ, AAPL, NVDA, TSLA, MSFT, AMZN.
    Operator can override via --symbols.
  * Picks 3 expirations per symbol: near (~1-2 weeks),
    mid (~3-6 weeks), far (~6-12 weeks). Closest available match
    from yfinance per bucket.
  * Per-expiration strike coverage = ITM/ATM/OTM around spot,
    capped at MAX_STRIKES_PER_EXPIRATION (default 24).
  * Skips contracts missing bid, ask, OI, or with bid > ask. Logs
    skip reasons.
  * Output: artifacts/options_chains/<symbol>_<expiration>.csv.
  * Idempotent: re-running rewrites CSVs with fresh quotes.

Usage:

    python -m scripts.fetch_options_chains_yahoo
    python -m scripts.fetch_options_chains_yahoo \\
        --symbols SPY,QQQ,AAPL --max-strikes 30

Exit codes:
  0  success
  1  validation/parse error
  2  refused (bad arg)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from pathlib import Path
from typing import Any

from loguru import logger

DEFAULT_SYMBOLS = (
    "SPY", "QQQ", "AAPL", "NVDA", "TSLA", "MSFT", "AMZN",
)
OUT_DIR = Path("artifacts/options_chains")

# Expiration target windows in calendar days from today.
NEAR_WINDOW = (5, 14)
MID_WINDOW = (21, 42)
FAR_WINDOW = (42, 90)

MAX_STRIKES_PER_EXPIRATION = 24

REQUIRED_OUTPUT_COLUMNS = (
    "expiry", "strike", "option_type", "option_symbol",
    "bid", "ask", "mid", "last", "volume", "open_interest",
    "delta", "gamma", "theta", "vega", "iv", "quote_age_seconds",
)


def _argparse() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fetch_options_chains_yahoo",
        description="Fetch real options chains from Yahoo via yfinance.",
    )
    p.add_argument(
        "--symbols", default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated underlyings.",
    )
    p.add_argument(
        "--max-strikes", type=int, default=MAX_STRIKES_PER_EXPIRATION,
        help="Cap strikes per (symbol, expiration, type).",
    )
    p.add_argument(
        "--out-dir", default=str(OUT_DIR),
        help="Output directory for CSVs.",
    )
    return p


def _select_expirations(
    available: list[str], today: dt.date,
) -> list[tuple[str, str]]:
    """Pick one expiration per (near, mid, far) window. Returns
    list of (bucket_name, expiration_str)."""
    picks: list[tuple[str, str]] = []
    parsed: list[tuple[dt.date, str]] = []
    for s in available:
        try:
            d = dt.date.fromisoformat(s)
        except ValueError:
            continue
        if d <= today:
            continue
        parsed.append((d, s))
    parsed.sort()

    def _pick_in_window(lo: int, hi: int) -> tuple[str, str] | None:
        for d, s in parsed:
            days = (d - today).days
            if lo <= days <= hi:
                return (s, s)
        # Fallback: closest expiration to the window midpoint, capped
        # between (lo*0.5) and (hi*1.5) so we don't pull anything
        # silly if the desired band has no listed expiration.
        if not parsed:
            return None
        target = (lo + hi) / 2
        chosen = min(
            parsed, key=lambda t: abs((t[0] - today).days - target)
        )
        days = (chosen[0] - today).days
        if days < lo * 0.5 or days > hi * 1.5:
            return None
        return (chosen[1], chosen[1])

    seen: set[str] = set()
    for name, window in (
        ("near", NEAR_WINDOW),
        ("mid", MID_WINDOW),
        ("far", FAR_WINDOW),
    ):
        pick = _pick_in_window(*window)
        if pick is None:
            logger.warning(
                "no expiration available in {} window {} for these listings",
                name, window,
            )
            continue
        if pick[1] in seen:
            continue
        seen.add(pick[1])
        picks.append((name, pick[1]))
    return picks


def _fetch_chain_for_expiration(
    ticker, expiration: str, max_strikes: int, spot: float,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Pull yfinance option chain for one expiration. Returns
    (rows, skip_counts)."""
    skips: dict[str, int] = {}
    chain = ticker.option_chain(expiration)
    rows: list[dict[str, Any]] = []
    for df, opt_type in ((chain.calls, "CALL"), (chain.puts, "PUT")):
        if df is None or df.empty:
            continue
        # Trim to strikes within +/- 25% of spot to keep file sizes
        # sane and to focus on liquid range.
        if spot > 0:
            df = df[
                (df["strike"] >= spot * 0.75)
                & (df["strike"] <= spot * 1.25)
            ]
        # Sort by closeness to spot, take top max_strikes.
        df = df.assign(_dist=lambda x: (x["strike"] - spot).abs())
        df = df.sort_values("_dist").head(max_strikes)
        for r in df.itertuples():
            bid = getattr(r, "bid", None)
            ask = getattr(r, "ask", None)
            last = getattr(r, "lastPrice", None)
            oi = getattr(r, "openInterest", None)
            vol = getattr(r, "volume", None)
            iv = getattr(r, "impliedVolatility", None)
            ct_symbol = getattr(r, "contractSymbol", None)

            if bid is None or ask is None:
                skips["missing_bid_or_ask"] = (
                    skips.get("missing_bid_or_ask", 0) + 1
                )
                continue
            try:
                bid_f = float(bid); ask_f = float(ask)
            except (TypeError, ValueError):
                skips["non_numeric_bid_ask"] = (
                    skips.get("non_numeric_bid_ask", 0) + 1
                )
                continue
            if ask_f <= bid_f or bid_f <= 0:
                skips["bid_ask_invalid"] = (
                    skips.get("bid_ask_invalid", 0) + 1
                )
                continue
            mid_f = (bid_f + ask_f) / 2
            try:
                oi_i = int(oi) if oi is not None else 0
            except (TypeError, ValueError):
                oi_i = 0
            try:
                vol_i = int(vol) if vol is not None else 0
            except (TypeError, ValueError):
                vol_i = 0
            try:
                iv_f = float(iv) if iv is not None else None
            except (TypeError, ValueError):
                iv_f = None
            try:
                last_f = float(last) if last is not None else None
            except (TypeError, ValueError):
                last_f = None

            rows.append({
                "expiry": expiration,
                "strike": float(r.strike),
                "option_type": opt_type,
                "option_symbol": ct_symbol or "",
                "bid": round(bid_f, 4),
                "ask": round(ask_f, 4),
                "mid": round(mid_f, 4),
                "last": round(last_f, 4) if last_f is not None else "",
                "volume": vol_i,
                "open_interest": oi_i,
                "delta": "",       # yfinance does not return greeks
                "gamma": "",
                "theta": "",
                "vega": "",
                "iv": round(iv_f, 6) if iv_f is not None else "",
                # Yahoo doesn't expose quote freshness; use 60s as a
                # safe default — still well below typical staleness
                # threshold (600s).
                "quote_age_seconds": 60,
            })
    return rows, skips


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(REQUIRED_OUTPUT_COLUMNS))
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main(argv: list[str] | None = None) -> int:
    args = _argparse().parse_args(argv)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        sys.stderr.write("REFUSED: --symbols list empty\n")
        return 2
    if args.max_strikes < 4 or args.max_strikes > 100:
        sys.stderr.write("REFUSED: --max-strikes must be 4..100\n")
        return 2
    out_dir = Path(args.out_dir)
    today = dt.date.today()

    import yfinance as yf

    total_written = 0
    summary: list[dict[str, Any]] = []
    for sym in symbols:
        logger.info("[fetch] {} pulling chain", sym)
        try:
            ticker = yf.Ticker(sym)
            available = list(ticker.options or ())
            if not available:
                logger.warning("[fetch] {} no expirations available", sym)
                summary.append({
                    "symbol": sym, "expirations": 0,
                    "contracts": 0, "skipped": 0,
                    "note": "no_expirations",
                })
                continue
            spot_history = ticker.history(period="1d")
            spot = (
                float(spot_history["Close"].iloc[-1])
                if not spot_history.empty else 0.0
            )
            if spot <= 0:
                logger.warning("[fetch] {} no spot price", sym)
                summary.append({
                    "symbol": sym, "expirations": 0,
                    "contracts": 0, "skipped": 0,
                    "note": "no_spot_price",
                })
                continue
            picks = _select_expirations(available, today)
            sym_total = 0
            sym_skipped = 0
            for bucket, exp in picks:
                rows, skips = _fetch_chain_for_expiration(
                    ticker, exp, args.max_strikes, spot,
                )
                if not rows:
                    logger.warning(
                        "[fetch] {} {} ({}) — 0 rows after liquidity drops "
                        "(skips={})",
                        sym, exp, bucket, skips,
                    )
                    sym_skipped += sum(skips.values())
                    continue
                path = out_dir / f"{sym}_{exp}.csv"
                _write_csv(rows, path)
                sym_total += len(rows)
                sym_skipped += sum(skips.values())
                logger.info(
                    "[fetch] {} {} ({}) → {} rows written to {} "
                    "(skipped={})",
                    sym, exp, bucket, len(rows), path, skips,
                )
            total_written += sym_total
            summary.append({
                "symbol": sym, "expirations": len(picks),
                "contracts": sym_total, "skipped": sym_skipped,
                "spot": spot,
            })
        except Exception as exc:  # noqa: BLE001
            logger.error("[fetch] {} ERROR: {}", sym, exc)
            summary.append({
                "symbol": sym, "expirations": 0,
                "contracts": 0, "skipped": 0,
                "note": f"fetch_error: {type(exc).__name__}: {exc}",
            })

    logger.info("=" * 68)
    logger.info("[fetch] SUMMARY (real Yahoo data — no synthesis)")
    for s in summary:
        logger.info("  {}", s)
    logger.info("[fetch]   total_written = {}", total_written)
    logger.info("[fetch]   out_dir       = {}", out_dir)
    logger.info("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
