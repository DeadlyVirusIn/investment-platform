"""Paper-cost audit stamp — paper_trade.execution_cost_json (Priority 3 hardening).

One additive nullable JSONB column. Stamped by ``submit_trade`` ONLY when the
honest cost model fired (PAPER_COST_MODEL_ENABLED, default OFF): the full
durable breakdown — raw + effective fill price, gross_notional, commission,
slippage_cost, total_cost, net_notional (all exact Decimal strings) — plus
the cost-model version and configuration that produced them. Without it a
cost-enabled fill cannot be unambiguously reconstructed: the stored
fill_price is the quantized EFFECTIVE price, so backing the raw price out of
slippage_bps is lossy, and the model config is invisible across churn.

NULL for every legacy row, every zero-cost fill, and every caller that bakes
its own costs (fill_price_override — weekly rebalance). No backfill.

PROPOSED — validated on an ephemeral container only; dev/prod application is
a separate approval-gated step. Additive only; downgrade drops the column.

Revision ID: 115_paper_trade_cost_stamp
Revises: 114_agent_gateway
Create Date: 2026-07-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "115_paper_trade_cost_stamp"
down_revision = "114_agent_gateway"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "paper_trade",
        sa.Column("execution_cost_json", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("paper_trade", "execution_cost_json")
