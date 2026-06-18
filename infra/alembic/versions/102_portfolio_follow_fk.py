"""Sprint E — referential integrity on portfolio_follow.paper_portfolio_id.

Adds the missing FK to paper_portfolio (ON DELETE CASCADE). Cleans any
orphaned follow rows first so the constraint can be created.

Revision ID: 102_portfolio_follow_fk
Revises: 101_model_portfolios
"""

from __future__ import annotations

from alembic import op

revision = "102_portfolio_follow_fk"
down_revision = "101_model_portfolios"
branch_labels = None
depends_on = None

FK = "fk_portfolio_follow_paper_portfolio"


def upgrade() -> None:
    op.execute(
        "DELETE FROM portfolio_follow f WHERE NOT EXISTS "
        "(SELECT 1 FROM paper_portfolio p WHERE p.id = f.paper_portfolio_id)"
    )
    op.create_foreign_key(
        FK, "portfolio_follow", "paper_portfolio",
        ["paper_portfolio_id"], ["id"], ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(FK, "portfolio_follow", type_="foreignkey")
