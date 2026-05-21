"""Phase L M080 — vocabulary seed loader.

Loads canonical vocabulary entries from JSON files under
apps/api/src/vocabulary/seed/ into the vocabulary_entry table.

Idempotent: ON CONFLICT skips existing (vocabulary_type, canonical_name)
pairs without modifying them. New entries are added; existing entries
are left intact (deprecation/retirement is a separate operator action).

Usage:
    python -m scripts.seed_vocabulary
    python -m scripts.seed_vocabulary --type signal
    python -m scripts.seed_vocabulary --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from sqlalchemy import text

from apps.api.src.db import SessionLocal


SEED_DIR = Path("apps/api/src/vocabulary/seed")

# (filename, vocabulary_type)
SEED_FILES: list[tuple[str, str]] = [
    ("signals_v1.json", "signal"),
    ("skeletons_v1.json", "skeleton"),
    ("invalidations_v1.json", "invalidation_trigger"),
    # Future seeds — added in subsequent days:
    # ("regimes_v1.json", "regime"),
    # ("strategies_v1.json", "strategy_family"),
    # ("portfolio_states_v1.json", "portfolio_state"),
    # ("banner_causes_v1.json", "truth_banner_cause"),
    # ("contradictions_v1.json", "contradiction_reason"),
]

INTRODUCED_VERSION = "v1.0"


def _load_seed_file(path: Path) -> list[dict]:
    with path.open() as f:
        return json.load(f)


def _upsert_entries(
    session, vocab_type: str, entries: list[dict], dry_run: bool,
) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    for e in entries:
        canonical = e["name"]
        existing = session.execute(
            text(
                "SELECT id FROM vocabulary_entry "
                "WHERE vocabulary_type = :vt AND canonical_name = :cn"
            ),
            {"vt": vocab_type, "cn": canonical},
        ).first()
        if existing is not None:
            skipped += 1
            continue
        if dry_run:
            print(f"  [dry-run] would insert: {vocab_type}/{canonical}")
            inserted += 1
            continue
        session.execute(
            text(
                "INSERT INTO vocabulary_entry "
                "  (id, vocabulary_type, canonical_name, display_label, "
                "   domain, description, status, introduced_version) "
                "VALUES "
                "  (:id, :vt, :cn, :lbl, :dom, :desc, 'active', :ver)"
            ),
            {
                "id": str(uuid.uuid4()),
                "vt": vocab_type,
                "cn": canonical,
                "lbl": e["label"],
                "dom": e.get("domain"),
                "desc": e["description"],
                "ver": INTRODUCED_VERSION,
            },
        )
        inserted += 1
    return inserted, skipped


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="seed_vocabulary")
    p.add_argument(
        "--type", default=None,
        help="Restrict to a single vocabulary type (e.g. 'signal').",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be inserted without writing.",
    )
    args = p.parse_args(argv)

    total_ins = 0
    total_skip = 0
    with SessionLocal() as session:
        for fname, vtype in SEED_FILES:
            if args.type is not None and args.type != vtype:
                continue
            path = SEED_DIR / fname
            if not path.exists():
                print(f"SKIP {fname}: file missing", file=sys.stderr)
                continue
            print(f"seeding {vtype} from {fname}")
            entries = _load_seed_file(path)
            ins, skip = _upsert_entries(session, vtype, entries, args.dry_run)
            total_ins += ins
            total_skip += skip
            print(f"  inserted={ins} skipped(existing)={skip}")
        if not args.dry_run:
            session.commit()
    print(f"DONE: inserted={total_ins} skipped={total_skip}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
