"""Phase B7.3 — strategy_candidate event-awareness columns.

Adds 4 nullable columns to `options_strategy_candidate` so the
generator can persist the earliest in-window macro event seen for
the underlying at emission time. Columns stay NULL when no event
falls in the DTE window — honest empty state.

Strictly additive.

Revision ID: 075_strategy_candidate_event_columns
Revises: 074_market_event_calendar
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "075_candidate_event_cols"
down_revision = "074_market_event_calendar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "options_strategy_candidate",
        sa.Column("earliest_event_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "options_strategy_candidate",
        sa.Column("earliest_event_type", sa.Text(), nullable=True),
    )
    op.add_column(
        "options_strategy_candidate",
        sa.Column("earliest_event_importance", sa.Text(), nullable=True),
    )
    op.add_column(
        "options_strategy_candidate",
        sa.Column("event_days_away", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_strategy_candidate_event_window",
        "options_strategy_candidate",
        ["earliest_event_date"],
        postgresql_where=sa.text("earliest_event_date IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_strategy_candidate_event_window",
        table_name="options_strategy_candidate",
    )
    op.drop_column("options_strategy_candidate", "event_days_away")
    op.drop_column("options_strategy_candidate", "earliest_event_importance")
    op.drop_column("options_strategy_candidate", "earliest_event_type")
    op.drop_column("options_strategy_candidate", "earliest_event_date")
