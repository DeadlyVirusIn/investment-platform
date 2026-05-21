"""Phase Opt-C2 Pre-Canary 0 — canary scaffolding.

Adds three new tables + scheduler rows + initial canary portfolio
seed. Strictly additive; no existing schema mutated.

New tables
----------
* options_paper_portfolio   — capital container (cash, max_open, cap)
* options_paper_position    — capital reservation per OPEN trade
                              (released on terminal transition)
* options_execution_funnel  — daily counts: candidates / promoted /
                              skip-reason rollup, mirrors stock-funnel
                              proposal pattern

Seed rows
---------
* options_paper_portfolio   — single canary-spy-v1 row, active=false
* job_schedule              — three new cron rows
                              (compute_options_features,
                               run_options_canary_promotion,
                               run_options_lifecycle_check)
                              all enabled=true; jobs themselves are
                              gated by OPTIONS_CANARY_ENABLED env flag
                              so disabled flag is the wrong knob

Reversibility
-------------
downgrade() drops the three tables, removes the cron rows, removes
the canary portfolio seed. No data loss because no execution has
occurred against these structures yet.

Revision ID: 069_options_canary_pre0
Revises: 068_options_analytics_indexes
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "069_options_canary_pre0"
down_revision = "068_options_analytics_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------
    # options_paper_portfolio
    # -----------------------------------------------------------------
    op.create_table(
        "options_paper_portfolio",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("cash_initial", sa.Numeric(20, 4), nullable=False),
        sa.Column("cash_current", sa.Numeric(20, 4), nullable=False),
        sa.Column(
            "max_open_trades", sa.Integer(), nullable=False,
            server_default="1",
        ),
        sa.Column(
            "max_capital_per_trade", sa.Numeric(20, 4), nullable=False,
        ),
        sa.Column(
            "active", sa.Boolean(), nullable=False, server_default=sa.false(),
        ),
        sa.Column("universe", sa.Text(), nullable=False),
        sa.Column("strategy_family", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "cash_initial >= 0 AND cash_current >= 0",
            name="ck_opt_portfolio_cash_nonneg",
        ),
        sa.CheckConstraint(
            "max_open_trades >= 1 AND max_capital_per_trade > 0",
            name="ck_opt_portfolio_caps_pos",
        ),
    )

    # -----------------------------------------------------------------
    # options_paper_position
    # -----------------------------------------------------------------
    op.create_table(
        "options_paper_position",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "portfolio_id", sa.String(36),
            sa.ForeignKey(
                "options_paper_portfolio.id",
                name="fk_opt_position_portfolio",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "trade_id", sa.Integer(),
            sa.ForeignKey(
                "options_paper_trade.id",
                name="fk_opt_position_trade",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("reserved_capital", sa.Numeric(20, 4), nullable=False),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "released_at", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column("release_reason", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "trade_id", name="ux_opt_position_trade",
        ),
        sa.CheckConstraint(
            "reserved_capital >= 0",
            name="ck_opt_position_capital_nonneg",
        ),
    )
    op.create_index(
        "ix_opt_position_portfolio_open",
        "options_paper_position",
        ["portfolio_id"],
        postgresql_where=sa.text("released_at IS NULL"),
    )

    # -----------------------------------------------------------------
    # options_execution_funnel
    # -----------------------------------------------------------------
    op.create_table(
        "options_execution_funnel",
        sa.Column(
            "id", sa.BigInteger(),
            sa.Identity(always=False), primary_key=True,
        ),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column(
            "portfolio_id", sa.String(36),
            sa.ForeignKey(
                "options_paper_portfolio.id",
                name="fk_opt_funnel_portfolio",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        # Top of funnel
        sa.Column(
            "candidates_total", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "candidates_after_universe", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "candidates_after_strategy", sa.Integer(), nullable=False,
            server_default="0",
        ),
        # Outcomes
        sa.Column(
            "promoted", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "filled", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "closed_today", sa.Integer(), nullable=False, server_default="0",
        ),
        # Skip-reason rollup
        sa.Column(
            "skip_canary_disabled", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "skip_slot_full", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "skip_over_capital_cap", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "skip_dte_outside_window", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "skip_no_chain_for_proposal", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "skip_proposal_duplicate", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column(
            "skip_other", sa.Integer(), nullable=False, server_default="0",
        ),
        # Saturation snapshot
        sa.Column("open_at_start", sa.Integer(), nullable=False),
        sa.Column("open_at_end", sa.Integer(), nullable=False),
        sa.Column("cash_at_start", sa.Numeric(20, 4), nullable=False),
        sa.Column("cash_at_end", sa.Numeric(20, 4), nullable=False),
        sa.Column("details_json", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "run_date", "portfolio_id",
            name="ux_opt_funnel_run_portfolio",
        ),
    )
    op.create_index(
        "ix_opt_funnel_run_date",
        "options_execution_funnel",
        [sa.text("run_date DESC")],
    )

    # -----------------------------------------------------------------
    # Seed: canary-spy-v1 portfolio (active=false until Phase 1B)
    # -----------------------------------------------------------------
    op.execute(
        sa.text(
            """
            INSERT INTO options_paper_portfolio
              (id, name, cash_initial, cash_current,
               max_open_trades, max_capital_per_trade,
               active, universe, strategy_family, notes)
            VALUES
              (gen_random_uuid()::text, 'canary-spy-v1',
               2000.00, 2000.00,
               1, 500.00,
               false, 'SPY', 'BULL_CALL_SPREAD',
               'Phase Opt-C2 canary portfolio. SPY only. '
               'BULL_CALL_SPREAD only. 1 OPEN at a time. '
               '$500 max risk per trade. active=false until '
               'Phase 1B opens fill path. See '
               'Phase Opt-C2 design proposal.')
            ON CONFLICT (name) DO NOTHING
            """
        )
    )

    # -----------------------------------------------------------------
    # Cron rows for the three new jobs.
    # All enabled=true at scheduler level; runtime gated by
    # OPTIONS_CANARY_ENABLED env flag (default false).
    # -----------------------------------------------------------------
    op.execute(
        sa.text(
            """
            INSERT INTO job_schedule
              (id, name, cron_expr, enabled, created_at, updated_at)
            VALUES
              (gen_random_uuid()::text, 'compute_options_features',
               '35 21 * * 1-5', true, NOW(), NOW()),
              (gen_random_uuid()::text, 'run_options_canary_promotion',
               '00 22 * * 1-5', true, NOW(), NOW()),
              (gen_random_uuid()::text, 'run_options_lifecycle_check',
               '30 13 * * 1-5', true, NOW(), NOW())
            ON CONFLICT (name) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM job_schedule
             WHERE name IN (
               'compute_options_features',
               'run_options_canary_promotion',
               'run_options_lifecycle_check'
             )
            """
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM options_paper_portfolio WHERE name='canary-spy-v1'"
        )
    )
    op.drop_index("ix_opt_funnel_run_date", table_name="options_execution_funnel")
    op.drop_table("options_execution_funnel")
    op.drop_index(
        "ix_opt_position_portfolio_open",
        table_name="options_paper_position",
    )
    op.drop_table("options_paper_position")
    op.drop_table("options_paper_portfolio")
