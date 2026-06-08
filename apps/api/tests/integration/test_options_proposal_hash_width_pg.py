"""P6D.19 — options_paper_trade.proposal_hash accepts 64-char SHA-256 hashes.

Regression for the first-canary activation failure (StringDataRightTruncation:
value too long for type character varying(32)). The canary proposal_hash is a
64-char SHA-256 hex digest; the column was widened 32->64 (migration 093 /
ORM String(64)). Touches only options_paper_trade (an ORM-modeled table), so it
runs under the standard testcontainer create_all fixture.
"""

from __future__ import annotations

import datetime as dt

import pytest
import sqlalchemy
from sqlalchemy import text

# noqa: F401 — register the ORM table on Base.metadata for create_all
from apps.api.src.db.options_models import OptionsPaperTrade  # noqa: F401

pytestmark = pytest.mark.integration

HASH64 = "f92686d2273e9b9bbb4283fb5c739556e0cc77d7c08c160194ae63eaf9d4a9b8"
HASH_LEGACY = "legacy0000000000000000000000abcd"   # 32 chars

_INSERT = text(
    "INSERT INTO options_paper_trade "
    "(underlying, strategy_name, strategy_version, status, opened_at, "
    " fees_total_dollars, max_loss_dollars, max_profit_dollars, "
    " fill_model_version, paper_only, proposal_hash) "
    "VALUES ('QQQ','SHORT_PUT_CREDIT_SPREAD','canary-v1','OPEN',:now,"
    " 2.80, 81, 19, 'v1.conservative', TRUE, :ph) RETURNING id"
)


def _insert(session, ph):
    return session.execute(
        _INSERT, {"now": dt.datetime(2026, 6, 8, tzinfo=dt.timezone.utc), "ph": ph}
    ).scalar()


def test_64char_proposal_hash_no_truncation(pg_session):
    assert len(HASH64) == 64
    tid = _insert(pg_session, HASH64)
    pg_session.commit()
    stored = pg_session.execute(
        text("SELECT proposal_hash FROM options_paper_trade WHERE id=:i"),
        {"i": tid},
    ).scalar()
    assert stored == HASH64            # full 64 chars, no truncation
    assert len(stored) == 64


def test_duplicate_proposal_hash_blocked(pg_session):
    # The partial-unique index is alembic-defined (067), not in the ORM, so the
    # create_all test schema lacks it — recreate the exact index to validate
    # dedup against the same definition the migrated DB uses.
    pg_session.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_options_paper_trade_proposal_hash "
        "ON options_paper_trade (proposal_hash) WHERE proposal_hash IS NOT NULL"
    ))
    pg_session.commit()
    _insert(pg_session, HASH64)
    pg_session.commit()
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        _insert(pg_session, HASH64)    # partial-unique index still enforces
        pg_session.commit()


def test_short_legacy_hash_still_ok(pg_session):
    tid = _insert(pg_session, HASH_LEGACY)
    pg_session.commit()
    stored = pg_session.execute(
        text("SELECT proposal_hash FROM options_paper_trade WHERE id=:i"),
        {"i": tid},
    ).scalar()
    assert stored == HASH_LEGACY
