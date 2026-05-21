"""CLI — run event-data validation report.

Scans normalized + raw + quarantine tables and prints a structured
summary. No mutations. Safe to run any time.
"""

from __future__ import annotations

import json
import sys

from loguru import logger

from apps.api.src.db import SessionLocal
from apps.api.src.ingestion.validation import run_validation


def main() -> int:
    with SessionLocal() as session:
        report = run_validation(session)
    print(json.dumps(report.as_dict(), indent=2, default=str))
    logger.info("[validation] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
