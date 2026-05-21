"""Phase 2 stock fix Phase 4 — backfill paper_execution_funnel from
existing artifacts/paper_trading_skips/<date>.jsonl files.

Reads every JSONL file in the skips dir, groups rows by
(date, portfolio_id), counts skip-reason codes, and UPSERTs one
funnel row per pair.

NOTE: pre-funnel runs lack saturation snapshot (open_positions_at_start,
cash_at_start, etc) — those are inferred from current state at backfill
time. Forward runs (post-Phase-4) write accurate snapshots.

Idempotent: re-running overwrites existing rows.

Usage (from repo root inside api container):
    python -m scripts.backfill_paper_execution_funnel
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from apps.api.src.db import SessionLocal
from apps.api.src.domain.paper_trading.funnel import (
    KNOWN_SKIP_CODES,
    PaperFunnelCounts,
    PaperFunnelSnapshot,
    upsert_funnel_row,
)


SKIPS_DIR = Path("artifacts/paper_trading_skips")


def _portfolio_meta(session) -> dict[str, dict]:
    """Per-portfolio current cash + max_open_positions from config_json."""
    rows = session.execute(text("""
        SELECT id, cash, config_json,
               (SELECT COUNT(*) FROM paper_position
                 WHERE portfolio_id=pp.id AND is_open=true) AS open_count
          FROM paper_portfolio pp
    """)).mappings().all()
    out = {}
    for r in rows:
        cfg = {}
        try:
            cfg = json.loads(r["config_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            cfg = {}
        out[r["id"]] = {
            "cash": Decimal(str(r["cash"] or 0)),
            "max_open": int(cfg.get("max_open_positions", 10)),
            "open_count": int(r["open_count"] or 0),
        }
    return out


def main() -> None:
    if not SKIPS_DIR.exists():
        print(f"no skips dir at {SKIPS_DIR.resolve()} — nothing to backfill")
        return

    files = sorted(SKIPS_DIR.glob("*.jsonl"))
    if not files:
        print("no jsonl files found")
        return

    inserted = 0
    skipped = 0
    with SessionLocal() as session:
        meta = _portfolio_meta(session)

        for path in files:
            stem = path.stem
            # Skip the .replayed.jsonl variant for now — separate counter.
            if stem.endswith(".replayed"):
                skipped += 1
                continue
            try:
                run_date = dt.date.fromisoformat(stem)
            except ValueError:
                skipped += 1
                continue

            per_portfolio: dict[str, Counter] = defaultdict(Counter)
            with path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    pid = row.get("portfolio_id")
                    reason = str(row.get("reason") or "")
                    if not pid:
                        continue
                    if reason in KNOWN_SKIP_CODES:
                        per_portfolio[pid][reason] += 1
                    else:
                        per_portfolio[pid]["unknown_reason"] += 1

            for pid, counts in per_portfolio.items():
                m = meta.get(pid, {
                    "cash": Decimal("0"), "max_open": 10, "open_count": 0,
                })
                fc = PaperFunnelCounts(
                    buy_candidates_total=sum(counts.values()),
                    buys_executed=0,   # backfill cannot reconstruct
                    sells_executed=0,
                    skip_portfolio_full=counts.get("portfolio_full", 0),
                    skip_duplicate_holding=counts.get("duplicate_holding", 0),
                    skip_pending_sell_same_asset=counts.get(
                        "pending_sell_same_asset", 0,
                    ),
                    skip_sizing_below_threshold=counts.get(
                        "sizing_below_threshold", 0,
                    ),
                    skip_position_too_small=counts.get("position_too_small", 0),
                    skip_cash_constraint=counts.get("cash_constraint", 0),
                    skip_execution_failure=counts.get("execution_failure", 0),
                    skip_unknown_reason=counts.get("unknown_reason", 0),
                )
                upsert_funnel_row(
                    session,
                    run_date=run_date,
                    portfolio_id=pid,
                    counts=fc,
                    snapshot=PaperFunnelSnapshot(
                        open_positions_at_start=m["open_count"],
                        max_open_positions=m["max_open"],
                        cash_at_start=m["cash"],
                        equity_at_start=m["cash"],
                    ),
                    details={"backfilled_from": path.name},
                )
                inserted += 1
        session.commit()
    print(f"inserted/upserted {inserted} funnel rows; "
          f"skipped {skipped} non-conformant files")


if __name__ == "__main__":
    main()
