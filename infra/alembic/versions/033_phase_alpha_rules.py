"""Phase SYSTEM-ALPHA-3 — rule suggestions + versioning + performance.

Adds:
  * alpha_rule_suggestion  — generated suggestions awaiting apply/ignore
  * alpha_rule_active       — currently-applied rules (one per rule_id)
  * alpha_rule_history      — append-only audit of applies + rollbacks
  * rule_performance_log    — before/after impact tracking

Revision ID: 033_phase_alpha_rules
Revises: 032_phase_alpha_activation
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "033_phase_alpha_rules"
down_revision = "032_phase_alpha_activation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # alpha_rule_suggestion — generated, awaiting decision
    op.create_table(
        "alpha_rule_suggestion",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("rule_id",      sa.Text, nullable=False),
        sa.Column("rule_type",    sa.Text, nullable=False),
        sa.Column("target",       sa.Text, nullable=True),
        sa.Column("description",  sa.Text, nullable=False),
        sa.Column("confidence",   sa.Numeric(6, 4), nullable=False),
        sa.Column("sample_size",  sa.Integer, nullable=False),
        sa.Column("expected_impact", sa.Text, nullable=False,
                  server_default="uncertain"),
        sa.Column("risk_level",   sa.Text, nullable=False,
                  server_default="medium"),
        sa.Column("auto_applicable", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("parameters",   JSONB, nullable=False,
                  server_default="{}"),
        sa.Column("details",      JSONB, nullable=True),
        sa.Column("status", sa.Text, nullable=False,
                  server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("rule_id", "created_at",
                              name="ux_rule_suggestion_ruleid_created"),
    )
    op.create_index("ix_rule_suggestion_status",
                    "alpha_rule_suggestion", ["status"])
    op.create_index("ix_rule_suggestion_rule_id",
                    "alpha_rule_suggestion", ["rule_id"])

    # alpha_rule_active — live applied rules
    op.create_table(
        "alpha_rule_active",
        sa.Column("rule_id", sa.Text, primary_key=True),
        sa.Column("rule_type", sa.Text, nullable=False),
        sa.Column("parameters",   JSONB, nullable=False,
                  server_default="{}"),
        sa.Column("previous_parameters", JSONB, nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("applied_by", sa.Text, nullable=False,
                  server_default="system"),
        sa.Column("suggestion_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text, nullable=False,
                  server_default="active"),
    )

    # alpha_rule_history — audit
    op.create_table(
        "alpha_rule_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("rule_id",   sa.Text, nullable=False),
        sa.Column("action",    sa.Text, nullable=False),   # apply | rollback
        sa.Column("parameters",          JSONB, nullable=True),
        sa.Column("previous_parameters", JSONB, nullable=True),
        sa.Column("applied_by", sa.Text, nullable=False,
                  server_default="system"),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False,
                  server_default="active"),
        sa.Column("impact_metrics", JSONB, nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rule_history_rule_id",
                    "alpha_rule_history", ["rule_id"])
    op.create_index("ix_rule_history_applied",
                    "alpha_rule_history", ["applied_at"])

    # rule_performance_log — per-rule before/after
    op.create_table(
        "rule_performance_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("rule_id",    sa.Text, nullable=False),
        sa.Column("window_start", sa.Date, nullable=False),
        sa.Column("window_end",   sa.Date, nullable=False),
        sa.Column("before", JSONB, nullable=True),
        sa.Column("after",  JSONB, nullable=True),
        sa.Column("delta",  JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rule_perf_rule_id",
                    "rule_performance_log", ["rule_id"])


def downgrade() -> None:
    op.drop_index("ix_rule_perf_rule_id", table_name="rule_performance_log")
    op.drop_table("rule_performance_log")
    op.drop_index("ix_rule_history_applied", table_name="alpha_rule_history")
    op.drop_index("ix_rule_history_rule_id", table_name="alpha_rule_history")
    op.drop_table("alpha_rule_history")
    op.drop_table("alpha_rule_active")
    op.drop_index("ix_rule_suggestion_rule_id",
                  table_name="alpha_rule_suggestion")
    op.drop_index("ix_rule_suggestion_status",
                  table_name="alpha_rule_suggestion")
    op.drop_table("alpha_rule_suggestion")
