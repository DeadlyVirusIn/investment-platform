"""Phase P6B.0 — align canary-spy-v1 seed strategy to an engine strategy.

The 069 seed used strategy_family='BULL_CALL_SPREAD', but the paper engine's
DEFINED_RISK_STRATEGIES only accepts SHORT_PUT_CREDIT_SPREAD,
SHORT_CALL_CREDIT_SPREAD, IRON_CONDOR — BULL_CALL_SPREAD would fail
validate_defined_risk at promotion time. Re-point the single canary seed to
SHORT_PUT_CREDIT_SPREAD (bullish, engine-validated, generator-emitted).

Data-only UPDATE; no schema change. The portfolio stays active=false (no
activation here). Idempotent + reversible.

Revision ID: 092_canary_strategy_align
Revises: 091_options_candidate_leg
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "092_canary_strategy_align"
down_revision = "091_options_candidate_leg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE options_paper_portfolio "
            "SET strategy_family = 'SHORT_PUT_CREDIT_SPREAD', updated_at = NOW() "
            "WHERE name = 'canary-spy-v1' "
            "  AND strategy_family = 'BULL_CALL_SPREAD'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE options_paper_portfolio "
            "SET strategy_family = 'BULL_CALL_SPREAD', updated_at = NOW() "
            "WHERE name = 'canary-spy-v1' "
            "  AND strategy_family = 'SHORT_PUT_CREDIT_SPREAD'"
        )
    )
