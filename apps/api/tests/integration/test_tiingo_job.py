"""Integration test: Tiingo job degrades gracefully when API key missing."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from apps.api.src.db.models import PriceBar
from apps.worker.src.jobs.registry import tiingo_backfill_eod

pytestmark = pytest.mark.integration


async def test_tiingo_backfill_skips_without_api_key(
    pg_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from apps.api.src.config import settings

    monkeypatch.setattr(settings, "TIINGO_API_KEY", "")

    # Should not raise, should not write anything
    await tiingo_backfill_eod()

    count = pg_session.query(PriceBar).count()
    assert count == 0
