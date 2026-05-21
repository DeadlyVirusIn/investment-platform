"""Backfill research-only regime labels into context_daily.

Writes status='diagnostic', logic_version='research_backfill_v1'.
Does NOT touch production v1.0.0 rows. Idempotent (ON CONFLICT DO
NOTHING on the unique key (as_of_date, context_name, logic_version)).

Run:
    DATABASE_URL=postgresql+psycopg://... ./.venv/Scripts/python.exe \
        -m scripts.backfill_research_regime [--start 2018-01-02]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

import pandas as pd
from sqlalchemy import text

from apps.api.src.db import SessionLocal
from apps.api.src.research.regime_backfill import (
    LOGIC_VERSION,
    SOURCE_FEATURES,
    STATUS,
    classify_pit,
    logic_hash,
)


def _load_bars(start: str) -> pd.DataFrame:
    from scripts.run_phase12_price_action import fetch_es_daily
    df = fetch_es_daily(start=start)
    df = df.copy()
    df.index = pd.to_datetime(df.index).normalize()
    return df


def _upsert(session, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = text("""
        INSERT INTO context_daily (
            as_of_date, context_name, status, value_bool,
            source_features, logic_version, logic_hash
        ) VALUES (
            :as_of_date, :context_name, :status, :value_bool,
            :source_features, :logic_version, :logic_hash
        )
        ON CONFLICT (as_of_date, context_name, logic_version)
        DO NOTHING
    """)
    inserted = 0
    for row in rows:
        result = session.execute(sql, row)
        inserted += result.rowcount or 0
    session.commit()
    return inserted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    bars = _load_bars(args.start)
    print(f"Loaded {len(bars)} bars from {bars.index[0].date()} -> "
          f"{bars.index[-1].date()}")
    print(f"Logic: {LOGIC_VERSION}  hash={logic_hash()}  status={STATUS}")

    closes = list(bars["close"].astype(float).values)
    dates = [d.date() if hasattr(d, "date") else d for d in bars.index]

    rows: list[dict] = []
    n_stress = 0
    n_directional = 0
    n_neutral = 0
    n_insufficient = 0

    for i, dt in enumerate(dates):
        labels = classify_pit(dt, closes[: i + 1])
        if labels.insufficient_history:
            n_insufficient += 1
        elif labels.stress_regime:
            n_stress += 1
        elif labels.directional_regime:
            n_directional += 1
        else:
            n_neutral += 1

        for context_name, value in (
            ("stress_regime", labels.stress_regime),
            ("directional_regime", labels.directional_regime),
        ):
            rows.append({
                "as_of_date": dt,
                "context_name": context_name,
                "status": STATUS,
                "value_bool": bool(value),
                "source_features": SOURCE_FEATURES,
                "logic_version": LOGIC_VERSION,
                "logic_hash": logic_hash(),
            })

    print(f"\nClassification breakdown across {len(dates)} bars:")
    print(f"  insufficient: {n_insufficient}")
    print(f"  stress      : {n_stress}")
    print(f"  directional : {n_directional}")
    print(f"  neutral     : {n_neutral}")

    if args.dry_run:
        print("\nDRY RUN — no DB writes.")
        return 0

    with SessionLocal() as s:
        inserted = _upsert(s, rows)
    print(f"\nInserted {inserted} new context_daily rows "
          f"({len(rows) - inserted} existed already / no-op).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
