"""Phase Options-Quality — append-only options strategy outcome table.

Records forward-return scoring per (underlying, strategy_name,
submitted_at_utc, horizon). Pure read of options_chain_snapshot;
this migration only creates the storage. No data migration. No
existing-row impact.

Revision ID: 063_opt_strat_outcome
Revises: 062_opt_paper_strategy_ext
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "063_opt_strat_outcome"
down_revision = "062_opt_paper_strategy_ext"
branch_labels = None
depends_on = None


_HORIZONS = ("1D", "3D", "5D", "10D", "20D")
_OUTCOME_LABELS = (
    "good", "neutral", "bad", "pending", "data_blocked",
)
_SOURCES = ("suggestion", "paper_trade")
_MODES = ("strict", "exploratory", "options_exploratory")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.create_table(
        "options_strategy_outcome",
        sa.Column(
            "id", sa.BigInteger,
            sa.Identity(always=False, start=1),
            primary_key=True,
        ),
        sa.Column("underlying", sa.Text, nullable=False),
        sa.Column("strategy_name", sa.Text, nullable=False),
        sa.Column("legs_json", JSONB, nullable=False),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column(
            "submitted_at_utc",
            sa.DateTime(timezone=True), nullable=False,
        ),
        sa.Column("horizon", sa.Text, nullable=False),
        sa.Column("entry_reference", sa.Numeric(14, 6)),
        sa.Column("exit_reference", sa.Numeric(14, 6)),
        sa.Column("forward_return_pct", sa.Numeric(14, 6)),
        sa.Column("mfe_pct", sa.Numeric(14, 6)),
        sa.Column("mae_pct", sa.Numeric(14, 6)),
        sa.Column("outcome_label", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("mode", sa.Text, nullable=False),
        sa.Column(
            "computed_at_utc",
            sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "underlying", "strategy_name", "submitted_at_utc",
            "horizon", "source",
            name="ux_options_strategy_outcome_natural_key",
        ),
        sa.CheckConstraint(
            _in("horizon", _HORIZONS),
            name="ck_options_strategy_outcome_horizon",
        ),
        sa.CheckConstraint(
            _in("outcome_label", _OUTCOME_LABELS),
            name="ck_options_strategy_outcome_label",
        ),
        sa.CheckConstraint(
            _in("source", _SOURCES),
            name="ck_options_strategy_outcome_source",
        ),
        sa.CheckConstraint(
            _in("mode", _MODES),
            name="ck_options_strategy_outcome_mode",
        ),
    )
    op.create_index(
        "ix_options_strategy_outcome_lookup",
        "options_strategy_outcome",
        ["as_of_date", "horizon", "mode"],
    )
    op.create_index(
        "ix_options_strategy_outcome_underlying",
        "options_strategy_outcome", ["underlying"],
    )


def downgrade() -> None:
    op.drop_index("ix_options_strategy_outcome_underlying",
                   table_name="options_strategy_outcome")
    op.drop_index("ix_options_strategy_outcome_lookup",
                   table_name="options_strategy_outcome")
    op.drop_table("options_strategy_outcome")
