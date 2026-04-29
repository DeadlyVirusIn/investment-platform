"""Phase 11R.1 - paper_research_fill table + paper_observation_label
source-CHECK expansion.

Hard-isolated from strict engine. Append-only. NEVER references
paper_trade / paper_position / decision_log / paper_portfolio.

CHECK constraints encode the isolation invariants:
  source = 'research_fast_fill'
  strict_fill_model_used = FALSE

Revision ID: 051_research_fast_fill
Revises: 050_paper_obs_label
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "051_research_fast_fill"
down_revision = "050_paper_obs_label"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_research_fill",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "source", sa.Text(), nullable=False,
            server_default=sa.text("'research_fast_fill'"),
        ),
        sa.Column(
            "fill_model", sa.Text(), nullable=False,
            server_default=sa.text("'same_day_research_v1'"),
        ),
        sa.Column(
            "label_version", sa.Text(), nullable=False,
            server_default=sa.text("'research-fast-fill-v1.0.0'"),
        ),
        sa.Column(
            "ml_label_eligible", sa.Boolean(), nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "strict_fill_model_used", sa.Boolean(), nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "decision_ts", sa.DateTime(timezone=True), nullable=False,
        ),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("underlying", sa.Text(), nullable=False),
        sa.Column("asset_id", sa.Text(), nullable=True),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("engine", sa.Text(), nullable=True),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column(
            "fill_price", sa.Numeric(20, 6), nullable=False,
        ),
        sa.Column(
            "fill_price_source", sa.Text(), nullable=False,
        ),
        sa.Column(
            "fill_ts", sa.DateTime(timezone=True), nullable=False,
        ),
        sa.Column(
            "qty", sa.Numeric(28, 10), nullable=False,
        ),
        sa.Column(
            "gate_snapshot", JSONB(),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "failed_gates",
            sa.dialects.postgresql.ARRAY(sa.Text()),
            nullable=False, server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("audit_jsonl_path", sa.Text(), nullable=True),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "source", "as_of_date", "underlying", "rule_id",
            "side", "fill_model", "label_version",
            name="uq_paper_research_fill_natural_key",
        ),
        sa.CheckConstraint(
            "source = 'research_fast_fill'",
            name="ck_paper_research_fill_source",
        ),
        sa.CheckConstraint(
            "strict_fill_model_used = FALSE",
            name="ck_paper_research_fill_strict_off",
        ),
        sa.CheckConstraint(
            "fill_price_source IN ('open','vwap','close')",
            name="ck_paper_research_fill_price_source",
        ),
        sa.CheckConstraint(
            "side IN ('BUY','SELL')",
            name="ck_paper_research_fill_side",
        ),
    )
    op.create_index(
        "ix_paper_research_fill_as_of_date",
        "paper_research_fill", ["as_of_date"],
    )
    op.create_index(
        "ix_paper_research_fill_underlying",
        "paper_research_fill", ["underlying"],
    )

    # Expand paper_observation_label.source allowed values.
    # Drop + recreate the existing CHECK with the additional value.
    op.drop_constraint(
        "ck_paper_observation_label_source",
        "paper_observation_label",
        type_="check",
    )
    op.create_check_constraint(
        "ck_paper_observation_label_source",
        "paper_observation_label",
        "source IN ("
        "'strict_paper','exploratory_paper',"
        "'options_paper','options_paper_mock','backfill',"
        "'research_fast_fill'"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_paper_observation_label_source",
        "paper_observation_label",
        type_="check",
    )
    op.create_check_constraint(
        "ck_paper_observation_label_source",
        "paper_observation_label",
        "source IN ("
        "'strict_paper','exploratory_paper',"
        "'options_paper','options_paper_mock','backfill'"
        ")",
    )
    op.drop_index(
        "ix_paper_research_fill_underlying",
        table_name="paper_research_fill",
    )
    op.drop_index(
        "ix_paper_research_fill_as_of_date",
        table_name="paper_research_fill",
    )
    op.drop_table("paper_research_fill")
