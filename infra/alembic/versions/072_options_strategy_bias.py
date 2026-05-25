"""Phase B1 — Options strategy bias taxonomy.

Creates `options_strategy_bias` keyed on `rule_id`. Maps each
strategy family the platform supports to:
  * directional bias (bullish/bearish/neutral/event/developing)
  * risk profile (defined/undefined)
  * regime-fit hints (jsonb)
  * a one-line directional view

Used by the Phase B `/api/options/opportunities` endpoint to
classify shadow signals into Bull/Bear/Neutral/Event/Developing/
Conviction lanes. Read-only — nothing else writes here. Operators
update bias via a separate `/api/options/strategy-bias` route
(out of Phase B scope).

Seeded with the common single-leg + spread + Iron Condor family
plus the engine's existing `STRATEGY_*` constants. New strategies
without a row default to `developing` at the endpoint level.

Strictly additive.

Revision ID: 072_options_strategy_bias
Revises: 071_paper_exit_cycle_schedule
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "072_options_strategy_bias"
down_revision = "071_paper_exit_cycle_schedule"
branch_labels = None
depends_on = None


# Locked taxonomy. The application layer asserts every row's `bias`
# value is one of these; new ones require a migration.
BIAS_VALUES: tuple[str, ...] = (
    "bullish", "bearish", "neutral", "event", "developing",
)


SEED_ROWS: list[dict[str, object]] = [
    # ---- single-leg longs ----
    {
        "rule_id":          "LONG_CALL",
        "bias":             "bullish",
        "directional_view": "Profits when underlying rises past breakeven.",
        "risk_profile":     "defined",
        "regime_fit": {
            "iv_low":  "favored",
            "iv_high": "avoid",       # premium paid is rich
            "trending": "favored",
            "ranging": "avoid",
        },
        "notes": "Sensitive to IV crush; pair with directional conviction.",
    },
    {
        "rule_id":          "LONG_PUT",
        "bias":             "bearish",
        "directional_view": "Profits when underlying falls past breakeven.",
        "risk_profile":     "defined",
        "regime_fit": {
            "iv_low":  "favored",
            "iv_high": "avoid",
            "trending": "favored",
            "ranging": "avoid",
        },
        "notes": "Useful as a defined-risk hedge in calm vol regimes.",
    },
    # ---- defined-risk debit spreads ----
    {
        "rule_id":          "BULL_CALL_SPREAD",
        "bias":             "bullish",
        "directional_view": "Modest upside; defined max loss.",
        "risk_profile":     "defined",
        "regime_fit": {
            "iv_low":  "favored",
            "iv_high": "neutral",
            "trending": "favored",
            "ranging": "neutral",
        },
        "notes": "Long-debit; less IV-sensitive than naked long call.",
    },
    {
        "rule_id":          "BEAR_PUT_SPREAD",
        "bias":             "bearish",
        "directional_view": "Modest downside; defined max loss.",
        "risk_profile":     "defined",
        "regime_fit": {
            "iv_low":  "favored",
            "iv_high": "neutral",
            "trending": "favored",
            "ranging": "neutral",
        },
        "notes": "Mirror of BULL_CALL_SPREAD for downside views.",
    },
    # ---- credit spreads ----
    {
        "rule_id":          "BULL_PUT_SPREAD",
        "bias":             "bullish",
        "directional_view": "Income with bullish bias; sells OTM put spread.",
        "risk_profile":     "defined",
        "regime_fit": {
            "iv_low":  "avoid",
            "iv_high": "favored",
            "trending": "favored",
            "ranging": "neutral",
        },
        "notes": "Credit collected; max loss is spread width − credit.",
    },
    {
        "rule_id":          "SHORT_PUT_CREDIT_SPREAD",
        "bias":             "bullish",
        "directional_view": "Same payoff as BULL_PUT_SPREAD; engine alias.",
        "risk_profile":     "defined",
        "regime_fit": {
            "iv_low":  "avoid",
            "iv_high": "favored",
            "trending": "favored",
            "ranging": "neutral",
        },
        "notes": "Canonical engine name for credit put spread.",
    },
    {
        "rule_id":          "BEAR_CALL_SPREAD",
        "bias":             "bearish",
        "directional_view": "Income with bearish bias; sells OTM call spread.",
        "risk_profile":     "defined",
        "regime_fit": {
            "iv_low":  "avoid",
            "iv_high": "favored",
            "trending": "favored",
            "ranging": "neutral",
        },
        "notes": "Defined-risk mirror of BULL_PUT_SPREAD.",
    },
    {
        "rule_id":          "SHORT_CALL_CREDIT_SPREAD",
        "bias":             "bearish",
        "directional_view": "Same payoff as BEAR_CALL_SPREAD; engine alias.",
        "risk_profile":     "defined",
        "regime_fit": {
            "iv_low":  "avoid",
            "iv_high": "favored",
            "trending": "favored",
            "ranging": "neutral",
        },
        "notes": "Canonical engine name for credit call spread.",
    },
    # ---- defined-risk neutral / income ----
    {
        "rule_id":          "IRON_CONDOR",
        "bias":             "neutral",
        "directional_view": "Profits if underlying stays in a range.",
        "risk_profile":     "defined",
        "regime_fit": {
            "iv_low":  "avoid",
            "iv_high": "favored",
            "trending": "avoid",
            "ranging": "favored",
        },
        "notes": "Two credit spreads; benefits from IV contraction.",
    },
    {
        "rule_id":          "IRON_BUTTERFLY",
        "bias":             "neutral",
        "directional_view": "Tight range profit; max gain at center strike.",
        "risk_profile":     "defined",
        "regime_fit": {
            "iv_low":  "avoid",
            "iv_high": "favored",
            "trending": "avoid",
            "ranging": "favored",
        },
        "notes": "Higher credit than condor; narrower break-even band.",
    },
    {
        "rule_id":          "CALENDAR_SPREAD",
        "bias":             "neutral",
        "directional_view": "Profits from front-leg decay > back-leg decay.",
        "risk_profile":     "defined",
        "regime_fit": {
            "iv_low":  "favored",
            "iv_high": "neutral",
            "trending": "neutral",
            "ranging": "favored",
        },
        "notes": "IV expansion at the back month is the main risk.",
    },
    {
        "rule_id":          "DIAGONAL_SPREAD",
        "bias":             "bullish",
        "directional_view": "Long back-month + short front-month, "
                            "moderately bullish.",
        "risk_profile":     "defined",
        "regime_fit": {
            "iv_low":  "favored",
            "iv_high": "neutral",
            "trending": "favored",
            "ranging": "neutral",
        },
        "notes": "Defaults bullish; bearish mirror also exists.",
    },
    # ---- event / volatility plays ----
    {
        "rule_id":          "LONG_STRADDLE",
        "bias":             "event",
        "directional_view": "Profits on a large move in either direction.",
        "risk_profile":     "defined",
        "regime_fit": {
            "iv_low":  "favored",
            "iv_high": "avoid",
            "trending": "neutral",
            "ranging": "avoid",
        },
        "notes": "Earnings / catalyst plays; max loss = combined premium.",
    },
    {
        "rule_id":          "LONG_STRANGLE",
        "bias":             "event",
        "directional_view": "Wider-band straddle; cheaper, larger needed move.",
        "risk_profile":     "defined",
        "regime_fit": {
            "iv_low":  "favored",
            "iv_high": "avoid",
            "trending": "neutral",
            "ranging": "avoid",
        },
        "notes": "Lower cost than straddle; needs bigger move.",
    },
    # ---- undefined-risk neutral (operator-only) ----
    {
        "rule_id":          "SHORT_STRADDLE",
        "bias":             "neutral",
        "directional_view": "Sells ATM straddle; undefined risk.",
        "risk_profile":     "undefined",
        "regime_fit": {
            "iv_low":  "avoid",
            "iv_high": "favored",
            "trending": "avoid",
            "ranging": "favored",
        },
        "notes": "Undefined risk — disabled in paper canary by policy.",
    },
    {
        "rule_id":          "SHORT_STRANGLE",
        "bias":             "neutral",
        "directional_view": "Sells OTM call + put; undefined risk.",
        "risk_profile":     "undefined",
        "regime_fit": {
            "iv_low":  "avoid",
            "iv_high": "favored",
            "trending": "avoid",
            "ranging": "favored",
        },
        "notes": "Undefined risk — disabled in paper canary by policy.",
    },
    # ---- stock-pairing strategies ----
    {
        "rule_id":          "COVERED_CALL",
        "bias":             "neutral",
        "directional_view": "Long stock + short OTM call; income strategy.",
        "risk_profile":     "undefined",
        "regime_fit": {
            "iv_low":  "neutral",
            "iv_high": "favored",
            "trending": "neutral",
            "ranging": "favored",
        },
        "notes": "Stock risk dominates; option leg is the income source.",
    },
    {
        "rule_id":          "CASH_SECURED_PUT",
        "bias":             "bullish",
        "directional_view": "Sells OTM put; assignment becomes long stock.",
        "risk_profile":     "undefined",
        "regime_fit": {
            "iv_low":  "neutral",
            "iv_high": "favored",
            "trending": "favored",
            "ranging": "favored",
        },
        "notes": "Cash collateral required; assignment risk on dip.",
    },
    # ---- engine-internal placeholder used by shadow_evaluator ----
    {
        "rule_id":          "options_shadow_v1",
        "bias":             "developing",
        "directional_view": "Engine-internal multi-strategy shadow evaluator.",
        "risk_profile":     "defined",
        "regime_fit": {},
        "notes": "Internal name used in options_shadow_decision_log; "
                 "mapped to 'developing' so it surfaces in the Developing "
                 "lane until per-rule signals are split out.",
    },
]


def upgrade() -> None:
    op.create_table(
        "options_strategy_bias",
        sa.Column("rule_id", sa.Text(), primary_key=True),
        sa.Column("bias", sa.Text(), nullable=False),
        sa.Column("directional_view", sa.Text(), nullable=False),
        sa.Column("risk_profile", sa.Text(), nullable=False),
        sa.Column(
            "regime_fit", sa.dialects.postgresql.JSONB(),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
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
            "bias IN ('bullish','bearish','neutral','event','developing')",
            name="ck_options_strategy_bias_value",
        ),
        sa.CheckConstraint(
            "risk_profile IN ('defined','undefined')",
            name="ck_options_strategy_bias_risk",
        ),
    )
    op.create_index(
        "ix_options_strategy_bias_bias",
        "options_strategy_bias", ["bias"],
    )

    # Seed using JSONB-safe parameter binding.
    import json
    for row in SEED_ROWS:
        op.execute(
            sa.text(
                """
                INSERT INTO options_strategy_bias
                  (rule_id, bias, directional_view, risk_profile,
                   regime_fit, notes)
                VALUES
                  (:rule_id, :bias, :directional_view, :risk_profile,
                   CAST(:regime_fit AS jsonb), :notes)
                ON CONFLICT (rule_id) DO NOTHING
                """
            ).bindparams(
                rule_id=row["rule_id"],
                bias=row["bias"],
                directional_view=row["directional_view"],
                risk_profile=row["risk_profile"],
                regime_fit=json.dumps(row["regime_fit"]),
                notes=row["notes"],
            )
        )


def downgrade() -> None:
    op.drop_index(
        "ix_options_strategy_bias_bias",
        table_name="options_strategy_bias",
    )
    op.drop_table("options_strategy_bias")
