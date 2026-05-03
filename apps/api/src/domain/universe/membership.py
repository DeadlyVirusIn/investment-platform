"""Universe membership point-in-time lookups.

Semantics: an asset is a member of `universe_name` on date `as_of` iff a
row exists where ``start_date <= as_of`` AND (``end_date IS NULL`` OR
``end_date >= as_of``). Inclusive on both ends.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, UniverseMembership


def list_members(
    session: Session,
    universe_name: str,
    as_of: dt.date | None = None,
) -> list[tuple[UniverseMembership, Asset]]:
    """Return all (membership_row, asset) tuples active in the universe on
    ``as_of``. Defaults to today. Ordered by asset symbol for determinism."""
    effective = as_of or dt.date.today()
    stmt = (
        select(UniverseMembership, Asset)
        .join(Asset, Asset.id == UniverseMembership.asset_id)
        .where(
            UniverseMembership.universe_name == universe_name,
            UniverseMembership.start_date <= effective,
            or_(
                UniverseMembership.end_date.is_(None),
                UniverseMembership.end_date >= effective,
            ),
        )
        .order_by(Asset.symbol.asc())
    )
    return list(session.execute(stmt).all())


def is_member(
    session: Session,
    universe_name: str,
    asset_id: str,
    as_of: dt.date,
) -> bool:
    """True iff the asset is in the universe on ``as_of``."""
    stmt = (
        select(UniverseMembership.id)
        .where(
            UniverseMembership.universe_name == universe_name,
            UniverseMembership.asset_id == asset_id,
            UniverseMembership.start_date <= as_of,
            or_(
                UniverseMembership.end_date.is_(None),
                UniverseMembership.end_date >= as_of,
            ),
        )
        .limit(1)
    )
    return session.execute(stmt).first() is not None
