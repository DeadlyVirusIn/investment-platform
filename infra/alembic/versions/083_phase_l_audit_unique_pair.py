"""Phase L M083 — reasoning_audit unique constraint over (envelope_hash, paper_trade_id).

The original constraint on envelope_hash alone is too strict: the same
envelope can legitimately be associated with multiple paper_trades
(e.g. identical thesis applied across the AI's portfolio at the same
moment). Additionally, an envelope can be recorded once standalone
(paper_trade_id=NULL) and later re-recorded attached to a real trade.

Postgres treats NULLs as distinct in unique constraints by default,
so (hash, NULL) and (hash, trade_x) and (hash, trade_y) all coexist.
The ON CONFLICT DO NOTHING semantics in record_envelope still prevent
double-writing the same (envelope, trade) pair.

Revision ID: 083_phase_l_audit_unique_pair
Revises: 082_phase_l_audit_trade_id_uuid
"""

from __future__ import annotations

from alembic import op


revision = "083_phase_l_audit_unique_pair"
down_revision = "082_phase_l_audit_trade_id_uuid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_reasoning_audit_envelope_hash",
        "reasoning_audit",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_reasoning_audit_envelope_hash_trade",
        "reasoning_audit",
        ["envelope_hash", "paper_trade_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_reasoning_audit_envelope_hash_trade",
        "reasoning_audit",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_reasoning_audit_envelope_hash",
        "reasoning_audit",
        ["envelope_hash"],
    )
