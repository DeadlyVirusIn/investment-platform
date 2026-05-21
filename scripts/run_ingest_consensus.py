"""CLI — ingest EPS/Revenue consensus+actual records from a JSONL file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from loguru import logger

from apps.api.src.db import SessionLocal
from apps.api.src.ingestion.consensus import ingest_consensus


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.input.exists():
        logger.error("[cli.consensus] input not found: {}", args.input)
        return 1
    records = []
    for line in args.input.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    logger.info("[cli.consensus] read {} records", len(records))
    with SessionLocal() as session:
        result = ingest_consensus(session, records, dry_run=args.dry_run)
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.quarantined == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
