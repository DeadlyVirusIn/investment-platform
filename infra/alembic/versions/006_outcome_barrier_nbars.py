"""Outcome triple-barrier: store horizon length used per row.

Revision ID: 006
Revises: 005
Create Date: 2026-04-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "recommendation_outcome",
        sa.Column("barrier_n_bars", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recommendation_outcome", "barrier_n_bars")
