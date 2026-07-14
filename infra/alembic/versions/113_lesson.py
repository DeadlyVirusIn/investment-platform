"""Learning Loop — lesson table (Elite ArthOS, Priority 6).

Generated per docs/architecture/LEARNING_LOOP_SPEC.md (Priority-6 slice:
table + service only — no router, no scheduler wiring, no generator job).
NOT applied to any database (orchestrator applies; validated on an
ephemeral container only). Additive only; downgrade drops the table.

A lesson is one post-outcome learning record tied to the decision it
judges. Bias posture is structural, not stylistic:
  * `original_thesis_quote` is VERBATIM as-of-decision-time text — the
    service containment-checks it against thesis_revision snapshots at or
    before recommendation.generated_at (hindsight guard, spec §4.1);
  * generated lessons are FORCED to review_state='draft'; approval is a
    human action carrying reviewer identity (CHECK ck_lesson_reviewed);
  * approving a lesson NEVER mutates thesis status — it may only attach a
    thesis_link(target_type='lesson') row (spec §1 rule 1, NON-GOALS).

FK posture: recommendation RESTRICT (a judged decision can never vanish
under its lesson), paper_trade SET NULL (trade linkage is convenience,
not identity), thesis RESTRICT (belief history is never cascaded away).
`outcome_ref` is a soft reference to recommendation_outcome.id
(thesis_link precedent: existence-checked in the service, no hard FK).

Revision ID: 113_lesson
Revises: 112_research_inbox
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "113_lesson"
down_revision = "112_research_inbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lesson",
        sa.Column("id", sa.String(36), primary_key=True),
        # subject links — nullable at the DB layer (future aggregate
        # lessons carry no single subject); the service requires
        # recommendation_id + thesis_id for single-outcome lessons
        sa.Column("recommendation_id", sa.String(36),
                  sa.ForeignKey("recommendation.id", ondelete="RESTRICT")),
        sa.Column("paper_trade_id", sa.String(36),
                  sa.ForeignKey("paper_trade.id", ondelete="SET NULL")),
        # soft reference to recommendation_outcome.id — service
        # existence-checks it read-only (thesis_link precedent)
        sa.Column("outcome_ref", sa.String(36)),
        sa.Column("thesis_id", sa.String(36),
                  sa.ForeignKey("thesis.id", ondelete="RESTRICT")),
        # lesson body
        sa.Column("what_happened", sa.Text, nullable=False),
        # VERBATIM as-of-decision-time text — hindsight guard (spec §4.1)
        sa.Column("original_thesis_quote", sa.Text, nullable=False),
        sa.Column("expectation", sa.Text),
        sa.Column("evidence_correct", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("evidence_misleading", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("thesis_effect", sa.String(16), nullable=False,
                  server_default="none"),
        sa.Column("calibration_note", sa.Text),
        sa.Column("risk_controls_note", sa.Text),
        sa.Column("should_change", sa.Text),
        # provenance + review
        sa.Column("provenance", sa.String(16), nullable=False),
        sa.Column("review_state", sa.String(16), nullable=False,
                  server_default="draft"),
        sa.Column("reviewed_by", sa.String(64)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(64), nullable=False,
                  server_default="owner"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "thesis_effect IN ('strengthened','weakened','invalidated','none')",
            name="ck_lesson_effect",
        ),
        sa.CheckConstraint(
            "provenance IN ('generated','human')",
            name="ck_lesson_provenance",
        ),
        sa.CheckConstraint(
            "review_state IN ('draft','approved','rejected')",
            name="ck_lesson_review",
        ),
        # approved/rejected rows must carry the reviewer trail
        # (thesis_evidence / research_report precedent)
        sa.CheckConstraint(
            "review_state = 'draft' "
            "OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_lesson_reviewed",
        ),
    )
    op.create_index("ix_lesson_review_created", "lesson",
                    ["review_state", sa.text("created_at DESC")])
    op.create_index("ix_lesson_recommendation", "lesson",
                    ["recommendation_id"])
    op.create_index("ix_lesson_thesis", "lesson", ["thesis_id"])
    op.create_index("ix_lesson_outcome_ref", "lesson", ["outcome_ref"])


def downgrade() -> None:
    for ix in ("ix_lesson_outcome_ref", "ix_lesson_thesis",
               "ix_lesson_recommendation", "ix_lesson_review_created"):
        op.drop_index(ix, table_name="lesson")
    op.drop_table("lesson")
