"""BACKTEST-PAPER-4 — recommendation persist replay seam.

Proves the optional generated_at + model_version_override params on persist()
let a replay caller stamp the decision date and a namespaced version, while
the default (both None) is byte-identical to live persistence.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, Recommendation, RecommendationOutcome
from apps.api.src.domain.recommendations.recommendation_engine import (
    RecommendationResult,
    persist,
)

pytestmark = pytest.mark.integration


def _asset(pg_session: Session, symbol: str) -> str:
    a = Asset(symbol=symbol, asset_class="equity", exchange="TEST", currency="USD")
    pg_session.add(a)
    pg_session.flush()
    return a.id


def _result(asset_id: str, snap: str, *, version: str = "engine-v1",
            price: Decimal | None = Decimal("123.45")) -> RecommendationResult:
    return RecommendationResult(
        asset_id=asset_id, action="Buy", confidence=Decimal("70"),
        confidence_label="High", enough_data=True, engine_version=version,
        snapshot_hash=snap, thesis="t", composite_score=Decimal("0.5"),
        family_scores={}, signals=[], tags=["equity"], current_price=price,
    )


def _get(pg_session: Session, rec_id: str) -> Recommendation:
    return pg_session.get(Recommendation, rec_id)


def test_default_persist_unchanged(pg_session: Session) -> None:
    aid = _asset(pg_session, "BP4A")
    before = dt.datetime.now(dt.timezone.utc)
    rid = persist(pg_session, _result(aid, "snapA"))
    pg_session.flush()

    row = _get(pg_session, rid)
    assert row.model_version == "engine-v1"             # default version
    assert row.generated_at is not None
    # DB default ~ now()
    gen = row.generated_at
    if gen.tzinfo is None:
        gen = gen.replace(tzinfo=dt.timezone.utc)
    assert abs((gen - before).total_seconds()) < 300

    outcome = pg_session.execute(
        select(RecommendationOutcome).where(
            RecommendationOutcome.recommendation_id == rid)
    ).scalars().first()
    assert outcome is not None
    assert outcome.price_at_recommendation == Decimal("123.45")


def test_generated_at_override(pg_session: Session) -> None:
    aid = _asset(pg_session, "BP4B")
    T = dt.datetime(2020, 1, 1, 14, 0, tzinfo=dt.timezone.utc)
    rid = persist(pg_session, _result(aid, "snapB"), generated_at=T)
    pg_session.flush()

    gen = _get(pg_session, rid).generated_at
    if gen.tzinfo is None:
        gen = gen.replace(tzinfo=dt.timezone.utc)
    assert gen == T


def test_model_version_override(pg_session: Session) -> None:
    aid = _asset(pg_session, "BP4C")
    rid = persist(pg_session, _result(aid, "snapC"),
                  model_version_override="engine-v1+replay:r1")
    pg_session.flush()
    assert _get(pg_session, rid).model_version == "engine-v1+replay:r1"


def test_idempotent_under_override(pg_session: Session) -> None:
    aid = _asset(pg_session, "BP4D")
    r1 = persist(pg_session, _result(aid, "snapD"),
                 model_version_override="engine-v1+replay:r1")
    pg_session.flush()
    r2 = persist(pg_session, _result(aid, "snapD"),
                 model_version_override="engine-v1+replay:r1")
    pg_session.flush()
    assert r1 == r2   # same (asset, version, snapshot_hash) -> existing returned


def test_override_namespaced_distinct_from_default(pg_session: Session) -> None:
    """Same result with vs without override -> different rows (different
    model_version -> different unique key)."""
    aid = _asset(pg_session, "BP4E")
    replay_id = persist(pg_session, _result(aid, "snapE"),
                        model_version_override="engine-v1+replay:r1")
    pg_session.flush()
    live_id = persist(pg_session, _result(aid, "snapE"))   # no override
    pg_session.flush()
    assert replay_id != live_id
    assert _get(pg_session, replay_id).model_version == "engine-v1+replay:r1"
    assert _get(pg_session, live_id).model_version == "engine-v1"


def test_outcome_created_under_override(pg_session: Session) -> None:
    aid = _asset(pg_session, "BP4F")
    rid = persist(pg_session, _result(aid, "snapF", price=Decimal("99.99")),
                  generated_at=dt.datetime(2021, 6, 1, tzinfo=dt.timezone.utc),
                  model_version_override="engine-v1+replay:r1")
    pg_session.flush()
    outcome = pg_session.execute(
        select(RecommendationOutcome).where(
            RecommendationOutcome.recommendation_id == rid)
    ).scalars().first()
    assert outcome is not None
    assert outcome.price_at_recommendation == Decimal("99.99")
