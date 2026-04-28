"""Phase 11P.1 - additive columns on decision_log for paper data tagging.

Adds four append-only columns:
  * source                 text NOT NULL DEFAULT 'strict_paper'
  * strict_gates_passed    boolean
  * failed_gates           text[] NOT NULL DEFAULT '{}'
  * ml_label_eligible      boolean NOT NULL DEFAULT FALSE

Backfills existing rows with source='strict_paper' (default already
applies to historical rows). CHECK constraint locks the source value
to a closed set.

NEVER drops, renames, or alters existing columns. NEVER touches any
strict-engine table.

Revision ID: 049_paper_label_cols
Revises: 048_phase11d_features
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "049_paper_label_cols"
down_revision = "048_phase11d_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "decision_log",
        sa.Column(
            "source",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'strict_paper'"),
        ),
    )
    op.add_column(
        "decision_log",
        sa.Column(
            "strict_gates_passed",
            sa.Boolean(),
            nullable=True,
        ),
    )
    op.add_column(
        "decision_log",
        sa.Column(
            "failed_gates",
            sa.dialects.postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.add_column(
        "decision_log",
        sa.Column(
            "ml_label_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
    )
    # Backfill existing rows. Server-default applied above, but we
    # repeat the explicit UPDATE so that operator + audit can see one
    # explicit pass that all historical rows are tagged 'strict_paper'.
    op.execute(
        "UPDATE decision_log SET source = 'strict_paper' "
        "WHERE source IS NULL"
    )
    op.create_check_constraint(
        "ck_decision_log_source",
        "decision_log",
        "source IN ('strict_paper', 'exploratory_paper', 'backfill')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_decision_log_source", "decision_log",
                       type_="check")
    op.drop_column("decision_log", "ml_label_eligible")
    op.drop_column("decision_log", "failed_gates")
    op.drop_column("decision_log", "strict_gates_passed")
    op.drop_column("decision_log", "source")
