"""Phase L M082 — correct reasoning_audit.paper_trade_id type.

M081 declared paper_trade_id as BIGINT, but paper_trade.id is a UUID
(stored as varchar in this codebase). M082 corrects the column type
to TEXT so audit rows can reference real trades.

Safe: M081 just shipped, no real paper_trade_id values written yet
(only NULLs from D3.6 self-test). USING NULL is sufficient.

Revision ID: 082_phase_l_audit_trade_id_uuid
Revises: 081_phase_l_reasoning_audit
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "082_phase_l_audit_trade_id_uuid"
down_revision = "081_phase_l_reasoning_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "reasoning_audit",
        "paper_trade_id",
        existing_type=sa.BigInteger(),
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="paper_trade_id::text",
    )


def downgrade() -> None:
    op.alter_column(
        "reasoning_audit",
        "paper_trade_id",
        existing_type=sa.Text(),
        type_=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using="NULLIF(paper_trade_id, '')::bigint",
    )
