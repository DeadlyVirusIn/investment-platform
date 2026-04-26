"""Phase V2-PROMOTION — v2_promotion_snapshot + v2_promotion_approval tables.

Phase 1 of the V2 promotion-trigger framework. Adds two read-only audit
tables to track weekly snapshots of the V2 vs B2 promotion-trigger
state machine and operator approval / rescission rows.

NEVER touches paper_trade_log, decision_log, paper_shadow_log,
shadow_strategy modules, engine_b_router, ENGINE_B_MODE, or any
production execution surface. These tables are written only by the
V2 promotion snapshot job (Phase 4) and the approval API (Phase 5),
neither of which is implemented yet.

Schema per docs/research/V2_PROMOTION_TRIGGER_DESIGN.md.

Revision ID: 045_v2_promotion_snapshot
Revises: 044_promotion_pause_column
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "045_v2_promotion_snapshot"
down_revision = "044_promotion_pause_column"
branch_labels = None
depends_on = None


_VALID_STATES = (
    "NOT_READY",
    "WATCH",
    "READY_FOR_REVIEW",
    "STRONG_CANDIDATE",
    "APPROVED_FOR_SHADOW_REPLACEMENT",
)

_VALID_DECISIONS = ("APPROVE", "RESCIND")


def upgrade() -> None:
    op.create_table(
        "v2_promotion_snapshot",
        sa.Column(
            "id", sa.BigInteger,
            sa.Identity(always=False, start=1),
            primary_key=True,
        ),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("iso_year", sa.Integer, nullable=False),
        sa.Column("iso_week", sa.Integer, nullable=False),
        sa.Column("comparison_bundle_json", JSONB, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("prior_state", sa.Text, nullable=True),
        sa.Column(
            "promotion_confidence",
            sa.Numeric(5, 4),
            nullable=False,
        ),
        sa.Column(
            "gates_json", JSONB, nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "verdict_streak", sa.Integer, nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "readiness_streak", sa.Integer, nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("rollback_reason", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "iso_year", "iso_week",
            name="ux_v2_promotion_snapshot_iso_week",
        ),
        sa.CheckConstraint(
            "state IN ('"
            + "', '".join(_VALID_STATES)
            + "')",
            name="ck_v2_promotion_snapshot_state",
        ),
        sa.CheckConstraint(
            "prior_state IS NULL OR prior_state IN ('"
            + "', '".join(_VALID_STATES)
            + "')",
            name="ck_v2_promotion_snapshot_prior_state",
        ),
        sa.CheckConstraint(
            "promotion_confidence >= 0 AND promotion_confidence <= 1",
            name="ck_v2_promotion_snapshot_confidence_range",
        ),
        sa.CheckConstraint(
            "verdict_streak >= 0 AND readiness_streak >= 0",
            name="ck_v2_promotion_snapshot_streaks_nonneg",
        ),
        sa.CheckConstraint(
            "iso_week >= 1 AND iso_week <= 53",
            name="ck_v2_promotion_snapshot_iso_week_range",
        ),
    )
    # Fast lookup of most-recent snapshots
    op.create_index(
        "ix_v2_promotion_snapshot_as_of_date_desc",
        "v2_promotion_snapshot",
        [sa.text("as_of_date DESC")],
    )
    # State filter
    op.create_index(
        "ix_v2_promotion_snapshot_state",
        "v2_promotion_snapshot",
        ["state"],
    )

    op.create_table(
        "v2_promotion_approval",
        sa.Column(
            "id", sa.BigInteger,
            sa.Identity(always=False, start=1),
            primary_key=True,
        ),
        sa.Column(
            "snapshot_id", sa.BigInteger,
            sa.ForeignKey(
                "v2_promotion_snapshot.id",
                ondelete="RESTRICT",
                name="fk_v2_promotion_approval_snapshot",
            ),
            nullable=False,
        ),
        sa.Column("decision", sa.Text, nullable=False),
        sa.Column("approver", sa.Text, nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column(
            "approved_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('" + "', '".join(_VALID_DECISIONS) + "')",
            name="ck_v2_promotion_approval_decision",
        ),
        sa.CheckConstraint(
            "char_length(rationale) >= 20",
            name="ck_v2_promotion_approval_rationale_min_len",
        ),
        sa.CheckConstraint(
            "char_length(approver) > 0",
            name="ck_v2_promotion_approval_approver_nonempty",
        ),
    )
    op.create_index(
        "ix_v2_promotion_approval_snapshot_id",
        "v2_promotion_approval",
        ["snapshot_id"],
    )
    op.create_index(
        "ix_v2_promotion_approval_approved_at_desc",
        "v2_promotion_approval",
        [sa.text("approved_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_v2_promotion_approval_approved_at_desc",
        table_name="v2_promotion_approval",
    )
    op.drop_index(
        "ix_v2_promotion_approval_snapshot_id",
        table_name="v2_promotion_approval",
    )
    op.drop_table("v2_promotion_approval")

    op.drop_index(
        "ix_v2_promotion_snapshot_state",
        table_name="v2_promotion_snapshot",
    )
    op.drop_index(
        "ix_v2_promotion_snapshot_as_of_date_desc",
        table_name="v2_promotion_snapshot",
    )
    op.drop_table("v2_promotion_snapshot")
