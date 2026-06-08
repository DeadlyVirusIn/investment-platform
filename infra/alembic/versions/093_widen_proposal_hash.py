"""Phase P6D.19 — widen options_paper_trade.proposal_hash to 64 chars.

The canary proposal_hash (`options.canary.positions.proposal_hash`) is a
SHA-256 hex digest = 64 characters, but the column was created varchar(32)
in Opt-B1 (067), which used a shorter hash. The first real canary promotion
failed at insert: `value too long for type character varying(32)`.

Widen to varchar(64). A varchar length INCREASE is a catalog-only change in
PostgreSQL (no table rewrite), and the partial UNIQUE index
`uq_options_paper_trade_proposal_hash` is preserved automatically. No data
loss — existing values are <= 32 chars and fit.

Revision ID: 093_widen_proposal_hash
Revises: 092_canary_strategy_align
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "093_widen_proposal_hash"
down_revision = "092_canary_strategy_align"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "options_paper_trade",
        "proposal_hash",
        type_=sa.String(64),
        existing_type=sa.String(32),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Narrowing can truncate; safe only if no value exceeds 32 chars.
    op.alter_column(
        "options_paper_trade",
        "proposal_hash",
        type_=sa.String(32),
        existing_type=sa.String(64),
        existing_nullable=True,
    )
