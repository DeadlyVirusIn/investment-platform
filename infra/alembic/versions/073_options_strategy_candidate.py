"""Phase B6.1 — options_strategy_candidate (semantic enrichment).

Additive layer that interprets `options_shadow_decision_log`
contract qualifications as 1-3 strategy candidates with full
explainability metadata. The shadow log remains the canonical
"did this contract pass the filter chain?" record; this table
adds the AI-strategist interpretation layer.

Discipline:
  * FK to shadow_decision_log (RESTRICT delete) — interpretation
    is meaningless without the source observation.
  * FK to options_strategy_bias (RESTRICT delete) — every rule_id
    must have a published taxonomy entry.
  * Idempotent on (shadow_observation_id, rule_id).
  * Read-only path from generation onward; no UPDATE flow in
    Phase B6. Re-running the generator is a no-op due to
    ON CONFLICT.

Explainability columns (locked by Phase B6 review):
  why_emitted          — single-sentence justification for emission
  triggering_rule      — name of the deterministic generator rule
                         that fired (e.g. "call_long_low_iv")
  rejected_alternatives — jsonb array of strategies considered then
                         deprioritized + the reason each was passed
                         over (compact form: [{rule_id, reason}])
  strategy_fit_reason  — why this strategy suits the underlying view
  iv_fit_reason        — why current IV environment supports it
  dte_fit_reason       — why current DTE aligns with the strategy
  liquidity_fit_reason — why current chain liquidity supports it

Strictly additive.

Revision ID: 073_options_strategy_candidate
Revises: 072_options_strategy_bias
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "073_options_strategy_candidate"
down_revision = "072_options_strategy_bias"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "options_strategy_candidate",
        sa.Column(
            "id", sa.BigInteger(),
            sa.Identity(always=False), primary_key=True,
        ),
        sa.Column(
            "shadow_observation_id", sa.BigInteger(),
            sa.ForeignKey(
                "options_shadow_decision_log.id",
                name="fk_strategy_candidate_shadow",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("run_date",   sa.Date(), nullable=False),
        sa.Column("underlying", sa.Text(), nullable=False),
        sa.Column(
            "rule_id", sa.Text(),
            sa.ForeignKey(
                "options_strategy_bias.rule_id",
                name="fk_strategy_candidate_bias",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        # Denormalized for query efficiency. The authoritative values
        # live in options_strategy_bias; these mirror them at emission
        # time so analytic queries don't always need a join.
        sa.Column("bias",             sa.Text(), nullable=False),
        sa.Column("directional_view", sa.Text(), nullable=False),
        sa.Column("risk_profile",     sa.Text(), nullable=False),
        # Suitability components — each 0..1.
        sa.Column("confidence",           sa.Numeric(8, 4), nullable=False),
        sa.Column("iv_suitability",       sa.Numeric(8, 4), nullable=False),
        sa.Column("expiry_suitability",   sa.Numeric(8, 4), nullable=False),
        sa.Column("liquidity_suitability", sa.Numeric(8, 4), nullable=False),
        sa.Column("composite_score",      sa.Numeric(8, 4), nullable=False),
        # Explainability — every emission must persist its reasoning.
        sa.Column("why_emitted",       sa.Text(), nullable=False),
        sa.Column("triggering_rule",   sa.Text(), nullable=False),
        sa.Column(
            "rejected_alternatives", sa.dialects.postgresql.JSONB(),
            nullable=False, server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("strategy_fit_reason",  sa.Text(), nullable=True),
        sa.Column("iv_fit_reason",        sa.Text(), nullable=True),
        sa.Column("dte_fit_reason",       sa.Text(), nullable=True),
        sa.Column("liquidity_fit_reason", sa.Text(), nullable=True),
        sa.Column(
            "diagnostics", sa.dialects.postgresql.JSONB(),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "shadow_observation_id", "rule_id",
            name="ux_strategy_candidate_observation_rule",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1 "
            "AND iv_suitability >= 0 AND iv_suitability <= 1 "
            "AND expiry_suitability >= 0 AND expiry_suitability <= 1 "
            "AND liquidity_suitability >= 0 AND liquidity_suitability <= 1 "
            "AND composite_score >= 0 AND composite_score <= 1",
            name="ck_strategy_candidate_unit_scores",
        ),
    )
    op.create_index(
        "ix_strategy_candidate_run_date",
        "options_strategy_candidate",
        [sa.text("run_date DESC"), "underlying"],
    )
    op.create_index(
        "ix_strategy_candidate_bias_rank",
        "options_strategy_candidate",
        ["bias", sa.text("composite_score DESC")],
    )
    op.create_index(
        "ix_strategy_candidate_rule_id",
        "options_strategy_candidate",
        ["rule_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_strategy_candidate_rule_id",
        table_name="options_strategy_candidate",
    )
    op.drop_index(
        "ix_strategy_candidate_bias_rank",
        table_name="options_strategy_candidate",
    )
    op.drop_index(
        "ix_strategy_candidate_run_date",
        table_name="options_strategy_candidate",
    )
    op.drop_table("options_strategy_candidate")
