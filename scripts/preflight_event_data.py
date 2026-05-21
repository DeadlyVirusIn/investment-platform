"""Preflight — verify Phase 10 + 10.6 schema readiness before ingestion.

Queries information_schema for:
  - presence of 3 raw tables + 3 normalized tables + quarantine
  - required Phase-10.6 columns (content_hash, value_unit, etc.)
  - required unique constraints

Does NOT apply migrations. Reports status + exact missing items + ops
command to fix.

Usage:
    python -m scripts.preflight_event_data
    python -m scripts.preflight_event_data --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field

from sqlalchemy import inspect, text

from apps.api.src.db import SessionLocal


REQUIRED_TABLES = (
    "event_raw_earnings",
    "event_raw_shares",
    "event_raw_consensus",
    "earnings_event",
    "shares_outstanding",
    "consensus_estimate",
    "event_quarantine",
)

# Phase 10.6 new columns per table
REQUIRED_PHASE106_COLUMNS: dict[str, list[str]] = {
    "event_raw_earnings": ["content_hash"],
    "event_raw_shares": ["content_hash"],
    "event_raw_consensus": ["content_hash"],
    "consensus_estimate": [
        "value_unit", "original_value", "original_unit", "content_hash",
    ],
}

REQUIRED_UNIQUE_CONSTRAINTS: dict[str, list[str]] = {
    "event_raw_earnings": ["ux_event_raw_earnings_source_content_hash"],
    "event_raw_shares": ["ux_event_raw_shares_source_content_hash"],
    "event_raw_consensus": ["ux_event_raw_consensus_source_content_hash"],
}


@dataclass
class PreflightReport:
    phase10_applied: bool = False
    phase10_6_applied: bool = False
    missing_tables: list[str] = field(default_factory=list)
    missing_columns: dict[str, list[str]] = field(default_factory=dict)
    missing_unique_constraints: dict[str, list[str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def ingestion_ready(self) -> bool:
        return (
            self.phase10_applied and self.phase10_6_applied
            and not self.missing_tables
            and not self.missing_columns
            and not self.missing_unique_constraints
        )

    def as_dict(self) -> dict:
        return {
            "phase10_applied": self.phase10_applied,
            "phase10_6_applied": self.phase10_6_applied,
            "ingestion_ready": self.ingestion_ready,
            "missing_tables": self.missing_tables,
            "missing_columns": self.missing_columns,
            "missing_unique_constraints": self.missing_unique_constraints,
            "notes": self.notes,
        }


def run_preflight() -> PreflightReport:
    report = PreflightReport()
    with SessionLocal() as session:
        insp = inspect(session.bind)

        # Phase 10 — tables
        existing = set(insp.get_table_names())
        for t in REQUIRED_TABLES:
            if t not in existing:
                report.missing_tables.append(t)
        report.phase10_applied = not report.missing_tables

        # Phase 10.6 — columns
        p106_columns_ok = True
        for table, cols in REQUIRED_PHASE106_COLUMNS.items():
            if table not in existing:
                continue   # handled by phase10 check
            present = {c["name"] for c in insp.get_columns(table)}
            missing = [c for c in cols if c not in present]
            if missing:
                p106_columns_ok = False
                report.missing_columns[table] = missing

        # Phase 10.6 — unique constraints
        p106_uq_ok = True
        for table, constraints in REQUIRED_UNIQUE_CONSTRAINTS.items():
            if table not in existing:
                continue
            present = {uc["name"] for uc in insp.get_unique_constraints(table)}
            missing = [c for c in constraints if c not in present]
            if missing:
                p106_uq_ok = False
                report.missing_unique_constraints[table] = missing

        # Phase 10.6 is only meaningful once Phase 10 tables exist.
        report.phase10_6_applied = (
            report.phase10_applied and p106_columns_ok and p106_uq_ok
        )

    # Ops notes
    if report.missing_tables:
        report.notes.append(
            "Run: alembic upgrade 021   # applies Phase 10 baseline"
        )
    if report.missing_columns or report.missing_unique_constraints:
        report.notes.append(
            "Run: alembic upgrade 022   # applies Phase 10.6 hardening"
        )
    if report.ingestion_ready:
        report.notes.append("SCHEMA READY — ingestion can proceed.")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_preflight()
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print("=" * 72)
        print("EVENT-DATA SCHEMA PREFLIGHT")
        print("=" * 72)
        print(f"Phase 10 tables applied:    {report.phase10_applied}")
        print(f"Phase 10.6 hardening applied: {report.phase10_6_applied}")
        print(f"Ingestion ready:            {report.ingestion_ready}")
        if report.missing_tables:
            print(f"Missing tables:             {report.missing_tables}")
        if report.missing_columns:
            print("Missing columns:")
            for t, cols in report.missing_columns.items():
                print(f"  {t:<28s} {cols}")
        if report.missing_unique_constraints:
            print("Missing unique constraints:")
            for t, ucs in report.missing_unique_constraints.items():
                print(f"  {t:<28s} {ucs}")
        if report.notes:
            print("Notes:")
            for n in report.notes:
                print(f"  - {n}")
        print("=" * 72)
    return 0 if report.ingestion_ready else 1


if __name__ == "__main__":
    sys.exit(main())
