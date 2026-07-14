"""research_run registry + append-only approval table (Elite ArthOS Sprint 5).

PROPOSED — generated for review per RESEARCH_RUN_REGISTRY_SPEC.md.
NOT applied to any database. Additive only; downgrade drops both tables.

Revision ID: 109_research_run
Revises: 108_app_user_role
Create Date: 2026-07-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "109_research_run"
down_revision = "108_app_user_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_run",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_uid", sa.String(32), nullable=False),
        sa.Column("run_type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="draft"),
        sa.Column("git_sha", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64)),
        sa.Column("feature_schema_version", sa.String(64)),
        sa.Column("data_start", sa.Date),
        sa.Column("data_end", sa.Date),
        sa.Column("data_hash", sa.String(64)),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("random_seed", sa.BigInteger),
        sa.Column("split_method", sa.String(32)),
        sa.Column("parameters", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("metrics", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("artifact_manifest", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("parent_run_id", sa.String(36),
                  sa.ForeignKey("research_run.id", ondelete="RESTRICT")),
        sa.Column("promotion_status", sa.String(16), nullable=False,
                  server_default="none"),
        sa.Column("promoted_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(64), nullable=False,
                  server_default="owner"),
        sa.Column("error_summary", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("run_uid", name="uq_research_run_uid"),
        sa.CheckConstraint(
            "run_type IN ('walk_forward','optuna_study','optuna_trial',"
            "'calibration','backtest','feature_study','drift_study','other')",
            name="ck_research_run_type",
        ),
        sa.CheckConstraint(
            "status IN ('draft','running','completed','failed','aborted')",
            name="ck_research_run_status",
        ),
        sa.CheckConstraint(
            "promotion_status IN ('none','candidate','approved','rejected',"
            "'promoted','rolled_back')",
            name="ck_research_run_promotion",
        ),
        sa.CheckConstraint(
            "status NOT IN ('completed','failed','aborted') "
            "OR completed_at IS NOT NULL",
            name="ck_research_run_completed",
        ),
        sa.CheckConstraint(
            "status <> 'failed' OR error_summary IS NOT NULL",
            name="ck_research_run_error",
        ),
        sa.CheckConstraint(
            "promotion_status IN ('none','rejected') OR status = 'completed'",
            name="ck_research_run_promo_completed",
        ),
        sa.CheckConstraint(
            "pg_column_size(parameters) <= 65536",
            name="ck_research_run_params_size",
        ),
        sa.CheckConstraint(
            "pg_column_size(metrics) <= 65536",
            name="ck_research_run_metrics_size",
        ),
        sa.CheckConstraint(
            "pg_column_size(artifact_manifest) <= 65536",
            name="ck_research_run_manifest_size",
        ),
    )
    op.create_index("ix_research_run_type_created", "research_run",
                    ["run_type", sa.text("created_at DESC")])
    op.create_index("ix_research_run_status", "research_run", ["status"])
    op.create_index("ix_research_run_parent", "research_run", ["parent_run_id"])
    op.create_index("ix_research_run_git_sha", "research_run", ["git_sha"])
    op.create_index("ix_research_run_config_hash", "research_run",
                    ["config_hash"])
    op.create_index(
        "ix_research_run_promoted", "research_run", ["promotion_status"],
        postgresql_where=sa.text("promotion_status <> 'none'"),
    )

    op.create_table(
        "research_run_approval",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36),
                  sa.ForeignKey("research_run.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("approver", sa.String(64), nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("run_content_hash", sa.String(64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "decision IN ('approve','reject','promote','rollback')",
            name="ck_research_run_approval_decision",
        ),
    )
    op.create_index("ix_research_run_approval_run", "research_run_approval",
                    ["run_id", sa.text("decided_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_research_run_approval_run",
                  table_name="research_run_approval")
    op.drop_table("research_run_approval")
    for ix in ("ix_research_run_promoted", "ix_research_run_config_hash",
               "ix_research_run_git_sha", "ix_research_run_parent",
               "ix_research_run_status", "ix_research_run_type_created"):
        op.drop_index(ix, table_name="research_run")
    op.drop_table("research_run")
