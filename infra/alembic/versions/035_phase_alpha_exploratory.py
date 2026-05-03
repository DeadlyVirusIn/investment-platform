"""Phase SYSTEM-ALPHA-5 — paper exploratory mode fields.

Additive columns only. Strict/live behaviour unchanged.

Revision ID: 035_phase_alpha_exploratory
Revises: 034_phase_alpha_enforcement
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "035_phase_alpha_exploratory"
down_revision = "034_phase_alpha_enforcement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decision_log",
        sa.Column("gate_mode", sa.Text, nullable=True))
    op.add_column("decision_log",
        sa.Column("exploratory_paper", sa.Boolean, nullable=False,
                  server_default=sa.text("false")))
    op.add_column("decision_log",
        sa.Column("exploratory_reason", sa.Text, nullable=True))
    op.add_column("decision_log",
        sa.Column("gates_passed", sa.Integer, nullable=True))
    op.add_column("decision_log",
        sa.Column("gates_total",  sa.Integer, nullable=True))
    op.add_column("decision_log",
        sa.Column("gates_failed", JSONB, nullable=True))
    op.add_column("decision_log",
        sa.Column("strict_would_block", sa.Boolean, nullable=False,
                  server_default=sa.text("false")))
    op.add_column("decision_log",
        sa.Column("exploratory_size_multiplier",
                  sa.Numeric(6, 4), nullable=True))
    op.create_index("ix_decision_log_exploratory",
                    "decision_log", ["exploratory_paper"])

    op.add_column("paper_trade_log",
        sa.Column("exploratory_paper", sa.Boolean, nullable=False,
                  server_default=sa.text("false")))
    op.add_column("paper_trade_log",
        sa.Column("exploratory_snapshot", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("paper_trade_log", "exploratory_snapshot")
    op.drop_column("paper_trade_log", "exploratory_paper")
    op.drop_index("ix_decision_log_exploratory",
                  table_name="decision_log")
    for c in ("exploratory_size_multiplier", "strict_would_block",
              "gates_failed", "gates_total", "gates_passed",
              "exploratory_reason", "exploratory_paper", "gate_mode"):
        op.drop_column("decision_log", c)
