"""Phase F.2 — Strategy Playbook table (educational depth).

Canonical 1:1 playbook per rule_id. Holds:
  * executive_summary
  * when_to_use / when_not_to_use (jsonb arrays of conditions)
  * market_environment_fit (jsonb: trending/ranging/volatile/calm)
  * iv_regime_fit (jsonb: deeper than bias.regime_fit)
  * theta_behavior, vega_behavior, delta_behavior (text)
  * typical_dte_range (jsonb)
  * lifecycle_expectations (jsonb)
  * risk_summary (text — defined/undefined detail)
  * educational_overlay_basic (beginner)
  * educational_overlay_advanced (advanced)
  * related_concepts (text[])

Strictly additive. Seeded for every rule_id in
options_strategy_bias. No LLM at runtime — every line is here.

Revision ID: 076_strategy_playbook
Revises: 075_candidate_event_cols
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "076_strategy_playbook"
down_revision = "075_candidate_event_cols"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Seed playbooks
# ---------------------------------------------------------------------------

PLAYBOOKS: list[dict] = [
    # ---- LONG_CALL ----
    {
        "rule_id": "LONG_CALL",
        "executive_summary":
            "Pay premium upfront to gain leveraged upside exposure in a "
            "specific underlying. Profits scale linearly above the strike "
            "plus premium; max loss is the premium paid.",
        "when_to_use": [
            {"condition": "Directional view is clearly bullish",
             "explanation": "Long calls demand price moves up; sideways action loses to theta."},
            {"condition": "IV rank is below ~50",
             "explanation": "Cheap premium environment lets you pay less for the same delta exposure."},
            {"condition": "DTE 20-50 days",
             "explanation": "Shorter DTE faces accelerating theta; longer DTE pays high time-value premium."},
        ],
        "when_not_to_use": [
            {"condition": "IV rank above 75",
             "explanation": "Premium is rich; consider credit spreads instead to collect premium."},
            {"condition": "Sideways or ranging market",
             "explanation": "Theta decay punishes a long-call without realized move."},
            {"condition": "Catalyst already priced into IV",
             "explanation": "Post-event IV crush typically destroys long premium."},
        ],
        "market_environment_fit": {
            "trending_up": "favored", "trending_down": "avoid",
            "ranging": "avoid", "volatile": "neutral", "calm_low_vol": "favored",
        },
        "iv_regime_fit": {
            "iv_low":  {"fit": "favored",
                        "reason": "Cheap premium maximizes long-vega + long-delta payoff."},
            "iv_high": {"fit": "avoid",
                        "reason": "Premium is expensive; IV crush risk dominates payoff."},
        },
        "theta_behavior":
            "LONG theta-negative. Position loses value daily as expiry "
            "approaches, all else equal. Decay accelerates inside ~30 DTE.",
        "vega_behavior":
            "LONG vega. Position GAINS when implied volatility expands and "
            "LOSES when IV compresses (post-event IV crush).",
        "delta_behavior":
            "Positive delta. ATM ≈ +0.50, ITM approaches +1.00, OTM "
            "approaches 0. Gamma is highest near ATM as expiry nears.",
        "typical_dte_range": {
            "min": 20, "max": 50, "ideal": 35,
            "reason": "Balances theta carry against capital efficiency.",
        },
        "lifecycle_expectations": {
            "entry": "Choose ITM-to-ATM strike for directional plays; OTM only "
                     "for high-conviction, large-move setups.",
            "management": "Watch for IV expansion gains; rule of thumb: "
                          "exit at 50-100% of premium captured.",
            "exit": "Take profit ≥50% gain. Stop loss ≥50% premium loss. "
                    "Avoid holding into expiry week (gamma + IV crush risk).",
            "typical_hold_days": 14,
        },
        "risk_summary":
            "Defined risk — max loss is the premium paid. No capital "
            "calls, no margin. Best-case 'time' is measured in weeks.",
        "educational_overlay_basic":
            "Buy a call when you expect price to go up soon. You pay a "
            "premium upfront and profit if price rises past your strike. "
            "You can never lose more than what you paid.",
        "educational_overlay_advanced":
            "Long call is long delta, long vega, short theta, long gamma. "
            "Strategy P&L is dominated by realized move vs implied; "
            "edge typically comes from being right on direction faster "
            "than implied move suggested. Avoid post-catalyst IV crush.",
        "related_concepts": [
            "delta", "theta_decay", "iv_crush",
            "intrinsic_vs_extrinsic", "gamma_risk",
        ],
    },
    # ---- LONG_PUT ----
    {
        "rule_id": "LONG_PUT",
        "executive_summary":
            "Mirror of LONG_CALL for downside. Pay premium to gain "
            "leveraged downside; max loss is premium paid.",
        "when_to_use": [
            {"condition": "Directional view is clearly bearish",
             "explanation": "Long puts demand price moves down within DTE."},
            {"condition": "IV rank below ~50",
             "explanation": "Cheap premium lets you express downside without overpaying."},
            {"condition": "Hedging an existing long stock exposure",
             "explanation": "Defined-risk protection without selling the underlying."},
        ],
        "when_not_to_use": [
            {"condition": "IV rank above 75 with no catalyst nearby",
             "explanation": "Expensive premium; consider credit call spread instead."},
            {"condition": "Strong uptrend",
             "explanation": "Fighting trend wastes theta."},
        ],
        "market_environment_fit": {
            "trending_up": "avoid", "trending_down": "favored",
            "ranging": "avoid", "volatile": "neutral",
            "calm_low_vol": "favored",
        },
        "iv_regime_fit": {
            "iv_low":  {"fit": "favored",
                        "reason": "Cheap downside protection / directional play."},
            "iv_high": {"fit": "avoid",
                        "reason": "Premium is rich; IV crush risk dominates."},
        },
        "theta_behavior":
            "LONG theta-negative. Same daily-decay profile as long calls.",
        "vega_behavior":
            "LONG vega. Benefits from IV expansion (often during sell-offs).",
        "delta_behavior":
            "Negative delta. ATM ≈ -0.50, ITM approaches -1.00.",
        "typical_dte_range": {
            "min": 20, "max": 50, "ideal": 35,
            "reason": "Same as long calls.",
        },
        "lifecycle_expectations": {
            "entry": "ITM-to-ATM for directional; OTM only for high-conviction moves.",
            "management": "Watch for IV expansion during sell-offs (vega benefit).",
            "exit": "Same TP/SL discipline as long calls.",
            "typical_hold_days": 14,
        },
        "risk_summary":
            "Defined risk — max loss is premium paid.",
        "educational_overlay_basic":
            "Buy a put when you expect price to go down. You profit "
            "if price falls below your strike. Max loss is what you paid.",
        "educational_overlay_advanced":
            "Long put is short delta, long vega, short theta, long gamma. "
            "Sell-offs typically expand IV; this provides a positive vega "
            "kicker beyond pure delta P&L.",
        "related_concepts": [
            "delta", "theta_decay", "hedging",
            "vix_correlation", "skew",
        ],
    },
    # ---- BULL_CALL_SPREAD ----
    {
        "rule_id": "BULL_CALL_SPREAD",
        "executive_summary":
            "Debit spread: buy a lower-strike call + sell a higher-strike "
            "call same expiry. Bullish with defined risk; cheaper than "
            "long call alone but caps max profit.",
        "when_to_use": [
            {"condition": "Bullish bias with limited upside expectation",
             "explanation": "Selling the further-OTM call funds part of the long; right-size to expected move."},
            {"condition": "IV rank above ~30",
             "explanation": "Selling the higher leg becomes more valuable as IV rises."},
            {"condition": "DTE 25-60",
             "explanation": "Long enough to capture move, short enough to limit theta."},
        ],
        "when_not_to_use": [
            {"condition": "Expecting a massive upside breakout",
             "explanation": "Long call captures unlimited upside; spread caps it."},
            {"condition": "Very low IV with strong conviction",
             "explanation": "Just buy the call — capped upside not worth the credit."},
        ],
        "market_environment_fit": {
            "trending_up": "favored", "trending_down": "avoid",
            "ranging": "neutral", "volatile": "neutral",
            "calm_low_vol": "favored",
        },
        "iv_regime_fit": {
            "iv_low":  {"fit": "favored",
                        "reason": "Cheap debit cost; long-leg dominates."},
            "iv_high": {"fit": "neutral",
                        "reason": "Short leg compensates but capped profit reduces appeal."},
        },
        "theta_behavior":
            "Net theta near-flat. Long leg's decay partially offset by short leg.",
        "vega_behavior":
            "Net vega LONG but smaller than naked long call.",
        "delta_behavior":
            "Net positive delta. Peaks between strikes near expiry.",
        "typical_dte_range": {
            "min": 25, "max": 60, "ideal": 45,
            "reason": "Balanced decay + room for the move.",
        },
        "lifecycle_expectations": {
            "entry": "Long strike near current price; short strike at expected-move upper bound.",
            "management": "Roll up the short leg if spot moves past it early.",
            "exit": "Take profit at 60-70% of max — last 30% is hardest to extract.",
            "typical_hold_days": 21,
        },
        "risk_summary":
            "Defined risk — max loss = debit paid. Max profit = (spread "
            "width × 100) − debit.",
        "educational_overlay_basic":
            "Buy a call and sell another call further out. Cheaper than just "
            "buying — but your max profit is also capped. Good for mild "
            "bullish views.",
        "educational_overlay_advanced":
            "Vertical debit spread. Delta-positive, slightly long-vega, "
            "low-theta. Maximum P&L decay is asymmetric — early moves earn "
            "most of the spread's potential; late moves leave premium on table.",
        "related_concepts": [
            "vertical_spread", "debit_spread", "theta_neutralization",
            "max_profit_zone", "spread_width",
        ],
    },
    # ---- BEAR_PUT_SPREAD ----
    {
        "rule_id": "BEAR_PUT_SPREAD",
        "executive_summary":
            "Mirror of BULL_CALL_SPREAD for downside. Buy higher-strike "
            "put + sell lower-strike put same expiry.",
        "when_to_use": [
            {"condition": "Bearish bias with limited downside expectation",
             "explanation": "Defined-risk way to express downside view."},
            {"condition": "IV moderate (30-60)",
             "explanation": "Short leg becomes valuable enough to lower cost meaningfully."},
        ],
        "when_not_to_use": [
            {"condition": "Expecting crash / panic move",
             "explanation": "Long put alone captures full downside."},
            {"condition": "IV very high without catalyst",
             "explanation": "Likely paying for vol; consider credit call spread instead."},
        ],
        "market_environment_fit": {
            "trending_up": "avoid", "trending_down": "favored",
            "ranging": "neutral", "volatile": "neutral",
            "calm_low_vol": "favored",
        },
        "iv_regime_fit": {
            "iv_low":  {"fit": "favored", "reason": "Cheap debit cost."},
            "iv_high": {"fit": "neutral",
                        "reason": "Short leg helps but capped upside reduces appeal."},
        },
        "theta_behavior": "Net theta near-flat.",
        "vega_behavior":  "Net vega LONG but smaller than naked long put.",
        "delta_behavior": "Net negative delta.",
        "typical_dte_range": {"min": 25, "max": 60, "ideal": 45,
                              "reason": "Mirror of bull call spread."},
        "lifecycle_expectations": {
            "entry": "Long-put strike near spot; short-put at expected-move lower bound.",
            "management": "Roll short leg down if spot pierces it early.",
            "exit": "Take profit at 60-70% of max.",
            "typical_hold_days": 21,
        },
        "risk_summary":
            "Defined risk — max loss = debit. Max profit = (spread × 100) − debit.",
        "educational_overlay_basic":
            "Buy a put and sell a lower-strike put. Cheaper than just buying — "
            "but profit is capped. Good for mild bearish views.",
        "educational_overlay_advanced":
            "Mirror of bull call spread. Delta-negative, low-theta.",
        "related_concepts": [
            "vertical_spread", "debit_spread", "hedging",
        ],
    },
    # ---- BULL_PUT_SPREAD ----
    {
        "rule_id": "BULL_PUT_SPREAD",
        "executive_summary":
            "Credit spread: sell higher-strike put + buy lower-strike put "
            "(same expiry). Profits if underlying stays above short strike. "
            "Defined risk via the long put.",
        "when_to_use": [
            {"condition": "Bullish or neutral-bullish bias",
             "explanation": "Profits anywhere underlying stays above short strike."},
            {"condition": "IV rank above ~50",
             "explanation": "Rich premium environment — selling makes more credit."},
            {"condition": "DTE 30-45",
             "explanation": "Time decay works for you; theta is the engine."},
        ],
        "when_not_to_use": [
            {"condition": "Expected sharp drop",
             "explanation": "Short put loses faster than long protects."},
            {"condition": "Low IV environment",
             "explanation": "Credit collected won't compensate for risk."},
        ],
        "market_environment_fit": {
            "trending_up": "favored", "trending_down": "avoid",
            "ranging": "favored", "volatile": "neutral",
            "calm_low_vol": "neutral",
        },
        "iv_regime_fit": {
            "iv_low":  {"fit": "avoid",
                        "reason": "Credit too thin to justify defined risk."},
            "iv_high": {"fit": "favored",
                        "reason": "Premium-collection strategy thrives on rich IV."},
        },
        "theta_behavior":
            "SHORT theta-positive. Position GAINS daily from time decay.",
        "vega_behavior":
            "SHORT vega. Benefits from IV compression after entry.",
        "delta_behavior":
            "Net positive delta from selling the put.",
        "typical_dte_range": {
            "min": 30, "max": 45, "ideal": 35,
            "reason": "Sweet spot for theta with manageable gamma.",
        },
        "lifecycle_expectations": {
            "entry": "Short put delta ~0.30 (above support); long put 1-2 strikes lower.",
            "management": "Exit early at 50% of max credit captured.",
            "exit": "Take profit at 50% credit captured. Stop loss at 2× credit "
                    "received (don't let losses escape defined max).",
            "typical_hold_days": 21,
        },
        "risk_summary":
            "Defined risk = spread width × 100 − credit received. "
            "Max profit = credit collected.",
        "educational_overlay_basic":
            "Sell a put and buy a cheaper put as insurance. Profits if "
            "the underlying stays above your short strike. Time works for you.",
        "educational_overlay_advanced":
            "Vertical credit spread. Delta-positive, short-vega, long-theta. "
            "Sweet spot when IV is rich and bias is bullish-neutral.",
        "related_concepts": [
            "credit_spread", "theta_collection", "iv_rank",
            "max_loss_management", "early_exit_50pct",
        ],
    },
    # ---- IRON_CONDOR ----
    {
        "rule_id": "IRON_CONDOR",
        "executive_summary":
            "Two credit spreads (bull put + bear call) on the same expiry. "
            "Profits if underlying stays inside a defined range. Pure "
            "premium-collection / time-decay strategy.",
        "when_to_use": [
            {"condition": "Range-bound / sideways underlying",
             "explanation": "Iron condor profits ONLY when price stays inside the wings."},
            {"condition": "IV rank above 50 (ideally 75+)",
             "explanation": "Rich premium environment funds the wings."},
            {"condition": "No major catalyst inside DTE",
             "explanation": "Avoid earnings/FOMC inside the window — vol expansion is the enemy."},
        ],
        "when_not_to_use": [
            {"condition": "Strong directional view",
             "explanation": "Use a single credit spread instead — fewer legs, more directional."},
            {"condition": "Low IV environment",
             "explanation": "Credit too thin; reward/risk skewed against you."},
            {"condition": "Earnings inside DTE",
             "explanation": "IV expansion + binary move can crush both wings."},
        ],
        "market_environment_fit": {
            "trending_up": "avoid", "trending_down": "avoid",
            "ranging": "favored", "volatile": "avoid",
            "calm_low_vol": "neutral",
        },
        "iv_regime_fit": {
            "iv_low":  {"fit": "avoid",
                        "reason": "Credit too thin for the risk profile."},
            "iv_high": {"fit": "favored",
                        "reason": "IV compression + range-bound = ideal."},
        },
        "theta_behavior":
            "SHORT theta-positive. Strongest theta carry of all defined-risk "
            "strategies, especially near ATM.",
        "vega_behavior":
            "SHORT vega. IV expansion hurts; IV compression is the engine.",
        "delta_behavior":
            "Net delta near zero (delta-neutral at entry).",
        "typical_dte_range": {
            "min": 30, "max": 50, "ideal": 40,
            "reason": "Theta sweet spot with enough buffer for noise.",
        },
        "lifecycle_expectations": {
            "entry": "Short legs at ~0.20 delta. Long legs 1-2 strikes further out.",
            "management": "Adjust if spot threatens one side. Don't let untested side mature.",
            "exit": "Take profit at 25-50% of max credit. Stop loss at 2× credit.",
            "typical_hold_days": 21,
        },
        "risk_summary":
            "Defined risk = wing width × 100 − credit. Max profit = credit.",
        "educational_overlay_basic":
            "Sell a call AND a put further out, with cheap insurance on both. "
            "Profits if underlying stays between your short strikes. Time works for you.",
        "educational_overlay_advanced":
            "Delta-neutral, short-vega, long-theta. Win rate is high but "
            "max loss can be 2-4× max profit; risk management is the game.",
        "related_concepts": [
            "delta_neutral", "wing_width", "credit_spread",
            "iv_rank", "early_exit_25pct", "untested_side",
        ],
    },
    # ---- LONG_STRADDLE ----
    {
        "rule_id": "LONG_STRADDLE",
        "executive_summary":
            "Buy ATM call + ATM put same expiry. Profits on large move "
            "in either direction. Pure volatility play.",
        "when_to_use": [
            {"condition": "Expecting binary catalyst (earnings, FOMC, NFP, CPI)",
             "explanation": "Big move expected but direction uncertain."},
            {"condition": "Realized vol > implied vol regime",
             "explanation": "If actual moves consistently exceed IV, long premium pays."},
            {"condition": "IV rank LOW pre-catalyst",
             "explanation": "Buy cheap vol; sell into the IV ramp before event."},
        ],
        "when_not_to_use": [
            {"condition": "IV rank above 75 pre-event",
             "explanation": "Premium is already priced for the move — IV crush risk dominates."},
            {"condition": "Calm sideways market with no catalyst",
             "explanation": "Theta will eat the position alive."},
        ],
        "market_environment_fit": {
            "trending_up": "neutral", "trending_down": "neutral",
            "ranging": "avoid", "volatile": "favored",
            "calm_low_vol": "avoid",
        },
        "iv_regime_fit": {
            "iv_low":  {"fit": "favored",
                        "reason": "Cheap entry; benefits from IV expansion into catalyst."},
            "iv_high": {"fit": "avoid",
                        "reason": "Paying peak vol; IV crush often kills it post-event."},
        },
        "theta_behavior":
            "LONG theta-negative — double decay (call + put). Time is the enemy.",
        "vega_behavior":
            "LONG vega — double exposure. Benefits from IV expansion.",
        "delta_behavior":
            "Delta-neutral at entry. Gamma grows as catalyst approaches.",
        "typical_dte_range": {
            "min": 7, "max": 21, "ideal": 14,
            "reason": "Short enough to limit theta; long enough to span the event.",
        },
        "lifecycle_expectations": {
            "entry": "Both legs ATM. Total cost ≈ 2× ATM premium.",
            "management": "Watch for IV ramp into the event. Consider closing one leg if directional move occurs early.",
            "exit": "EXIT post-event quickly to avoid IV crush. Take profit on realized-move side; "
                    "let losing leg decay or close.",
            "typical_hold_days": 7,
        },
        "risk_summary":
            "Defined risk = combined premium paid. Theoretically unlimited "
            "profit on either side.",
        "educational_overlay_basic":
            "Buy a call AND a put at the same strike. You profit if price "
            "moves a lot in either direction. Best used before big news.",
        "educational_overlay_advanced":
            "Double premium long. Delta-neutral entry, double-vega exposure, "
            "double-theta drag. Edge requires realized move > implied move "
            "(positive 'gamma scalping' or large directional resolution).",
        "related_concepts": [
            "gamma_scalping", "implied_vs_realized_vol",
            "iv_crush", "catalyst_play", "vol_arb",
        ],
    },
    # ---- LONG_STRANGLE ----
    {
        "rule_id": "LONG_STRANGLE",
        "executive_summary":
            "Cheaper straddle. Buy OTM call + OTM put same expiry. Needs "
            "a larger move to profit but costs less.",
        "when_to_use": [
            {"condition": "Expecting very large move",
             "explanation": "Strangle wins when realized move exceeds combined strike distance."},
            {"condition": "Low IV pre-catalyst",
             "explanation": "Cheap entry for vol expansion play."},
        ],
        "when_not_to_use": [
            {"condition": "Modest expected move",
             "explanation": "Strangle requires a bigger move than straddle to break even."},
            {"condition": "High IV pre-event",
             "explanation": "Paying for the move that's already priced in."},
        ],
        "market_environment_fit": {
            "trending_up": "neutral", "trending_down": "neutral",
            "ranging": "avoid", "volatile": "favored",
            "calm_low_vol": "avoid",
        },
        "iv_regime_fit": {
            "iv_low":  {"fit": "favored", "reason": "Cheap setup."},
            "iv_high": {"fit": "avoid", "reason": "IV crush dominates."},
        },
        "theta_behavior": "LONG theta-negative. Slightly less decay than straddle.",
        "vega_behavior":  "LONG vega.",
        "delta_behavior": "Delta-neutral at entry; gamma lower than straddle.",
        "typical_dte_range": {"min": 7, "max": 21, "ideal": 14,
                              "reason": "Mirror of straddle."},
        "lifecycle_expectations": {
            "entry": "Both legs OTM ~0.20-0.30 delta. Cheaper than straddle.",
            "management": "Same as straddle.",
            "exit": "Quick exit post-catalyst.",
            "typical_hold_days": 7,
        },
        "risk_summary":
            "Defined risk = combined premium. Needs larger move than "
            "straddle to break even.",
        "educational_overlay_basic":
            "Like a straddle but cheaper. You need a bigger move to profit. "
            "Use for catalyst plays when budget is tight.",
        "educational_overlay_advanced":
            "Wider-band straddle. Less gamma, less delta whip, more break-even distance.",
        "related_concepts": [
            "strangle_vs_straddle", "wing_distance", "break_even_distance",
        ],
    },
]

# Short stubs for remaining rule_ids so every strategy has SOME
# educational copy. Operators can replace with longer text later.
STUB_PLAYBOOKS: list[dict] = [
    {
        "rule_id": "SHORT_PUT_CREDIT_SPREAD",
        "summary": "Engine alias for BULL_PUT_SPREAD. Identical payoff.",
    },
    {
        "rule_id": "BEAR_CALL_SPREAD",
        "summary": "Sell call + buy higher call. Bearish credit spread. "
                   "Profits if underlying stays below short strike. "
                   "Defined risk via long call.",
    },
    {
        "rule_id": "SHORT_CALL_CREDIT_SPREAD",
        "summary": "Engine alias for BEAR_CALL_SPREAD.",
    },
    {
        "rule_id": "IRON_BUTTERFLY",
        "summary": "Iron condor with body at ATM. Higher credit + narrower "
                   "break-even band. Max gain at center strike at expiry.",
    },
    {
        "rule_id": "CALENDAR_SPREAD",
        "summary": "Sell front-month + buy back-month same strike. "
                   "Profits from front-leg theta > back-leg theta. "
                   "Watch for IV expansion at back month.",
    },
    {
        "rule_id": "DIAGONAL_SPREAD",
        "summary": "Calendar spread variant with different strikes. "
                   "Moderately directional + theta capture.",
    },
    {
        "rule_id": "SHORT_STRADDLE",
        "summary": "Sell ATM call + ATM put. UNDEFINED RISK. Premium "
                   "collection in expected calm; capped to operator-only.",
    },
    {
        "rule_id": "SHORT_STRANGLE",
        "summary": "Sell OTM call + OTM put. UNDEFINED RISK. Wider safety "
                   "band than short straddle; capped to operator-only.",
    },
    {
        "rule_id": "COVERED_CALL",
        "summary": "Long stock + sell OTM call. Income strategy. "
                   "Stock risk dominates; option leg is premium harvest.",
    },
    {
        "rule_id": "CASH_SECURED_PUT",
        "summary": "Sell OTM put with cash to cover assignment. "
                   "Bullish-to-neutral. Assignment = becomes long stock.",
    },
    {
        "rule_id": "options_shadow_v1",
        "summary": "Engine-internal placeholder. Not a tradeable strategy; "
                   "surfaces under the Developing lane until per-rule signals split.",
    },
]


def upgrade() -> None:
    op.create_table(
        "options_strategy_playbook",
        sa.Column(
            "rule_id", sa.Text(),
            sa.ForeignKey(
                "options_strategy_bias.rule_id",
                name="fk_playbook_bias",
                ondelete="RESTRICT",
            ),
            primary_key=True,
        ),
        sa.Column("executive_summary",        sa.Text(), nullable=False),
        sa.Column(
            "when_to_use", sa.dialects.postgresql.JSONB(),
            nullable=False, server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "when_not_to_use", sa.dialects.postgresql.JSONB(),
            nullable=False, server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "market_environment_fit", sa.dialects.postgresql.JSONB(),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "iv_regime_fit", sa.dialects.postgresql.JSONB(),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("theta_behavior",  sa.Text(), nullable=True),
        sa.Column("vega_behavior",   sa.Text(), nullable=True),
        sa.Column("delta_behavior",  sa.Text(), nullable=True),
        sa.Column(
            "typical_dte_range", sa.dialects.postgresql.JSONB(),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "lifecycle_expectations", sa.dialects.postgresql.JSONB(),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("risk_summary",                sa.Text(), nullable=True),
        sa.Column("educational_overlay_basic",   sa.Text(), nullable=True),
        sa.Column("educational_overlay_advanced", sa.Text(), nullable=True),
        sa.Column(
            "related_concepts", sa.dialects.postgresql.ARRAY(sa.Text()),
            nullable=False, server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column("source", sa.Text(), nullable=False,
                  server_default=sa.text("'manual_seed_2026_05'")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("NOW()"),
        ),
    )

    insert_sql = sa.text(
        """
        INSERT INTO options_strategy_playbook
          (rule_id, executive_summary,
           when_to_use, when_not_to_use,
           market_environment_fit, iv_regime_fit,
           theta_behavior, vega_behavior, delta_behavior,
           typical_dte_range, lifecycle_expectations,
           risk_summary,
           educational_overlay_basic, educational_overlay_advanced,
           related_concepts, source)
        VALUES
          (:rule_id, :exec_summary,
           CAST(:when_to AS jsonb), CAST(:when_not AS jsonb),
           CAST(:env_fit AS jsonb), CAST(:iv_fit AS jsonb),
           :theta, :vega, :delta,
           CAST(:dte AS jsonb), CAST(:lifecycle AS jsonb),
           :risk,
           :basic, :advanced,
           CAST(:concepts AS text[]),
           'manual_seed_2026_05')
        ON CONFLICT (rule_id) DO NOTHING
        """
    )

    for p in PLAYBOOKS:
        op.execute(insert_sql.bindparams(
            rule_id=p["rule_id"],
            exec_summary=p["executive_summary"],
            when_to=json.dumps(p["when_to_use"]),
            when_not=json.dumps(p["when_not_to_use"]),
            env_fit=json.dumps(p["market_environment_fit"]),
            iv_fit=json.dumps(p["iv_regime_fit"]),
            theta=p["theta_behavior"],
            vega=p["vega_behavior"],
            delta=p["delta_behavior"],
            dte=json.dumps(p["typical_dte_range"]),
            lifecycle=json.dumps(p["lifecycle_expectations"]),
            risk=p["risk_summary"],
            basic=p["educational_overlay_basic"],
            advanced=p["educational_overlay_advanced"],
            concepts="{" + ",".join(p["related_concepts"]) + "}",
        ))

    # Stub playbooks — keep schema fully populated for the other rule_ids.
    stub_sql = sa.text(
        """
        INSERT INTO options_strategy_playbook
          (rule_id, executive_summary, source)
        VALUES (:rule_id, :summary, 'manual_seed_2026_05_stub')
        ON CONFLICT (rule_id) DO NOTHING
        """
    )
    for p in STUB_PLAYBOOKS:
        op.execute(stub_sql.bindparams(
            rule_id=p["rule_id"],
            summary=p["summary"],
        ))


def downgrade() -> None:
    op.drop_table("options_strategy_playbook")
