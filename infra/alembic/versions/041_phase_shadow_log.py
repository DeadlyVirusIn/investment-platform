"""Phase SHADOW — paper_shadow_log table.

Read-only research log for shadow strategy candidates. Stores one row
per (as_of_date, source_strategy). NEVER touches paper_trade_log,
decision_log, or any production execution table.

Revision ID: 041_phase_shadow_log
Revises: 040_paper_trade_idempotent
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "041_phase_shadow_log"
down_revision = "040_paper_trade_idempotent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_shadow_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("instrument", sa.Text, nullable=False),
        sa.Column("source_strategy", sa.Text, nullable=False),
        sa.Column("signal", sa.Text, nullable=False),  # LONG | FLAT
        sa.Column("entry_price", sa.Numeric(20, 6)),
        sa.Column("exit_price", sa.Numeric(20, 6)),
        sa.Column("fwd_return_1d", sa.Numeric(12, 8)),
        sa.Column("fwd_return_5d", sa.Numeric(12, 8)),
        sa.Column("regime_label", sa.Text),
        sa.Column("engine_a_active", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("trend_score", sa.Numeric(12, 6)),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("as_of_date", "instrument", "source_strategy",
                              name="ux_paper_shadow_date_strategy"),
        sa.CheckConstraint("signal IN ('LONG', 'FLAT')",
                              name="ck_paper_shadow_signal"),
    )
    op.create_index("ix_paper_shadow_strategy_date", "paper_shadow_log",
                    ["source_strategy", "as_of_date"])


def downgrade() -> None:
    op.drop_index("ix_paper_shadow_strategy_date", "paper_shadow_log")
    op.drop_table("paper_shadow_log")
