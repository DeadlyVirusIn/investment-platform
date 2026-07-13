"""Recommendation Publication Preflight — immutable verdict ledger (Wave 1A).

One additive table, ``recommendation_preflight``: an append-only record of
every deterministic publication-gate evaluation. A row is written once and
never updated — re-evaluation with different inputs appends a NEW row; an
identical (recommendation, rule set, input hash) evaluation is idempotent via
the unique key (concurrent evaluators race safely with ON CONFLICT DO
NOTHING). There is deliberately no UPDATE path in the service and nothing an
LLM or administrator can silently override.

FK to recommendation is plain (no cascade): recommendations are never deleted
in this system; if one ever were, the verdict ledger must make that fail
loudly rather than silently losing audit history.

CHECK constraints pin the verdict vocabulary and bound the JSON payload sizes
so a malfunctioning evaluator cannot bloat the table.

PROPOSED as revision 119 after verifying ``alembic heads`` == 118 on this
branch (verified 2026-07-12). Validated up/down/up on an ephemeral container
before any dev application; prod application is a separate approval-gated
step (prod is at 109).

Revision ID: 119_recommendation_preflight
Revises: 118_execution_lease
Create Date: 2026-07-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "119_recommendation_preflight"
down_revision = "118_execution_lease"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_preflight",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "recommendation_id",
            sa.String(36),
            sa.ForeignKey("recommendation.id"),
            nullable=False,
        ),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("rule_set_version", sa.String(16), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("checks_json", sa.Text, nullable=False),
        sa.Column("limitations_json", sa.Text, nullable=False),
        sa.Column("blocking_reasons_json", sa.Text, nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluator_git_sha", sa.String(64), nullable=False),
        sa.Column("source_freshness_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "verdict IN ('READY','READY_WITH_LIMITATIONS','HOLD','BLOCKED')",
            name="ck_rec_preflight_verdict",
        ),
        sa.CheckConstraint(
            "char_length(checks_json) <= 20000",
            name="ck_rec_preflight_checks_bound",
        ),
        sa.CheckConstraint(
            "char_length(limitations_json) <= 8000",
            name="ck_rec_preflight_limitations_bound",
        ),
        sa.CheckConstraint(
            "char_length(blocking_reasons_json) <= 8000",
            name="ck_rec_preflight_blocking_bound",
        ),
        sa.UniqueConstraint(
            "recommendation_id",
            "rule_set_version",
            "input_hash",
            name="ux_rec_preflight_idempotency",
        ),
    )
    op.create_index(
        "ix_rec_preflight_rec_created",
        "recommendation_preflight",
        ["recommendation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_rec_preflight_rec_created", table_name="recommendation_preflight")
    op.drop_table("recommendation_preflight")
