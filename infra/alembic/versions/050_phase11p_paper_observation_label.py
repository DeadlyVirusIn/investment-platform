"""Phase 11P.1 - paper_observation_label table.

Append-only label store for paper trades + paper observations across
both equity and options domains. UNIQUE constraints ensure no
duplicate label rows per (domain, foreign-key, label_version).

Provisional rows (is_provisional=TRUE) may be re-evaluated and
finalized via the labeller's --reprocess-provisional path which
issues UPDATE statements only against rows where
is_provisional=TRUE AND entry_date <= cutoff.

NEVER references any strict-engine table. NEVER references
v2_promotion_*, engine_b*, shadow_strategy*, paper_trade_log.

Revision ID: 050_phase11p_paper_observation_label
Revises: 049_phase11p_paper_label_columns
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "050_phase11p_paper_observation_label"
down_revision = "049_phase11p_paper_label_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_observation_label",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "paper_decision_log_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("paper_trade_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "options_paper_trade_id", sa.BigInteger(), nullable=True,
        ),
        sa.Column(
            "options_observation_id", sa.Text(), nullable=True,
        ),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=True),
        sa.Column(
            "failed_gates",
            sa.dialects.postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "gate_snapshot", JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "entry_price", sa.Numeric(18, 6), nullable=True,
        ),
        sa.Column("return_1d",  sa.Numeric(10, 6), nullable=True),
        sa.Column("return_3d",  sa.Numeric(10, 6), nullable=True),
        sa.Column("return_5d",  sa.Numeric(10, 6), nullable=True),
        sa.Column("return_10d", sa.Numeric(10, 6), nullable=True),
        sa.Column("return_20d", sa.Numeric(10, 6), nullable=True),
        sa.Column(
            "max_adverse_excursion", sa.Numeric(10, 6), nullable=True,
        ),
        sa.Column(
            "max_favorable_excursion", sa.Numeric(10, 6), nullable=True,
        ),
        sa.Column("outcome_class", sa.Text(), nullable=True),
        sa.Column(
            "outcome_threshold_pct", sa.Numeric(6, 4), nullable=True,
        ),
        sa.Column(
            "label_confidence", sa.Numeric(6, 4), nullable=True,
        ),
        sa.Column(
            "label_version", sa.Text(), nullable=False,
            server_default=sa.text("'label-v1.0.0'"),
        ),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column(
            "is_provisional", sa.Boolean(),
            nullable=False, server_default=sa.text("TRUE"),
        ),
        sa.CheckConstraint(
            "domain IN ('equity', 'options')",
            name="ck_paper_observation_label_domain",
        ),
        sa.CheckConstraint(
            "source IN ('strict_paper','exploratory_paper',"
            "'options_paper','options_paper_mock','backfill')",
            name="ck_paper_observation_label_source",
        ),
        sa.CheckConstraint(
            "outcome_class IS NULL OR outcome_class IN "
            "('positive','negative','neutral')",
            name="ck_paper_observation_label_outcome_class",
        ),
    )
    op.create_unique_constraint(
        "uq_paper_observation_label_decision",
        "paper_observation_label",
        ["domain", "paper_decision_log_id", "label_version"],
    )
    op.create_unique_constraint(
        "uq_paper_observation_label_paper_trade",
        "paper_observation_label",
        ["domain", "paper_trade_id", "label_version"],
    )
    op.create_unique_constraint(
        "uq_paper_observation_label_options_paper_trade",
        "paper_observation_label",
        ["domain", "options_paper_trade_id", "label_version"],
    )
    op.create_unique_constraint(
        "uq_paper_observation_label_options_observation",
        "paper_observation_label",
        ["domain", "options_observation_id", "label_version"],
    )
    op.create_index(
        "ix_paper_observation_label_entry_date",
        "paper_observation_label", ["entry_date"],
    )
    op.create_index(
        "ix_paper_observation_label_domain_source",
        "paper_observation_label", ["domain", "source"],
    )
    op.create_index(
        "ix_paper_observation_label_provisional",
        "paper_observation_label", ["is_provisional"],
        postgresql_where=sa.text("is_provisional"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_paper_observation_label_provisional",
        table_name="paper_observation_label",
    )
    op.drop_index(
        "ix_paper_observation_label_domain_source",
        table_name="paper_observation_label",
    )
    op.drop_index(
        "ix_paper_observation_label_entry_date",
        table_name="paper_observation_label",
    )
    op.drop_table("paper_observation_label")
