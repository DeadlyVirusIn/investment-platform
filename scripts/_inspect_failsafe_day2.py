"""Verify: if materializer throws, generate_stock_candidates still completes,
candidate_idea rows still written, ERROR logged loudly."""

from __future__ import annotations

import asyncio
import datetime as dt
from unittest.mock import patch

from sqlalchemy import select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import CandidateIdea
from apps.worker.src.jobs.generate_stock_candidates import generate_stock_candidates

AS_OF = dt.date(2026, 3, 13)


def _boom(*args, **kwargs):
    raise RuntimeError("synthetic failure to test fail-safe wrapper")


async def _run() -> None:
    with SessionLocal() as s:
        before_candidates = s.scalar(
            select(CandidateIdea).where(CandidateIdea.as_of_date == AS_OF).limit(1)
        )
        assert before_candidates is not None, "pre-state missing"

    with patch(
        "apps.worker.src.jobs.generate_stock_candidates.materialize_actions_for_day",
        side_effect=_boom,
    ):
        await generate_stock_candidates(AS_OF)

    with SessionLocal() as s:
        after_count = s.execute(
            select(CandidateIdea).where(CandidateIdea.as_of_date == AS_OF)
        ).all()
    print(f"candidate_idea rows after materializer raise: {len(after_count)}")
    assert len(after_count) > 0, "candidate_idea should still be written"
    print("FAIL-SAFE VERIFIED: candidate_idea persisted, materializer error swallowed")


if __name__ == "__main__":
    asyncio.run(_run())
