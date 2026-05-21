"""Fetch iShares IWV (Russell 3000) holdings CSV — Phase 11.1.

iShares publishes daily holdings. We pull the current snapshot and keep only
US-domiciled equity lines. Non-equity (cash placeholders, futures) filtered.

Output: artifacts/phase11_1/iwv_universe_YYYY-MM-DD.csv
        artifacts/phase11_1/iwv_universe_latest.csv   (symlink-ish copy)

Columns kept: ticker, name, sector, market_value, weight_pct

Usage:
    python -m scripts.fetch_iwv_universe
    python -m scripts.fetch_iwv_universe --top 100
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import sys
from pathlib import Path

import requests
from loguru import logger

IWV_URL = (
    "https://www.ishares.com/us/products/239714/ishares-russell-3000-etf/"
    "1467271812596.ajax?fileType=csv&fileName=IWV_holdings&dataType=fund"
)

OUT_DIR = Path("artifacts/phase11_1")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_raw() -> str:
    r = requests.get(
        IWV_URL, timeout=30,
        headers={"User-Agent": "Mozilla/5.0 investment-platform phase11.1"},
    )
    r.raise_for_status()
    # iShares sometimes returns cp1252-encoded BOM + metadata block
    text = r.content.decode("utf-8-sig", errors="replace")
    return text


def parse_holdings(raw: str) -> list[dict]:
    lines = raw.splitlines()
    # Header row is the first line that starts with "Ticker,"
    hdr_idx = None
    for i, ln in enumerate(lines):
        if ln.startswith("Ticker,"):
            hdr_idx = i
            break
    if hdr_idx is None:
        raise RuntimeError("IWV CSV header not found (iShares layout changed?)")

    reader = csv.DictReader(io.StringIO("\n".join(lines[hdr_idx:])))
    out: list[dict] = []
    for row in reader:
        tk = (row.get("Ticker") or "").strip()
        if not tk or tk == "-":
            continue
        asset_class = (row.get("Asset Class") or "").strip()
        if asset_class != "Equity":
            continue
        location = (row.get("Location") or "").strip()
        if location != "United States":
            continue
        currency = (row.get("Currency") or "").strip()
        if currency != "USD":
            continue
        try:
            mv = float((row.get("Market Value") or "0").replace(",", ""))
            wt = float((row.get("Weight (%)") or "0").replace(",", ""))
        except ValueError:
            continue
        if mv <= 0:
            continue
        out.append({
            "ticker": tk.replace(".", "-"),  # BRK.B -> BRK-B for yfinance-style
            "name": (row.get("Name") or "").strip(),
            "sector": (row.get("Sector") or "").strip(),
            "exchange": (row.get("Exchange") or "").strip(),
            "market_value_usd": mv,
            "weight_pct": wt,
        })
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=0,
                   help="Keep top-N by market value (0 = all)")
    args = p.parse_args()

    logger.info("[iwv] fetching...")
    raw = fetch_raw()
    holdings = parse_holdings(raw)
    logger.info("[iwv] parsed {} US-equity holdings", len(holdings))
    holdings.sort(key=lambda h: h["market_value_usd"], reverse=True)
    if args.top > 0:
        holdings = holdings[:args.top]

    today = dt.date.today().isoformat()
    fn = OUT_DIR / f"iwv_universe_{today}.csv"
    with fn.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(holdings[0].keys()))
        w.writeheader()
        w.writerows(holdings)
    (OUT_DIR / "iwv_universe_latest.csv").write_text(fn.read_text())
    logger.info("[iwv] wrote {} rows to {}", len(holdings), fn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
