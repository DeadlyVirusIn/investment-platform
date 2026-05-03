"""Stock engine Batch 5: paper_trade cost columns (slippage_bps, commission).

Revision ID: 012
Revises: 011
Create Date: 2026-04-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "paper_trade",
        sa.Column("slippage_bps", sa.Numeric(10, 4), nullable=True),
    )
    op.add_column(
        "paper_trade",
        sa.Column(
            "commission",
            sa.Numeric(20, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("paper_trade", "commission")
    op.drop_column("paper_trade", "slippage_bps")
