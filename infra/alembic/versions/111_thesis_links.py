"""Thesis Ledger satellites — thesis_catalyst + thesis_risk + thesis_link
(Elite ArthOS Sprint 6, Priority 2).

Generated per docs/architecture/THESIS_LEDGER_SPEC.md §4/§11 (split from
the core migration so the core can ship and be exercised first).
NOT applied to any database (orchestrator applies). Additive only;
downgrade drops the three tables.

thesis_link is polymorphic — deliberately NO hard FK on target_id
(targets span recommendation / paper_trade / recommendation_outcome and a
future `lesson` table); existence is validated in the service layer at
link time. PaperObservationLabel precedent.

Revision ID: 111_thesis_links
Revises: 110_thesis_ledger
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "111_thesis_links"
down_revision = "110_thesis_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "thesis_catalyst",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("thesis_id", sa.String(36),
                  sa.ForeignKey("thesis.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("expected_at", sa.Date),
        sa.Column("window_days", sa.Integer),
        sa.Column("direction", sa.String(16), nullable=False,
                  server_default="either"),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "direction IN ('helps','hurts','either')",
            name="ck_thesis_catalyst_direction",
        ),
    )
    op.create_index("ix_thesis_catalyst_thesis", "thesis_catalyst",
                    ["thesis_id"])

    op.create_table(
        "thesis_risk",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("thesis_id", sa.String(36),
                  sa.ForeignKey("thesis.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("detail", sa.Text),
        sa.Column("severity", sa.String(8), nullable=False,
                  server_default="medium"),
        sa.Column("materialized_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "severity IN ('low','medium','high')",
            name="ck_thesis_risk_severity",
        ),
    )
    op.create_index("ix_thesis_risk_thesis", "thesis_risk", ["thesis_id"])

    op.create_table(
        "thesis_link",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("thesis_id", sa.String(36),
                  sa.ForeignKey("thesis.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("target_type", sa.String(24), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "target_type IN ('recommendation','paper_trade','outcome',"
            "'lesson')",
            name="ck_thesis_link_type",
        ),
        sa.UniqueConstraint("thesis_id", "target_type", "target_id",
                            name="uq_thesis_link"),
    )
    op.create_index("ix_thesis_link_target", "thesis_link",
                    ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_index("ix_thesis_link_target", table_name="thesis_link")
    op.drop_table("thesis_link")
    op.drop_index("ix_thesis_risk_thesis", table_name="thesis_risk")
    op.drop_table("thesis_risk")
    op.drop_index("ix_thesis_catalyst_thesis", table_name="thesis_catalyst")
    op.drop_table("thesis_catalyst")
