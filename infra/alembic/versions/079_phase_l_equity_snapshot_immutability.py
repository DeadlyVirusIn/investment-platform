"""Phase L M083 — paper_equity_snapshot immutability + source tagging.

Resolves OVA-1: exit-cycle replays were overwriting historical equity
snapshots via UPSERT keyed on (portfolio_id, snapshot_date), silently
rewriting the AI's daily P&L history.

Fix (per docs/research/M083_CANONICAL_SEMANTIC.md, Option A locked):
  1. Add `recorded_at` column (write timestamp) — preserves storage
     immutability of historical rows.
  2. Add `source` column with allowed values: live / replay / backfill /
     operator_manual — distinguishes canonical user-facing truth from
     forensic/audit-only rows.
  3. Drop old uniqueness constraint on (portfolio_id, snapshot_date).
  4. Add new uniqueness constraint on
     (portfolio_id, snapshot_date, source, recorded_at) — allows
     multiple rows per (portfolio_id, snapshot_date) when sources differ
     or when replay overlays accumulate, while preventing exact-duplicate
     writes.
  5. Index source for fast filtering on canonical reads.

Writer contract (mandatory; enforced at code-review):
  Every write to paper_equity_snapshot MUST specify `source` explicitly.

Reader contract (mandatory; enforced at code-review + CI):
  User-facing canonical reads MUST include `WHERE source = 'live'`.

Rollback policy (per docs/research/M083_CANONICAL_SEMANTIC.md):
  dev:        snapshot-restore (drop + restore from pre-deploy pg_dump)
  staging:    fail-loud if duplicates present
  production: fail-loud + pre-deploy pg_dump backup

This downgrade implementation is `fail-loud`: refuses to revert if any
duplicate (portfolio_id, snapshot_date) groups exist post-application.

Revision ID: 079_phase_l_equity_immutability
Revises: 078_phase_l_user_accounts
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "079_phase_l_equity_immutability"
down_revision = "078_phase_l_user_accounts"
branch_labels = None
depends_on = None


ALLOWED_SOURCES = ("live", "replay", "backfill", "operator_manual")


def upgrade() -> None:
    # 1. Add `recorded_at` — populate with `created_at` for existing rows
    #    so historical write timing is preserved.
    op.add_column(
        "paper_equity_snapshot",
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=True,  # nullable during backfill; tightened below
        ),
    )
    op.execute(
        "UPDATE paper_equity_snapshot SET recorded_at = created_at "
        "WHERE recorded_at IS NULL"
    )
    op.alter_column(
        "paper_equity_snapshot",
        "recorded_at",
        nullable=False,
        server_default=sa.text("NOW()"),
    )

    # 2. Add `source` — backfill all existing rows as 'live' (they
    #    pre-date the replay-row concept).
    op.add_column(
        "paper_equity_snapshot",
        sa.Column(
            "source",
            sa.String(16),
            nullable=True,
            server_default="live",
        ),
    )
    op.execute(
        "UPDATE paper_equity_snapshot SET source = 'live' WHERE source IS NULL"
    )
    op.alter_column("paper_equity_snapshot", "source", nullable=False)
    op.create_check_constraint(
        "ck_paper_equity_snapshot_source",
        "paper_equity_snapshot",
        "source IN ('live','replay','backfill','operator_manual')",
    )

    # 3. Drop old uniqueness constraint.
    op.drop_constraint(
        "uq_paper_equity_snapshot",
        "paper_equity_snapshot",
        type_="unique",
    )

    # 4. New uniqueness: allow multiple rows per (portfolio, date) when
    #    source or recorded_at differ. Exact-duplicate writes blocked.
    op.create_unique_constraint(
        "uq_paper_equity_snapshot",
        "paper_equity_snapshot",
        ["portfolio_id", "snapshot_date", "source", "recorded_at"],
    )

    # 5. Indexes for canonical reads.
    op.create_index(
        "idx_paper_equity_snapshot_canonical",
        "paper_equity_snapshot",
        ["portfolio_id", "snapshot_date", "source", sa.text("recorded_at DESC")],
    )
    op.create_index(
        "idx_paper_equity_snapshot_source",
        "paper_equity_snapshot",
        ["source"],
        postgresql_where=sa.text("source != 'live'"),
    )


def downgrade() -> None:
    """Fail-loud downgrade.

    Aborts if any (portfolio_id, snapshot_date) group has more than one
    row — indicates replay/backfill overlays accumulated post-M083 that
    cannot be silently reduced to a single row.
    """
    conn = op.get_bind()
    duplicates = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM ("
            "  SELECT portfolio_id, snapshot_date "
            "  FROM paper_equity_snapshot "
            "  GROUP BY portfolio_id, snapshot_date "
            "  HAVING COUNT(*) > 1"
            ") t"
        )
    ).scalar()
    if duplicates and duplicates > 0:
        raise RuntimeError(
            f"M079 downgrade refused: {duplicates} (portfolio_id, snapshot_date) "
            f"groups have >1 row. Per docs/research/M083_CANONICAL_SEMANTIC.md, "
            f"resolve manually via pg_dump restore or explicit policy before "
            f"downgrade can proceed."
        )

    op.drop_index(
        "idx_paper_equity_snapshot_source",
        table_name="paper_equity_snapshot",
    )
    op.drop_index(
        "idx_paper_equity_snapshot_canonical",
        table_name="paper_equity_snapshot",
    )
    op.drop_constraint(
        "uq_paper_equity_snapshot",
        "paper_equity_snapshot",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_paper_equity_snapshot",
        "paper_equity_snapshot",
        ["portfolio_id", "snapshot_date"],
    )
    op.drop_constraint(
        "ck_paper_equity_snapshot_source",
        "paper_equity_snapshot",
        type_="check",
    )
    op.drop_column("paper_equity_snapshot", "source")
    op.drop_column("paper_equity_snapshot", "recorded_at")
