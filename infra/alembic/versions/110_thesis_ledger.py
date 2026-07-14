"""Thesis Ledger core — thesis + thesis_evidence + thesis_revision
(Elite ArthOS Sprint 6, Priority 2).

Generated per docs/architecture/THESIS_LEDGER_SPEC.md §4/§11.
NOT applied to any database (orchestrator applies). Additive only;
downgrade drops the three tables. All FKs ON DELETE RESTRICT — no
cascade path can silently destroy ledger history.

Revision ID: 110_thesis_ledger
Revises: 109_research_run
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "110_thesis_ledger"
down_revision = "109_research_run"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "thesis",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("asset.id")),
        sa.Column("scope", sa.String(16), nullable=False,
                  server_default="company"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("statement", sa.Text, nullable=False),
        sa.Column("wrong_if", sa.Text, nullable=False),
        sa.Column("horizon", sa.String(16), nullable=False,
                  server_default="months"),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="forming"),
        sa.Column("status_reason", sa.Text),
        sa.Column("status_changed_at", sa.DateTime(timezone=True)),
        sa.Column("invalidated_reason", sa.Text),
        sa.Column("supersedes_thesis_id", sa.String(36),
                  sa.ForeignKey("thesis.id", ondelete="RESTRICT")),
        sa.Column("created_by", sa.String(64), nullable=False,
                  server_default="owner"),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "scope IN ('company','sector','theme','macro')",
            name="ck_thesis_scope",
        ),
        sa.CheckConstraint(
            "status IN ('forming','active','strengthened','weakened',"
            "'invalidated','closed')",
            name="ck_thesis_status",
        ),
        sa.CheckConstraint(
            "horizon IN ('weeks','months','quarters','years')",
            name="ck_thesis_horizon",
        ),
        # A thesis without a falsifier is not a thesis — mandatory,
        # non-trivial wrong_if at the DB layer.
        sa.CheckConstraint(
            "char_length(wrong_if) > 10",
            name="ck_thesis_wrong_if_len",
        ),
        sa.CheckConstraint(
            "status <> 'invalidated' OR invalidated_reason IS NOT NULL",
            name="ck_thesis_invalidated",
        ),
        sa.CheckConstraint(
            "scope <> 'company' OR asset_id IS NOT NULL",
            name="ck_thesis_company_asset",
        ),
    )
    op.create_index("ix_thesis_asset", "thesis", ["asset_id"])
    op.create_index("ix_thesis_status", "thesis", ["status"])

    op.create_table(
        "thesis_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("thesis_id", sa.String(36),
                  sa.ForeignKey("thesis.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("stance", sa.String(16), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("source_name", sa.String(128), nullable=False),
        sa.Column("source_url", sa.Text),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("weight", sa.Numeric(5, 4)),
        sa.Column("provenance", sa.String(16), nullable=False),
        sa.Column("review_status", sa.String(16), nullable=False,
                  server_default="pending"),
        sa.Column("reviewed_by", sa.String(64)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "stance IN ('supports','contradicts')",
            name="ck_thesis_evidence_stance",
        ),
        sa.CheckConstraint(
            "category IN ('price_action','fundamentals','news','analyst',"
            "'macro','other')",
            name="ck_thesis_evidence_category",
        ),
        sa.CheckConstraint(
            "provenance IN ('generated','human')",
            name="ck_thesis_evidence_provenance",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending','approved','rejected')",
            name="ck_thesis_evidence_review",
        ),
        sa.CheckConstraint(
            "weight IS NULL OR (weight >= 0 AND weight <= 1)",
            name="ck_thesis_evidence_weight",
        ),
        # generated evidence must carry a source URL — provenance rule at
        # the DB layer (spec §7)
        sa.CheckConstraint(
            "provenance <> 'generated' OR source_url IS NOT NULL",
            name="ck_thesis_evidence_gen_url",
        ),
        # reviewed rows must say who/when
        sa.CheckConstraint(
            "review_status = 'pending' "
            "OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_thesis_evidence_reviewed",
        ),
    )
    op.create_index("ix_thesis_evidence_thesis", "thesis_evidence",
                    ["thesis_id", "review_status"])
    op.create_index(
        "ix_thesis_evidence_pending", "thesis_evidence", ["review_status"],
        postgresql_where=sa.text("review_status = 'pending'"),
    )

    # Immutable revision history: the service appends one row per thesis
    # mutation. No UPDATE/DELETE path exists in application code.
    op.create_table(
        "thesis_revision",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("thesis_id", sa.String(36),
                  sa.ForeignKey("thesis.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("revision_no", sa.Integer, nullable=False),
        sa.Column("snapshot", postgresql.JSONB, nullable=False),
        sa.Column("changed_by", sa.String(64), nullable=False,
                  server_default="owner"),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("thesis_id", "revision_no",
                            name="uq_thesis_revision_no"),
        sa.CheckConstraint("revision_no >= 1", name="ck_thesis_revision_no"),
    )
    op.create_index("ix_thesis_revision_thesis", "thesis_revision",
                    ["thesis_id", sa.text("revision_no DESC")])


def downgrade() -> None:
    op.drop_index("ix_thesis_revision_thesis", table_name="thesis_revision")
    op.drop_table("thesis_revision")
    for ix in ("ix_thesis_evidence_pending", "ix_thesis_evidence_thesis"):
        op.drop_index(ix, table_name="thesis_evidence")
    op.drop_table("thesis_evidence")
    for ix in ("ix_thesis_status", "ix_thesis_asset"):
        op.drop_index(ix, table_name="thesis")
    op.drop_table("thesis")
