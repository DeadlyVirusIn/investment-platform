"""Outcome: persist signal_type family tag for stratification.

Revision ID: 007
Revises: 006
Create Date: 2026-04-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "recommendation_outcome",
        sa.Column("signal_type", sa.String(24), nullable=True),
    )
    op.create_index(
        "ix_recommendation_outcome_signal_type",
        "recommendation_outcome",
        ["signal_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recommendation_outcome_signal_type",
        table_name="recommendation_outcome",
    )
    op.drop_column("recommendation_outcome", "signal_type")
