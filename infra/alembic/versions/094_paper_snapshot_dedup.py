"""P6D.35C — paper_equity_snapshot dedup + one-row-per-(portfolio,date,source).

Forensics (P6D.35B): the M079 4-col unique key (portfolio_id, snapshot_date,
source, recorded_at) allowed every write event to append a new row. Live data
accumulated 47 duplicate (portfolio_id, snapshot_date, source) groups
(165 rows, 118 non-keepers), 31 with CONFLICTING equity values.

Keeper rule (P6D.35B locked, identical to the P6D.35A reader tiebreaker):
    ROW_NUMBER() OVER (
        PARTITION BY portfolio_id, snapshot_date, source
        ORDER BY recorded_at DESC, id DESC
    ) = 1
Because the keeper IS exactly what every reader already selects post-35A,
dedup changes no displayed value.

upgrade:
  1. CREATE paper_equity_snapshot_dup_archive (LIKE ... INCLUDING DEFAULTS)
     — deliberately WITHOUT unique indexes (forensic storage), plus an
     `archived_at` audit column.
  2. Archive every non-keeper row (never delete without archiving first).
  3. DELETE the archived non-keepers from paper_equity_snapshot.
  4. Narrow uq_paper_equity_snapshot to (portfolio_id, snapshot_date, source)
     — the writer (snapshot_equity_now) becomes a true UPSERT against it.

downgrade:
  Restore the 4-col unique key, re-insert the archived rows, drop the
  archive table. Lossless round trip.

Revision ID: 094_paper_snapshot_dedup
Revises: 093_widen_proposal_hash
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "094_paper_snapshot_dedup"
down_revision = "093_widen_proposal_hash"
branch_labels = None
depends_on = None


ARCHIVE = "paper_equity_snapshot_dup_archive"

# Explicit column list (order-independent restore on downgrade).
_COLS = (
    "id, portfolio_id, snapshot_date, cash, positions_value, total_equity, "
    "unrealized_pnl, realized_pnl_cumulative, created_at, recorded_at, source"
)


def upgrade() -> None:
    # 1. Forensic archive table — same shape + defaults, NO unique indexes.
    op.execute(
        f"CREATE TABLE {ARCHIVE} "
        f"(LIKE paper_equity_snapshot INCLUDING DEFAULTS)"
    )
    op.execute(
        f"ALTER TABLE {ARCHIVE} "
        f"ADD COLUMN archived_at timestamptz NOT NULL DEFAULT now()"
    )

    # 2. Archive non-keepers (keeper = latest recorded_at, id DESC tiebreak —
    #    exactly the row every post-35A reader already selects).
    op.execute(f"""
        INSERT INTO {ARCHIVE}
        SELECT s.*, now()
        FROM paper_equity_snapshot s
        WHERE s.id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY portfolio_id, snapshot_date, source
                           ORDER BY recorded_at DESC, id DESC
                       ) AS rn
                FROM paper_equity_snapshot
            ) ranked
            WHERE ranked.rn > 1
        )
    """)

    # 3. Delete exactly the rows that were archived (archive was created
    #    empty in this same transaction, so deleted == archived by
    #    construction).
    op.execute(f"""
        DELETE FROM paper_equity_snapshot
        WHERE id IN (SELECT id FROM {ARCHIVE})
    """)

    # Fail-loud sanity: no duplicate groups may remain.
    conn = op.get_bind()
    remaining = conn.execute(sa.text(
        "SELECT count(*) FROM ("
        "  SELECT 1 FROM paper_equity_snapshot"
        "  GROUP BY portfolio_id, snapshot_date, source"
        "  HAVING count(*) > 1"
        ") t"
    )).scalar()
    if remaining:
        raise RuntimeError(
            f"094 dedup failed: {remaining} duplicate "
            f"(portfolio_id, snapshot_date, source) groups remain"
        )

    # 4. Narrow the unique key. Live DB has it as a UNIQUE CONSTRAINT
    #    (created by 079 via op.create_unique_constraint; verified via
    #    \\d paper_equity_snapshot → 'UNIQUE CONSTRAINT').
    op.drop_constraint(
        "uq_paper_equity_snapshot", "paper_equity_snapshot", type_="unique"
    )
    op.create_unique_constraint(
        "uq_paper_equity_snapshot",
        "paper_equity_snapshot",
        ["portfolio_id", "snapshot_date", "source"],
    )


def downgrade() -> None:
    # Reverse order: widen the key first so archived rows fit again.
    op.drop_constraint(
        "uq_paper_equity_snapshot", "paper_equity_snapshot", type_="unique"
    )
    op.create_unique_constraint(
        "uq_paper_equity_snapshot",
        "paper_equity_snapshot",
        ["portfolio_id", "snapshot_date", "source", "recorded_at"],
    )
    op.execute(f"""
        INSERT INTO paper_equity_snapshot ({_COLS})
        SELECT {_COLS}
        FROM {ARCHIVE}
    """)
    op.execute(f"DROP TABLE {ARCHIVE}")
