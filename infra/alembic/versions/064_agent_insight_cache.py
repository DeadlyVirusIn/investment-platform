"""Phase F4 — agent insight cache (read-only research).

Stores safety-validated LLM insight markdown keyed by (kind,
payload_hash, model, safety_version). Hard isolation rules:

  * NO foreign keys to trading / paper / options / decision /
    replay tables.
  * NO cascade relationships.
  * Never referenced by execution paths.
  * Cache hits short-circuit the LLM call in
    /api/insights/{kind}; misses write a single row only after
    the response passes both pre- and post-call safety gates.
  * Banner is enforced verbatim by a CHECK constraint so a buggy
    writer cannot store a row with a missing or altered
    disclaimer.

Revision ID: 064_agent_insight_cache
Revises: 063_opt_strat_outcome
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "064_agent_insight_cache"
down_revision = "063_opt_strat_outcome"
branch_labels = None
depends_on = None


# Allow-list of agent kinds (mirrors AgentKind enum). Anything else
# is rejected at the DB tier.
_KINDS = (
    "trade_quality", "risk_commentary",
    "exit_review", "options_thesis",
)

# Canonical disclaimer string. Must match
# `agents.registry.BANNER` byte-for-byte.
_BANNER = "AI research insight — not execution logic."


def upgrade() -> None:
    op.create_table(
        "agent_insight",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("payload_hash", sa.Text, nullable=False),
        sa.Column("payload_redacted", JSONB, nullable=False),
        sa.Column("content_markdown", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("source_endpoint", sa.Text, nullable=False),
        sa.Column("banner", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column(
            "expires_at", sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "safety_version", sa.Text,
            nullable=False, server_default="v1",
        ),
        sa.UniqueConstraint(
            "kind", "payload_hash", "model", "safety_version",
            name="ux_agent_insight_natural_key",
        ),
        sa.CheckConstraint(
            "kind IN (" + ", ".join(f"'{k}'" for k in _KINDS) + ")",
            name="ck_agent_insight_kind",
        ),
        sa.CheckConstraint(
            f"banner = '{_BANNER}'",
            name="ck_agent_insight_banner",
        ),
        sa.CheckConstraint(
            "length(content_markdown) > 0",
            name="ck_agent_insight_content_nonempty",
        ),
    )
    op.create_index(
        "ix_agent_insight_lookup",
        "agent_insight",
        ["kind", "payload_hash", "model", "safety_version"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_insight_lookup", table_name="agent_insight",
    )
    op.drop_table("agent_insight")
