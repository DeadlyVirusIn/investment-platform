"""Phase L M084 — envelope generation run telemetry.

Per-portfolio, per-run roll-up of envelope generation outcomes.
Single thin table; one row per (run_id, portfolio_id) pair.

Goals:
  * Detect coverage regressions (envelopes_attached / trades_executed
    ratio dropping).
  * Surface skip-reason distribution so substrate gaps stay visible
    without grep'ing logs.
  * Cheap join target for future operator dashboards.

Append-only at the API layer. No UPDATE path.

Revision ID: 084_phase_l_envelope_gen_run
Revises: 083_phase_l_audit_unique_pair
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "084_phase_l_envelope_gen_run"
down_revision = "083_phase_l_audit_unique_pair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "envelope_generation_run",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("portfolio_id", sa.String(36), nullable=False),
        sa.Column("as_of_date", sa.Date, nullable=True),  # NULL = live run
        sa.Column("trades_executed", sa.Integer, nullable=False, default=0),
        sa.Column("envelopes_attached", sa.Integer, nullable=False, default=0),
        sa.Column("skip_features_unavailable", sa.Integer, nullable=False, default=0),
        sa.Column("skip_generator_returned_none", sa.Integer, nullable=False, default=0),
        sa.Column("skip_exception", sa.Integer, nullable=False, default=0),
        sa.Column(
            "skeleton_distribution",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_envelope_gen_run_portfolio_asof",
        "envelope_generation_run",
        ["portfolio_id", "as_of_date"],
    )
    op.create_index(
        "ix_envelope_gen_run_created_at",
        "envelope_generation_run",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_envelope_gen_run_created_at",
        table_name="envelope_generation_run",
    )
    op.drop_index(
        "ix_envelope_gen_run_portfolio_asof",
        table_name="envelope_generation_run",
    )
    op.drop_table("envelope_generation_run")
