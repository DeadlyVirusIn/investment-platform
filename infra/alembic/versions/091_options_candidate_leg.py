"""Phase C Stage 0 — options_candidate_leg.

Persists the COMPLETE set of legs the generator selects for each
defined-risk options candidate (2 for credit spreads, 4 for iron
condors), priced from a single chain snapshot at generation time.

Stage 0 is additive only — nothing reads or writes this table until
Stage 2A (generator leg materialization, flag-gated by
OPTIONS_PERSIST_LEGS, default OFF). Economics derivation
(compute_risk_metrics) is Stage 2B and READS these legs; it is NOT part
of this migration.

Discipline:
  * FK to options_strategy_candidate (CASCADE delete) — legs are
    meaningless without their candidate.
  * UNIQUE(candidate_id, role) — one leg per role; guards duplicate
    inserts on idempotent re-runs.
  * entry_mid + priced_as_of NOT NULL — every persisted leg carries a
    price and the snapshot it was priced from. delta nullable (reserved
    for future POP).
  * Closed-enum CHECKs on role / side / option_type.

Revision ID: 091_options_candidate_leg
Revises: 090_opt_canary_lifecycle_run
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "091_options_candidate_leg"
down_revision = "090_opt_canary_lifecycle_run"
branch_labels = None
depends_on = None


ROLE_ENUM = "'short_put', 'long_put', 'short_call', 'long_call'"
SIDE_ENUM = "'SELL', 'BUY'"
OPTION_TYPE_ENUM = "'PUT', 'CALL'"


def upgrade() -> None:
    op.create_table(
        "options_candidate_leg",
        sa.Column(
            "id", sa.BigInteger(),
            sa.Identity(always=False), primary_key=True,
        ),
        sa.Column(
            "candidate_id", sa.BigInteger(),
            sa.ForeignKey(
                "options_strategy_candidate.id",
                name="fk_candidate_leg_candidate",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("role",        sa.Text(), nullable=False),
        sa.Column("side",        sa.Text(), nullable=False),
        sa.Column("option_type", sa.Text(), nullable=False),
        sa.Column("strike",      sa.Numeric(12, 4), nullable=False),
        sa.Column("expiry",      sa.Date(), nullable=False),
        sa.Column("option_symbol", sa.Text(), nullable=True),
        # Prices snapshotted at generation time — reproducible economics.
        sa.Column("entry_bid",   sa.Numeric(12, 4), nullable=True),
        sa.Column("entry_ask",   sa.Numeric(12, 4), nullable=True),
        sa.Column("entry_mid",   sa.Numeric(12, 4), nullable=False),
        sa.Column("delta",       sa.Numeric(8, 6), nullable=True),
        sa.Column(
            "priced_as_of", sa.DateTime(timezone=True), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "candidate_id", "role",
            name="ux_candidate_leg_candidate_role",
        ),
        sa.CheckConstraint(f"role IN ({ROLE_ENUM})", name="ck_candidate_leg_role"),
        sa.CheckConstraint(f"side IN ({SIDE_ENUM})", name="ck_candidate_leg_side"),
        sa.CheckConstraint(
            f"option_type IN ({OPTION_TYPE_ENUM})",
            name="ck_candidate_leg_option_type",
        ),
    )
    op.create_index(
        "ix_candidate_leg_candidate",
        "options_candidate_leg",
        ["candidate_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_candidate_leg_candidate",
        table_name="options_candidate_leg",
    )
    op.drop_table("options_candidate_leg")
