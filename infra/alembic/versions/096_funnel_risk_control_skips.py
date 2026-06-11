"""P6D.36D — funnel counters for enforced portfolio risk controls.

promote_one now rejects with explicit statuses (underlying_cap /
daily_cap / cash_floor / aggregate_loss_cap). Same additive-column
pattern as 095 so the funnel RECORDS these rejections.

upgrade:
  Add four nullable integer counters (server_default '0') to
  options_execution_funnel:
    * skip_underlying_cap    — OPTIONS_CANARY_MAX_PER_UNDERLYING
    * skip_daily_cap         — OPTIONS_CANARY_MAX_PROMOTIONS_PER_DAY
    * skip_cash_floor        — OPTIONS_CANARY_MIN_CASH_FLOOR_DOLLARS
    * skip_aggregate_loss_cap — OPTIONS_CANARY_MAX_AGGREGATE_LOSS_DOLLARS

downgrade:
  Drop the four columns (pair with a code rollback — standard
  additive-column contract).

Revision ID: 096_funnel_risk_control_skips
Revises: 095_funnel_skip_reason_split
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "096_funnel_risk_control_skips"
down_revision = "095_funnel_skip_reason_split"
branch_labels = None
depends_on = None

_COLUMNS = (
    "skip_underlying_cap",
    "skip_daily_cap",
    "skip_cash_floor",
    "skip_aggregate_loss_cap",
)


def upgrade() -> None:
    for col in _COLUMNS:
        op.add_column(
            "options_execution_funnel",
            sa.Column(col, sa.Integer(), nullable=True, server_default="0"),
        )


def downgrade() -> None:
    for col in reversed(_COLUMNS):
        op.drop_column("options_execution_funnel", col)
