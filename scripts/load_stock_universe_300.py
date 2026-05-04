"""Phase 2 — idempotent loader for stock_swing_v1 universe expansion.

Reads the latest IWV (Russell 3000) CSV produced by
`scripts.fetch_iwv_universe` and inserts:

  * missing `asset` rows
  * missing `universe_membership` rows tagged
    `universe_name='stock_swing_v1'`, `start_date=today`,
    `reason='iwv_top300_load'`

Idempotent on natural keys:
  * `asset.symbol` (existing rows reused; sector backfilled only if blank)
  * `universe_membership(universe_name, asset_id, end_date IS NULL)`
    (re-running adds zero rows once the universe is full)

Hard rules (Phase 2 constraints):
  * Does NOT delete existing symbols.
  * Does NOT deactivate existing symbols.
  * Does NOT touch replay_recovery_manifest, paper_trade,
    paper_position, options_paper_trade, recommendation_outcome.
  * Does NOT change DB schema.
  * Default --commit refused without env confirmation
    `LOAD_UNIVERSE_300_CONFIRM=I_UNDERSTAND_THIS_INSERTS_UNIVERSE_DATA`.
  * --top is capped at 500 to refuse runaway loads.

Usage:

    # Dry-run (default). No DB writes.
    python -m scripts.load_stock_universe_300 \\
        --csv artifacts/phase11_1/iwv_universe_latest.csv \\
        --top 300

    # Commit. REQUIRES env confirm.
    LOAD_UNIVERSE_300_CONFIRM=I_UNDERSTAND_THIS_INSERTS_UNIVERSE_DATA \\
    python -m scripts.load_stock_universe_300 \\
        --csv artifacts/phase11_1/iwv_universe_latest.csv \\
        --top 300 --commit

Exit codes:
  0  success (dry-run or commit)
  1  validation error (bad CSV, missing columns)
  2  refused (no env confirm, missing CSV, --top out of range)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys
from pathlib import Path
from typing import Any

from loguru import logger

CONFIRM_ENV = "LOAD_UNIVERSE_300_CONFIRM"
CONFIRM_VALUE = "I_UNDERSTAND_THIS_INSERTS_UNIVERSE_DATA"
DEFAULT_UNIVERSE = "stock_swing_v1"
TOP_CEILING = 1500           # hard refuse beyond this (raised for 1000-load)
DEFAULT_TOP = 300

REQUIRED_COLUMNS = ("ticker", "name", "sector", "exchange",
                    "market_value_usd", "weight_pct")


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------
def _normalize_symbol(raw: str) -> str | None:
    """Match seed_universe_membership.py conventions: uppercase, dash
    in place of dot. Drop empty / placeholder tickers."""
    if not raw:
        return None
    s = raw.strip().upper().replace(".", "-")
    if not s or s == "-":
        return None
    if not all(c.isalnum() or c == "-" for c in s):
        return None
    return s


def _classify(sector: str) -> str:
    """Map iShares sector text to seed_universe_membership-style tags
    so downstream sector logic stays consistent."""
    if not sector:
        return "unknown"
    s = sector.strip().lower()
    table = {
        "information technology":     "tech",
        "technology":                 "tech",
        "financials":                 "financials",
        "health care":                "healthcare",
        "healthcare":                 "healthcare",
        "consumer discretionary":     "consumer_disc",
        "consumer staples":           "consumer_stap",
        "industrials":                "industrials",
        "energy":                     "energy",
        "utilities":                  "utilities",
        "materials":                  "materials",
        "communication":              "communication",
        "communication services":     "communication",
        "real estate":                "real_estate",
    }
    return table.get(s, s.replace(" ", "_"))


def load_csv(path: Path, top: int) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            f"CSV not found: {path}. Run `python -m "
            f"scripts.fetch_iwv_universe --top {top}` first."
        )
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header row: {path}")
        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(
                f"CSV missing required columns {missing}: {path}"
            )
        rows: list[dict[str, Any]] = []
        for raw in reader:
            sym = _normalize_symbol(raw.get("ticker", ""))
            if sym is None:
                continue
            try:
                mv = float((raw.get("market_value_usd") or "0").replace(",", ""))
            except ValueError:
                continue
            if mv <= 0:
                continue
            rows.append({
                "symbol": sym,
                "name": (raw.get("name") or "").strip(),
                "sector": _classify(raw.get("sector", "")),
                "exchange": (raw.get("exchange") or "").strip()[:32],
                "market_value_usd": mv,
            })
    rows.sort(key=lambda r: r["market_value_usd"], reverse=True)
    return rows[:top]


# ---------------------------------------------------------------------------
# Loader (commit path)
# ---------------------------------------------------------------------------
def _load(rows: list[dict[str, Any]], commit: bool) -> dict[str, int]:
    from sqlalchemy import select
    from apps.api.src.db import SessionLocal
    from apps.api.src.db.models import Asset, UniverseMembership

    today = dt.date.today()
    summary = {
        "csv_rows": len(rows),
        "assets_inserted": 0,
        "assets_existed": 0,
        "universe_rows_inserted": 0,
        "universe_rows_existed": 0,
        "skipped_invalid": 0,
    }

    if not commit:
        # Dry-run: count what WOULD insert without DB writes.
        with SessionLocal() as session:
            existing_assets = {
                sym for (sym,) in session.execute(
                    select(Asset.symbol)
                ).all()
            }
            existing_universe = {
                aid for (aid,) in session.execute(
                    select(UniverseMembership.asset_id).where(
                        UniverseMembership.universe_name == DEFAULT_UNIVERSE,
                        UniverseMembership.end_date.is_(None),
                    )
                ).all()
            }
            existing_asset_ids_by_sym = {
                sym: aid for (aid, sym) in session.execute(
                    select(Asset.id, Asset.symbol)
                ).all()
            }
        for r in rows:
            sym = r["symbol"]
            if sym in existing_assets:
                summary["assets_existed"] += 1
                aid = existing_asset_ids_by_sym.get(sym)
                if aid is None or aid not in existing_universe:
                    summary["universe_rows_inserted"] += 1
                else:
                    summary["universe_rows_existed"] += 1
            else:
                summary["assets_inserted"] += 1
                summary["universe_rows_inserted"] += 1
        return summary

    with SessionLocal() as session:
        existing_assets = {
            sym: aid for (aid, sym) in session.execute(
                select(Asset.id, Asset.symbol)
            ).all()
        }
        existing_universe = {
            aid for (aid,) in session.execute(
                select(UniverseMembership.asset_id).where(
                    UniverseMembership.universe_name == DEFAULT_UNIVERSE,
                    UniverseMembership.end_date.is_(None),
                )
            ).all()
        }

        # Insert missing assets first.
        for r in rows:
            sym = r["symbol"]
            if sym in existing_assets:
                summary["assets_existed"] += 1
                # Backfill sector when blank.
                a = session.get(Asset, existing_assets[sym])
                if a is not None and not a.sector and r["sector"]:
                    a.sector = r["sector"]
                continue
            a = Asset(
                symbol=sym, asset_class="equity", sector=r["sector"],
                exchange=r["exchange"], currency="USD", is_active=True,
            )
            session.add(a)
            session.flush()
            existing_assets[sym] = a.id
            summary["assets_inserted"] += 1
        session.commit()

        # Insert missing universe_membership rows.
        for r in rows:
            aid = existing_assets.get(r["symbol"])
            if aid is None:
                summary["skipped_invalid"] += 1
                continue
            if aid in existing_universe:
                summary["universe_rows_existed"] += 1
                continue
            session.add(UniverseMembership(
                universe_name=DEFAULT_UNIVERSE,
                asset_id=aid,
                start_date=today,
                reason="iwv_top300_load",
            ))
            existing_universe.add(aid)
            summary["universe_rows_inserted"] += 1
        session.commit()

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _argparse() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="load_stock_universe_300",
        description="Idempotent IWV-top-N loader for stock_swing_v1.",
    )
    p.add_argument(
        "--csv",
        default="artifacts/phase11_1/iwv_universe_latest.csv",
        help="Path to IWV CSV from scripts.fetch_iwv_universe.",
    )
    p.add_argument(
        "--top", type=int, default=DEFAULT_TOP,
        help=f"Keep top-N by market value (max {TOP_CEILING}).",
    )
    p.add_argument(
        "--commit", action="store_true",
        help="Actually INSERT. Requires "
             f"{CONFIRM_ENV}={CONFIRM_VALUE} in env.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _argparse().parse_args(argv)

    if not (1 <= args.top <= TOP_CEILING):
        sys.stderr.write(
            f"REFUSED: --top must be 1..{TOP_CEILING}, got {args.top}\n"
        )
        return 2

    if args.commit:
        confirm = os.environ.get(CONFIRM_ENV, "")
        if confirm != CONFIRM_VALUE:
            sys.stderr.write(
                f"REFUSED: --commit requires {CONFIRM_ENV}={CONFIRM_VALUE} "
                f"(got {confirm!r}).\n"
            )
            return 2

    csv_path = Path(args.csv)
    try:
        rows = load_csv(csv_path, args.top)
    except FileNotFoundError as exc:
        sys.stderr.write(f"REFUSED: {exc}\n")
        return 2
    except ValueError as exc:
        sys.stderr.write(f"VALIDATION ERROR: {exc}\n")
        return 1

    logger.info(
        "[load_universe_300] csv={} kept={} commit={}",
        csv_path, len(rows), args.commit,
    )

    summary = _load(rows, args.commit)

    logger.info("[load_universe_300] summary:")
    for k, v in summary.items():
        logger.info("  {}: {}", k, v)
    if not args.commit:
        logger.info(
            "[dry-run] no DB writes performed. Re-run with "
            f"{CONFIRM_ENV}={CONFIRM_VALUE} ... --commit to apply."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
