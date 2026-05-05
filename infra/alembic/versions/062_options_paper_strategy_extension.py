"""Phase Options-2 — extend options_paper_trade.strategy_name CHECK.

Migration 047 froze the strategy enum to:
    SHORT_PUT_CREDIT_SPREAD, SHORT_CALL_CREDIT_SPREAD, IRON_CONDOR.

Controlled options paper execution adds two simple directional
strategies to the allow-list:
    LONG_CALL, BULL_CALL_SPREAD.

Pure additive CHECK widening. No data migration. Existing rows (=0
in this DB) remain valid.

Revision ID: 062_options_paper_strategy_extension
Revises: 061_replay_manifest
"""

from __future__ import annotations

from alembic import op


revision = "062_opt_paper_strategy_ext"
down_revision = "061_replay_manifest"
branch_labels = None
depends_on = None


_OLD_STRATEGY_NAMES = (
    "SHORT_PUT_CREDIT_SPREAD",
    "SHORT_CALL_CREDIT_SPREAD",
    "IRON_CONDOR",
)
_NEW_STRATEGY_NAMES = _OLD_STRATEGY_NAMES + (
    "LONG_CALL",
    "BULL_CALL_SPREAD",
)


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.drop_constraint(
        "ck_options_paper_trade_strategy_name",
        "options_paper_trade", type_="check",
    )
    op.create_check_constraint(
        "ck_options_paper_trade_strategy_name",
        "options_paper_trade",
        _in("strategy_name", _NEW_STRATEGY_NAMES),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_options_paper_trade_strategy_name",
        "options_paper_trade", type_="check",
    )
    op.create_check_constraint(
        "ck_options_paper_trade_strategy_name",
        "options_paper_trade",
        _in("strategy_name", _OLD_STRATEGY_NAMES),
    )
