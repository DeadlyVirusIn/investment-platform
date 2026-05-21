"""Phase L M081 — reasoning audit log.

Persists every rendered ReasoningEnvelope for governance and
reproducibility. Anchored on envelope_hash (deterministic SHA-256 of
the canonical envelope payload).

Constraints:
  * envelope_hash is unique — identical envelopes collapse to one row.
  * skeleton_id is the canonical_name from the vocabulary_entry table
    (vocabulary_type='skeleton'), stored as text — no FK so the audit
    survives skeleton retirement.
  * paper_trade_id is optional FK — research/replay envelopes may not
    map to a trade row.
  * Append-only at the API layer; no UPDATE path.

Revision ID: 081_phase_l_reasoning_audit
Revises: 080_phase_l_vocabulary
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "081_phase_l_reasoning_audit"
down_revision = "080_phase_l_vocabulary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reasoning_audit",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("envelope_hash", sa.String(64), nullable=False),
        sa.Column("skeleton_id", sa.Text, nullable=False),
        sa.Column("slot_fills_json", sa.JSON, nullable=False),
        sa.Column("invalidation_json", sa.JSON, nullable=False),
        sa.Column("thesis_json", sa.JSON, nullable=False),
        sa.Column("uncertainty_markers", sa.JSON, nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column(
            "envelope_generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "rendered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("paper_trade_id", sa.BigInteger, nullable=True),
        sa.UniqueConstraint("envelope_hash", name="uq_reasoning_audit_envelope_hash"),
    )
    op.create_index(
        "ix_reasoning_audit_paper_trade_id",
        "reasoning_audit",
        ["paper_trade_id"],
    )
    op.create_index(
        "ix_reasoning_audit_skeleton_id",
        "reasoning_audit",
        ["skeleton_id"],
    )
    op.create_index(
        "ix_reasoning_audit_rendered_at",
        "reasoning_audit",
        ["rendered_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reasoning_audit_rendered_at", table_name="reasoning_audit",
    )
    op.drop_index(
        "ix_reasoning_audit_skeleton_id", table_name="reasoning_audit",
    )
    op.drop_index(
        "ix_reasoning_audit_paper_trade_id", table_name="reasoning_audit",
    )
    op.drop_table("reasoning_audit")
