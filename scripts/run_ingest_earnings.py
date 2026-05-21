"""CLI — ingest earnings records from a JSONL file.

Usage:
    python -m scripts.run_ingest_earnings --input path/to/file.jsonl
    python -m scripts.run_ingest_earnings --input path/to/file.jsonl --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from loguru import logger

from apps.api.src.db import SessionLocal
from apps.api.src.ingestion.earnings import ingest_earnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.input.exists():
        logger.error("[cli.earnings] input not found: {}", args.input)
        return 1

    records: list[dict] = []
    with args.input.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.error("[cli.earnings] line {}: {}", i, exc)
    logger.info("[cli.earnings] read {} records from {}", len(records), args.input)

    with SessionLocal() as session:
        result = ingest_earnings(session, records, dry_run=args.dry_run)

    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.quarantined == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
