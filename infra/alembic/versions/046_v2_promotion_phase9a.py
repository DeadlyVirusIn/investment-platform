"""Phase 9A — V2 promotion-trigger governance hardening.

Extensions to v2_promotion_snapshot + v2_promotion_approval:
  * Add SUSPENDED to allowed states (CHECK constraint update)
  * Add snapshot_content_hash (sha256 of canonicalized comparison_bundle_json)
  * Add schema_version (integer; bumps when bundle shape changes)
  * Add code_version (text; git sha or release tag at insert time)
  * Add evaluated_at_utc (explicit UTC timestamp distinct from created_at)
  * Add timezone (text; the SCHEDULER_TZ in effect at insert)
  * Approval table gains content_hash_at_approval (binds approval to
    exact evidence; if subsequent recompute changes the hash,
    pending approvals are invalidated by the snapshot job)
  * Approval CHECK extended to include 'RESUME_FROM_SUSPENDED'

NEVER touches paper_trade_log, decision_log, paper_shadow_log, or any
production execution surface.

Revision ID: 046_v2_promotion_phase9a
Revises: 045_v2_promotion_snapshot
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "046_v2_promotion_phase9a"
down_revision = "045_v2_promotion_snapshot"
branch_labels = None
depends_on = None


_VALID_STATES_PHASE9A = (
    "NOT_READY",
    "SUSPENDED",
    "WATCH",
    "READY_FOR_REVIEW",
    "STRONG_CANDIDATE",
    "APPROVED_FOR_SHADOW_REPLACEMENT",
)

_VALID_DECISIONS_PHASE9A = ("APPROVE", "RESCIND", "RESUME_FROM_SUSPENDED")


def _states_check_clause() -> str:
    return "(" + ", ".join(f"'{s}'" for s in _VALID_STATES_PHASE9A) + ")"


def _decisions_check_clause() -> str:
    return "(" + ", ".join(f"'{d}'" for d in _VALID_DECISIONS_PHASE9A) + ")"


def upgrade() -> None:
    # --- v2_promotion_snapshot: new columns -----------------------------
    op.add_column(
        "v2_promotion_snapshot",
        sa.Column(
            "snapshot_content_hash", sa.String(length=64), nullable=True,
        ),
    )
    op.add_column(
        "v2_promotion_snapshot",
        sa.Column(
            "schema_version", sa.Integer, nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "v2_promotion_snapshot",
        sa.Column("code_version", sa.Text, nullable=True),
    )
    op.add_column(
        "v2_promotion_snapshot",
        sa.Column(
            "evaluated_at_utc", sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "v2_promotion_snapshot",
        sa.Column("timezone", sa.Text, nullable=True),
    )

    # --- v2_promotion_snapshot: extend state CHECK to allow SUSPENDED ---
    op.execute("ALTER TABLE v2_promotion_snapshot DROP CONSTRAINT "
                "ck_v2_promotion_snapshot_state")
    op.create_check_constraint(
        "ck_v2_promotion_snapshot_state",
        "v2_promotion_snapshot",
        f"state IN {_states_check_clause()}",
    )
    op.execute("ALTER TABLE v2_promotion_snapshot DROP CONSTRAINT "
                "ck_v2_promotion_snapshot_prior_state")
    op.create_check_constraint(
        "ck_v2_promotion_snapshot_prior_state",
        "v2_promotion_snapshot",
        f"prior_state IS NULL OR prior_state IN {_states_check_clause()}",
    )

    # --- Index on content_hash for fast hash-lookup (approval validation) ---
    op.create_index(
        "ix_v2_promotion_snapshot_content_hash",
        "v2_promotion_snapshot",
        ["snapshot_content_hash"],
    )

    # --- v2_promotion_approval: bind to snapshot content hash + decision ---
    op.add_column(
        "v2_promotion_approval",
        sa.Column(
            "snapshot_content_hash_at_approval",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.execute("ALTER TABLE v2_promotion_approval DROP CONSTRAINT "
                "ck_v2_promotion_approval_decision")
    op.create_check_constraint(
        "ck_v2_promotion_approval_decision",
        "v2_promotion_approval",
        f"decision IN {_decisions_check_clause()}",
    )


def downgrade() -> None:
    op.execute("ALTER TABLE v2_promotion_approval DROP CONSTRAINT "
                "ck_v2_promotion_approval_decision")
    op.create_check_constraint(
        "ck_v2_promotion_approval_decision",
        "v2_promotion_approval",
        "decision IN ('APPROVE', 'RESCIND')",
    )
    op.drop_column(
        "v2_promotion_approval", "snapshot_content_hash_at_approval",
    )

    op.drop_index(
        "ix_v2_promotion_snapshot_content_hash",
        table_name="v2_promotion_snapshot",
    )
    op.execute("ALTER TABLE v2_promotion_snapshot DROP CONSTRAINT "
                "ck_v2_promotion_snapshot_prior_state")
    op.create_check_constraint(
        "ck_v2_promotion_snapshot_prior_state",
        "v2_promotion_snapshot",
        "prior_state IS NULL OR prior_state IN ("
        "'NOT_READY', 'WATCH', 'READY_FOR_REVIEW', "
        "'STRONG_CANDIDATE', 'APPROVED_FOR_SHADOW_REPLACEMENT')",
    )
    op.execute("ALTER TABLE v2_promotion_snapshot DROP CONSTRAINT "
                "ck_v2_promotion_snapshot_state")
    op.create_check_constraint(
        "ck_v2_promotion_snapshot_state",
        "v2_promotion_snapshot",
        "state IN ("
        "'NOT_READY', 'WATCH', 'READY_FOR_REVIEW', "
        "'STRONG_CANDIDATE', 'APPROVED_FOR_SHADOW_REPLACEMENT')",
    )
    op.drop_column("v2_promotion_snapshot", "timezone")
    op.drop_column("v2_promotion_snapshot", "evaluated_at_utc")
    op.drop_column("v2_promotion_snapshot", "code_version")
    op.drop_column("v2_promotion_snapshot", "schema_version")
    op.drop_column("v2_promotion_snapshot", "snapshot_content_hash")
