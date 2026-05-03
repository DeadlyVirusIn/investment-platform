"""Phase SYSTEM-ALPHA-4 — rule enforcement + audit columns.

Adds decision_log + paper_trade_log columns for rule-driven paper trading.

Revision ID: 034_phase_alpha_enforcement
Revises: 033_phase_alpha_rules
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "034_phase_alpha_enforcement"
down_revision = "033_phase_alpha_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # decision_log additions
    op.add_column("decision_log",
        sa.Column("alpha_rule_adjustment", JSONB, nullable=True))
    op.add_column("decision_log",
        sa.Column("alpha_rules_applied", JSONB, nullable=True))
    op.add_column("decision_log",
        sa.Column("alpha_rules_mode", sa.Text, nullable=True))
    op.add_column("decision_log",
        sa.Column("alpha_rule_size_multiplier", sa.Numeric(6, 4),
                  nullable=True))
    op.add_column("decision_log",
        sa.Column("alpha_rule_blocked", sa.Boolean, nullable=False,
                  server_default=sa.text("false")))
    op.add_column("decision_log",
        sa.Column("alpha_rule_block_reason", sa.Text, nullable=True))

    # paper_trade_log additions
    op.add_column("paper_trade_log",
        sa.Column("alpha_rule_adjusted", sa.Boolean, nullable=False,
                  server_default=sa.text("false")))
    op.add_column("paper_trade_log",
        sa.Column("alpha_rule_size_multiplier", sa.Numeric(6, 4),
                  nullable=True))
    op.add_column("paper_trade_log",
        sa.Column("alpha_rule_snapshot", JSONB, nullable=True))

    # Index on block flag for audit queries
    op.create_index(
        "ix_decision_log_alpha_rule_blocked",
        "decision_log", ["alpha_rule_blocked"],
    )


def downgrade() -> None:
    op.drop_index("ix_decision_log_alpha_rule_blocked",
                  table_name="decision_log")
    for c in ("alpha_rule_snapshot", "alpha_rule_size_multiplier",
              "alpha_rule_adjusted"):
        op.drop_column("paper_trade_log", c)
    for c in ("alpha_rule_block_reason", "alpha_rule_blocked",
              "alpha_rule_size_multiplier", "alpha_rules_mode",
              "alpha_rules_applied", "alpha_rule_adjustment"):
        op.drop_column("decision_log", c)
