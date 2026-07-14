"""Deterministic CLI seeding path for MVP model portfolios.

Idempotent: inserts any missing curated portfolios (by slug) and recomputes
their track records from the total-return price panel. Safe to run repeatedly
(post-migration, on deploy, or manually).

Usage:
    DATABASE_URL=postgresql+psycopg://... python scripts/seed_model_portfolios.py
    make seed-model-portfolios            # (Makefile target)
"""

from __future__ import annotations

from apps.api.src.db import SessionLocal
from apps.api.src.api.model_portfolios import seed_curated, CURATED


def main() -> None:
    with SessionLocal() as session:
        touched = seed_curated(session, recompute=True)
    print(f"seed_model_portfolios: curated={len(CURATED)} newly_inserted={len(touched)} {touched}")


if __name__ == "__main__":
    main()
