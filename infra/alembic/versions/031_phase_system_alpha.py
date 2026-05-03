"""Phase SYSTEM-ALPHA — factor attribution + failure analysis + health.

Extends decision_log and paper_trade_log with attribution/failure JSONB
fields. Adds system_health_score + feature_registry + provider_reliability.

Revision ID: 031_phase_system_alpha
Revises: 030_phase_ml3_shadow
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "031_phase_system_alpha"
down_revision = "030_phase_ml3_shadow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # decision_log additions
    op.add_column("decision_log",
        sa.Column("factor_attribution", JSONB, nullable=True))
    op.add_column("decision_log",
        sa.Column("factor_version", sa.Text, nullable=True))
    op.add_column("decision_log",
        sa.Column("feature_set_version", sa.Text, nullable=True))
    op.add_column("decision_log",
        sa.Column("risk_context", JSONB, nullable=True))

    # paper_trade_log additions
    op.add_column("paper_trade_log",
        sa.Column("failure_analysis", JSONB, nullable=True))
    op.add_column("paper_trade_log",
        sa.Column("failure_version", sa.Text, nullable=True))
    op.add_column("paper_trade_log",
        sa.Column("execution_quality", JSONB, nullable=True))
    op.add_column("paper_trade_log",
        sa.Column("slippage_adjusted_metrics", JSONB, nullable=True))

    # system_health_score
    op.create_table(
        "system_health_score",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("overall", sa.Integer, nullable=False),
        sa.Column("components", JSONB, nullable=False,
                  server_default="{}"),
        sa.Column("recommendation", sa.Text, nullable=True),
        sa.Column("warnings", JSONB, nullable=True),
    )
    op.create_index("ix_system_health_score_asof",
                    "system_health_score", ["as_of_date"])
    op.create_index("ix_system_health_score_created",
                    "system_health_score", ["created_at"])

    # feature_registry
    op.create_table(
        "feature_registry",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("feature_name", sa.Text, nullable=False),
        sa.Column("feature_set_version", sa.Text, nullable=False),
        sa.Column("dtype", sa.Text, nullable=False),
        sa.Column("nullable", sa.Boolean, nullable=False,
                  server_default=sa.text("true")),
        sa.Column("allowed_range", JSONB, nullable=True),
        sa.Column("source", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False,
                  server_default=sa.text("true")),
        sa.Column("notes", sa.Text, nullable=True),
        sa.UniqueConstraint(
            "feature_name", "feature_set_version",
            name="ux_feature_registry_name_version",
        ),
    )

    # provider_reliability
    op.create_table(
        "provider_reliability",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("reliability_score", sa.Numeric(6, 4), nullable=False,
                  server_default="0"),
        sa.Column("freshness_score",   sa.Numeric(6, 4), nullable=True),
        sa.Column("missing_rate",      sa.Numeric(6, 4), nullable=True),
        sa.Column("error_rate",        sa.Numeric(6, 4), nullable=True),
        sa.Column("latency_p50_ms",    sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "as_of_date", "provider",
            name="ux_provider_reliability_date_provider",
        ),
    )


def downgrade() -> None:
    op.drop_table("provider_reliability")
    op.drop_table("feature_registry")
    op.drop_index("ix_system_health_score_created",
                  table_name="system_health_score")
    op.drop_index("ix_system_health_score_asof",
                  table_name="system_health_score")
    op.drop_table("system_health_score")

    for c in ("slippage_adjusted_metrics", "execution_quality",
              "failure_version", "failure_analysis"):
        op.drop_column("paper_trade_log", c)

    for c in ("risk_context", "feature_set_version",
              "factor_version", "factor_attribution"):
        op.drop_column("decision_log", c)
