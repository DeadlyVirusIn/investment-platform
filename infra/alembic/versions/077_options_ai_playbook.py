"""Phase G — AI Strategy Approaches (meta-playbooks).

Layer above options_strategy_playbook. Each row is a thematic
approach (Premium Harvesting / Momentum Breakout / etc.) that
groups several individual strategies and explains when the approach
itself fits the current market regime.

Discipline:
  * Honest tone — no win-rate claims, no guru framing.
  * Every row carries a `transparency_note` for risk + uncertainty.
  * Maps approach → typical_strategies (rule_ids in
    options_strategy_bias). No FK enforced because rule_ids may
    legitimately not all be seeded.
  * Read-only seed; operators replace via INSERT…ON CONFLICT.

Revision ID: 077_ai_playbook
Revises: 076_strategy_playbook
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "077_ai_playbook"
down_revision = "076_strategy_playbook"
branch_labels = None
depends_on = None


APPROACHES: list[dict] = [
    {
        "slug": "premium_harvesting",
        "name": "Premium Harvesting",
        "one_liner":
            "Collect option premium when IV is rich and direction is "
            "secondary.",
        "thematic_summary":
            "Premium harvesting strategies sell defined-risk credit "
            "spreads in elevated implied-volatility environments. "
            "Edge comes from IV mean-reversion + theta carry, not "
            "directional precision. The approach favors high IV rank "
            "and underlyings without an imminent binary catalyst.",
        "when_it_fits": [
            {"signal": "IV rank ≥ 50 across the universe",
             "explanation": "Premium is rich; credit spreads pay more for the same risk."},
            {"signal": "Range-bound price action 5-15 sessions",
             "explanation": "No strong trend; theta carry is the dominant payoff."},
            {"signal": "No high-importance catalyst inside DTE",
             "explanation": "Binary moves can blow through wings; avoid event windows."},
        ],
        "when_it_doesnt": [
            {"signal": "IV rank < 30",
             "explanation": "Credit collected is too thin to cover defined max loss."},
            {"signal": "Trending market",
             "explanation": "Directional move past the short strike erodes the entire credit."},
            {"signal": "Earnings/FOMC inside DTE window",
             "explanation": "Vol expansion + binary moves destroy the premium edge."},
        ],
        "suitability": ["income_focused", "defined_risk", "conservative"],
        "typical_strategies": [
            "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD", "IRON_CONDOR",
            "IRON_BUTTERFLY", "SHORT_PUT_CREDIT_SPREAD",
            "SHORT_CALL_CREDIT_SPREAD",
        ],
        "iv_regime_preference": "high",
        "typical_dte_range": {"min": 30, "max": 45, "ideal": 35,
                              "reason": "Theta sweet spot + manageable gamma."},
        "risk_character": "defined",
        "profit_taking_guidance":
            "Take profit at 25-50% of max credit. Hold-to-expiry "
            "extracts the last dollar but risks gamma whips inside "
            "the final week.",
        "theta_expectations":
            "POSITIVE theta carry. Daily P&L favors patience, "
            "especially 30-15 DTE.",
        "iv_behavior_explainer":
            "Short-vega. Position GAINS when implied vol compresses "
            "and LOSES on IV expansion. Time-spread-rich regimes are "
            "the strongest tailwind.",
        "risk_expansion_scenarios": [
            {"scenario": "Surprise catalyst inside DTE",
             "explanation": "IV expansion + binary move can crush both wings "
                            "of an Iron Condor — managing pre-event closes is "
                            "critical."},
            {"scenario": "Trend break past short strike",
             "explanation": "Loss accelerates near max as spot moves through "
                            "the short leg."},
            {"scenario": "Liquidity gap on rolls",
             "explanation": "Rolling defensive positions in thin markets can "
                            "lock in unfavorable fills."},
        ],
        "educational_overlay_basic":
            "You sell options to collect premium and accept defined "
            "downside. Time helps you. Big moves hurt you. Best in "
            "calm but expensive option markets.",
        "educational_overlay_advanced":
            "Short-vega + long-theta. Edge is IV mean-reversion + "
            "time decay capture. Risk/reward typically asymmetric "
            "(reward < risk), so win rate must compensate. Position "
            "sizing is the actual P&L driver.",
        "regime_signals": [
            "IV rank ≥ 50 universe-wide",
            "Realized vol < implied vol (positive VRP)",
            "VIX term structure in contango",
            "No NFP/FOMC/CPI within current DTE window",
        ],
        "transparency_note":
            "Premium harvesting wins frequently but loses larger. Max "
            "loss is the wing width minus credit. Historical "
            "premium-collection systems are sensitive to fat-tail "
            "events; size accordingly. This is not a 'high win-rate' "
            "system without disciplined risk management.",
    },
    {
        "slug": "momentum_breakout",
        "name": "Momentum Breakout",
        "one_liner":
            "Express directional conviction with defined-risk debit "
            "structures.",
        "thematic_summary":
            "Capture sustained moves in trending markets via long "
            "calls / long puts and debit spreads. Edge comes from "
            "realized move exceeding the implied move at entry, "
            "typically when IV is cheap and trend is confirmed.",
        "when_it_fits": [
            {"signal": "Strong directional trend (>20-day breakout)",
             "explanation": "Long-delta debit captures continuation."},
            {"signal": "IV rank < 50",
             "explanation": "Cheap premium funds the directional bet."},
            {"signal": "DTE 20-50",
             "explanation": "Long enough for the move; short enough to limit theta."},
        ],
        "when_it_doesnt": [
            {"signal": "Sideways / mean-reverting tape",
             "explanation": "Theta decay eats long-debit without realized move."},
            {"signal": "Very high IV rank",
             "explanation": "Premium is expensive; expected move already priced."},
            {"signal": "Late-stage trend exhaustion",
             "explanation": "Counter-trend reversal is the dominant risk."},
        ],
        "suitability": ["growth_oriented", "defined_risk", "directional"],
        "typical_strategies": [
            "LONG_CALL", "LONG_PUT",
            "BULL_CALL_SPREAD", "BEAR_PUT_SPREAD",
            "DIAGONAL_SPREAD",
        ],
        "iv_regime_preference": "low",
        "typical_dte_range": {"min": 20, "max": 50, "ideal": 35,
                              "reason": "Balanced theta vs runway."},
        "risk_character": "defined",
        "profit_taking_guidance":
            "Take profit at +50-100% of premium. Trailing stops on "
            "intrinsic value preserve gains as trend matures.",
        "theta_expectations":
            "NEGATIVE theta. Time works against the position; the "
            "trade thesis must play out faster than implied.",
        "iv_behavior_explainer":
            "Long-vega — IV expansion (often on volatility spikes) "
            "is a tailwind. IV compression hurts; avoid post-event "
            "entries when IV crush is likely.",
        "risk_expansion_scenarios": [
            {"scenario": "Trend reversal",
             "explanation": "Long-delta against new trend loses fast."},
            {"scenario": "IV crush after entry",
             "explanation": "Vega-loss can dominate even when delta is right."},
            {"scenario": "Gap risk on illiquid names",
             "explanation": "Overnight gaps past breakeven create binary losses."},
        ],
        "educational_overlay_basic":
            "You buy options when you expect price to move strongly "
            "in one direction. Cheap premium makes the bet attractive. "
            "Time and lack of move hurt you.",
        "educational_overlay_advanced":
            "Long-delta + long-vega + short-theta. P&L driven by "
            "realized > implied move. Sizing should reflect "
            "expected-move discipline, not 'all-in conviction'.",
        "regime_signals": [
            "Major index above 50/200-day moving averages",
            "Sector breadth confirming",
            "VIX moderate to low",
            "Realized vol > implied vol (negative VRP)",
        ],
        "transparency_note":
            "Long-debit strategies lose more frequently than they win. "
            "Edge comes from win SIZE, not win rate. Most premium "
            "decays unused. This approach demands directional accuracy "
            "+ disciplined exits.",
    },
    {
        "slug": "earnings_expansion",
        "name": "Earnings Expansion",
        "one_liner":
            "Trade implied-volatility expansion ahead of named "
            "earnings events.",
        "thematic_summary":
            "Establish long-vol structures BEFORE earnings dates so "
            "IV ramp into the event lifts the position. Exit before "
            "the print to avoid IV crush. Pure volatility play — "
            "direction is secondary.",
        "when_it_fits": [
            {"signal": "Earnings within 5-15 days",
             "explanation": "IV ramp window captures vol expansion."},
            {"signal": "IV rank < 50 going in",
             "explanation": "Room for IV to expand. Already-rich IV is priced in."},
        ],
        "when_it_doesnt": [
            {"signal": "Earnings already priced (IV > 80)",
             "explanation": "IV crush post-event likely exceeds realized move benefit."},
            {"signal": "Earnings already passed",
             "explanation": "No catalyst; pure theta drag remains."},
        ],
        "suitability": ["event_driven", "growth_oriented", "defined_risk"],
        "typical_strategies": [
            "LONG_STRADDLE", "LONG_STRANGLE",
            "BULL_CALL_SPREAD", "BEAR_PUT_SPREAD",
        ],
        "iv_regime_preference": "low_to_moderate",
        "typical_dte_range": {"min": 7, "max": 30, "ideal": 14,
                              "reason": "Span event without paying for far theta."},
        "risk_character": "defined",
        "profit_taking_guidance":
            "EXIT before earnings print. Holding through earnings "
            "exposes the position to IV crush regardless of direction.",
        "theta_expectations":
            "NEGATIVE theta — straddles double the decay. Manage "
            "duration tightly; don't open too early.",
        "iv_behavior_explainer":
            "Long-vega — primary edge. IV typically rises into "
            "earnings then collapses on print. Capture the ramp; "
            "avoid the crush.",
        "risk_expansion_scenarios": [
            {"scenario": "IV crush before exit",
             "explanation": "If you hold through print, IV typically halves overnight."},
            {"scenario": "Earnings date moved",
             "explanation": "Company reschedules; thesis evaporates."},
        ],
        "educational_overlay_basic":
            "Earnings create big moves AND big volatility. Buying "
            "options before earnings can profit from the vol increase. "
            "Just close before the actual report.",
        "educational_overlay_advanced":
            "Pure vol arbitrage — trading implied vs realized "
            "earnings move. Edge requires entering when IV is below "
            "historical earnings move; exit captures the IV ramp.",
        "regime_signals": [
            "Symbol-level earnings within DTE",
            "Symbol IV rank rising 5 sessions pre-event",
            "Historical earnings move > current implied move",
        ],
        "transparency_note":
            "Earnings plays carry binary risk. Historically only "
            "~50-60% of earnings stocks move past their implied "
            "move. Holding through print is essentially a coin flip "
            "amplified by IV crush. Strict exit discipline is "
            "mandatory, not optional.",
    },
    {
        "slug": "volatility_compression",
        "name": "Volatility Compression",
        "one_liner":
            "Sell elevated vol expected to mean-revert.",
        "thematic_summary":
            "When implied vol is rich but no clear catalyst justifies "
            "it, sell defined-risk credit spreads or iron condors to "
            "capture the mean-reversion. Edge comes from IV typically "
            "compressing faster than realized move materializes.",
        "when_it_fits": [
            {"signal": "IV rank ≥ 70 with no scheduled catalyst",
             "explanation": "Premium is rich and not priced for known event."},
            {"signal": "Realized vol < implied vol consistently",
             "explanation": "Positive VRP confirms the IV is overpriced."},
        ],
        "when_it_doesnt": [
            {"signal": "Crisis-driven vol spike",
             "explanation": "IV can keep expanding through 'normal' compression triggers."},
            {"signal": "Catalyst inside DTE",
             "explanation": "Compression thesis breaks if event delivers volatility."},
        ],
        "suitability": ["income_focused", "defined_risk", "conservative"],
        "typical_strategies": [
            "IRON_CONDOR", "IRON_BUTTERFLY",
            "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD",
            "CALENDAR_SPREAD",
        ],
        "iv_regime_preference": "high",
        "typical_dte_range": {"min": 25, "max": 45, "ideal": 35,
                              "reason": "Time for IV mean-reversion to play out."},
        "risk_character": "defined",
        "profit_taking_guidance":
            "Exit at 30-50% of max credit. The last 30% of theta "
            "carry is fastest decayed BUT most gamma-exposed.",
        "theta_expectations":
            "POSITIVE theta + POSITIVE vega-compression carry.",
        "iv_behavior_explainer":
            "Short-vega + long-theta. Edge compounds when both "
            "compression AND time work for you.",
        "risk_expansion_scenarios": [
            {"scenario": "Vol regime shift",
             "explanation": "Sustained high vol can persist for weeks beyond expected reversion."},
            {"scenario": "Pin-risk near expiry",
             "explanation": "Underlying parked at short strike near expiry creates "
                            "ambiguous assignment risk."},
        ],
        "educational_overlay_basic":
            "When option premiums are unusually expensive, you can "
            "sell that expensive premium expecting prices to "
            "normalize. Defined risk via the wings.",
        "educational_overlay_advanced":
            "Volatility risk premium harvest. Empirical: IV typically "
            "overestimates realized move by 1-3 vol points; this "
            "approach systematizes that capture.",
        "regime_signals": [
            "IV rank ≥ 70 sustained",
            "VIX > 25 with no FOMC/earnings/CPI catalyst",
            "Term structure flat or inverted",
        ],
        "transparency_note":
            "Volatility CAN keep expanding for weeks during real "
            "crises. 2008, 2020, and 2022 saw multi-week IV regimes "
            "well above historical norms. Compression bets require "
            "wing width tuned to fat-tail outcomes, not normal "
            "distributions.",
    },
    {
        "slug": "defensive_hedging",
        "name": "Defensive Hedging",
        "one_liner":
            "Insurance for an existing long-equity book.",
        "thematic_summary":
            "Buy puts or put spreads to hedge an existing long-stock "
            "exposure. Pay defined premium for asymmetric downside "
            "protection. Edge is not P&L; edge is sleep-at-night + "
            "tail protection.",
        "when_it_fits": [
            {"signal": "Concentrated long-stock position",
             "explanation": "Hedge a single-stock or sector exposure cheaply."},
            {"signal": "Macro uncertainty rising",
             "explanation": "Cheap vol before vol expands is the textbook hedge window."},
        ],
        "when_it_doesnt": [
            {"signal": "Cheap puts and bullish view",
             "explanation": "Naked long stock without hedge cost is fine when conviction high."},
            {"signal": "Already-elevated IV",
             "explanation": "Insurance is expensive; consider reducing stock exposure instead."},
        ],
        "suitability": ["hedge_oriented", "defensive", "defined_risk"],
        "typical_strategies": ["LONG_PUT", "BEAR_PUT_SPREAD"],
        "iv_regime_preference": "low",
        "typical_dte_range": {"min": 30, "max": 90, "ideal": 60,
                              "reason": "Cover macro horizon with manageable decay."},
        "risk_character": "defined",
        "profit_taking_guidance":
            "Hedges typically expire worthless — that's the WIN. "
            "Take profit only on protective puts when underlying "
            "spike justifies redeployment.",
        "theta_expectations":
            "NEGATIVE theta — cost of insurance. Plan it as a budget "
            "line item, not a P&L source.",
        "iv_behavior_explainer":
            "Long-vega — protection appreciates on vol spikes, "
            "which typically coincide with sell-offs (negative skew "
            "for sellers, positive for hedgers).",
        "risk_expansion_scenarios": [
            {"scenario": "Whipsaw markets",
             "explanation": "Multiple put-buy/expire cycles drain budget."},
            {"scenario": "Slow grind down",
             "explanation": "Hedge expires before realizing protection."},
        ],
        "educational_overlay_basic":
            "Buy a put to protect stock you own. If the stock falls, "
            "the put gains. If it doesn't, you paid insurance — "
            "same as car insurance.",
        "educational_overlay_advanced":
            "Tail-hedge or systematic put-spread collar. Cost-of-carry "
            "is the explicit budget. Skew + term-structure optimization "
            "lowers cost.",
        "regime_signals": [
            "VIX < 18 (cheap insurance)",
            "Macro uncertainty rising (Fed, geopolitics)",
            "Personal portfolio drawdown comfort exceeded",
        ],
        "transparency_note":
            "Hedges are designed to LOSE most of the time. They are "
            "not a profit center. Win condition is 'didn't blow up'. "
            "Track them as a budget, not a strategy P&L.",
    },
    {
        "slug": "neutral_income",
        "name": "Neutral Income",
        "one_liner":
            "Generate income when no directional view exists.",
        "thematic_summary":
            "Range-bound markets favor delta-neutral credit "
            "structures. Iron condors + butterflies + calendars "
            "capture theta + IV compression simultaneously.",
        "when_it_fits": [
            {"signal": "No clear directional view",
             "explanation": "Delta-neutral lets you NOT need to be right on direction."},
            {"signal": "Range-bound 10-20 sessions",
             "explanation": "Historical range supports range-bound assumption."},
            {"signal": "IV rank moderate-to-high",
             "explanation": "Credit collection improves materially."},
        ],
        "when_it_doesnt": [
            {"signal": "Breakout / trend regime",
             "explanation": "Underlying moves through wings; defined-risk fails."},
            {"signal": "Earnings or macro catalyst inside DTE",
             "explanation": "Binary moves overwhelm theta carry."},
        ],
        "suitability": ["income_focused", "defined_risk", "conservative"],
        "typical_strategies": [
            "IRON_CONDOR", "IRON_BUTTERFLY", "CALENDAR_SPREAD",
        ],
        "iv_regime_preference": "moderate_to_high",
        "typical_dte_range": {"min": 30, "max": 50, "ideal": 40,
                              "reason": "Best theta sweet spot."},
        "risk_character": "defined",
        "profit_taking_guidance":
            "Exit at 25-50% max credit. Don't let untested wings "
            "mature past 21 DTE — gamma risk overwhelms reward.",
        "theta_expectations":
            "POSITIVE theta — the engine. Theta dominates over 30-21 "
            "DTE; gamma risk rises sharply inside 21.",
        "iv_behavior_explainer":
            "Short-vega — IV compression doubles the theta benefit. "
            "IV expansion is the primary headwind.",
        "risk_expansion_scenarios": [
            {"scenario": "Tested wing approaches expiry",
             "explanation": "Adjust or close before gamma turns binary."},
            {"scenario": "Surprise news breaks range",
             "explanation": "Defined max loss limits damage but still material."},
        ],
        "educational_overlay_basic":
            "When you don't have a strong view on direction, you can "
            "still profit if the underlying stays in a range. Sell "
            "options on both sides with insurance.",
        "educational_overlay_advanced":
            "Delta-neutral, short-vega, long-theta. Win rate high but "
            "max loss can exceed max win by 2-4x; sizing is everything.",
        "regime_signals": [
            "ATR contracting",
            "Implied move > realized move (positive VRP)",
            "No catalyst in DTE window",
        ],
        "transparency_note":
            "Neutral income systems often show high historical win "
            "rates that mask deep tail-risk loss profiles. A single "
            "max-loss event can erase 4-6 typical wins. Win rate "
            "≠ edge.",
    },
    {
        "slug": "event_volatility",
        "name": "Event Volatility",
        "one_liner":
            "Trade scheduled binary macro/single-name events.",
        "thematic_summary":
            "Position long-vol BEFORE FOMC, CPI, NFP, earnings — "
            "capture IV ramp + realized move. Close pre-event or "
            "directly after to avoid IV crush. Cousin of "
            "Earnings Expansion but broader across macro catalysts.",
        "when_it_fits": [
            {"signal": "Calendar-confirmed event within 5-14 days",
             "explanation": "FOMC, CPI, NFP, earnings — known schedule."},
            {"signal": "IV rank < 60 going in",
             "explanation": "Room for vol expansion."},
        ],
        "when_it_doesnt": [
            {"signal": "Already-elevated IV",
             "explanation": "Move is already priced; IV crush dominates."},
            {"signal": "No named catalyst in window",
             "explanation": "Pure theta drag without vol kicker."},
        ],
        "suitability": ["event_driven", "growth_oriented", "defined_risk"],
        "typical_strategies": ["LONG_STRADDLE", "LONG_STRANGLE"],
        "iv_regime_preference": "low_to_moderate",
        "typical_dte_range": {"min": 7, "max": 21, "ideal": 14,
                              "reason": "Span event without paying for far theta."},
        "risk_character": "defined",
        "profit_taking_guidance":
            "Exit pre-event when IV ramp is captured. If holding "
            "through, exit IMMEDIATELY post-print on the winning "
            "leg; manage the losing leg.",
        "theta_expectations":
            "Double-negative theta (long straddle/strangle).",
        "iv_behavior_explainer":
            "Long-vega — entire edge. Ramp captures the rise; "
            "close before crush.",
        "risk_expansion_scenarios": [
            {"scenario": "Event passes with non-event move",
             "explanation": "IV crush + no realized move = full premium loss."},
            {"scenario": "Event delayed",
             "explanation": "Theta drains while catalyst slides past expiry."},
        ],
        "educational_overlay_basic":
            "Big scheduled events (FOMC, jobs reports, earnings) "
            "expand option premiums beforehand. Buy options early; "
            "sell them before the event.",
        "educational_overlay_advanced":
            "Macro vol arbitrage. Edge requires entering when "
            "named-event IV is below historical event-move. Exit "
            "discipline is mandatory — IV crush is brutal.",
        "regime_signals": [
            "market_event_calendar event in DTE window",
            "Event importance: high",
            "Pre-event IV rank rising",
        ],
        "transparency_note":
            "Most event premium captures the move post-hoc, not "
            "pre-emptively. Holding through events is essentially a "
            "binary bet with poor odds. The systematic edge is "
            "trading the IV RAMP, not the EVENT.",
    },
]


def upgrade() -> None:
    op.create_table(
        "options_ai_playbook",
        sa.Column("slug",              sa.Text(), primary_key=True),
        sa.Column("name",              sa.Text(), nullable=False),
        sa.Column("one_liner",         sa.Text(), nullable=False),
        sa.Column("thematic_summary",  sa.Text(), nullable=False),
        sa.Column(
            "when_it_fits", sa.dialects.postgresql.JSONB(),
            nullable=False, server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "when_it_doesnt", sa.dialects.postgresql.JSONB(),
            nullable=False, server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "suitability", sa.dialects.postgresql.ARRAY(sa.Text()),
            nullable=False, server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column(
            "typical_strategies", sa.dialects.postgresql.ARRAY(sa.Text()),
            nullable=False, server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column("iv_regime_preference",  sa.Text(), nullable=False),
        sa.Column(
            "typical_dte_range", sa.dialects.postgresql.JSONB(),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("risk_character",         sa.Text(), nullable=False),
        sa.Column("profit_taking_guidance", sa.Text(), nullable=True),
        sa.Column("theta_expectations",     sa.Text(), nullable=True),
        sa.Column("iv_behavior_explainer",  sa.Text(), nullable=True),
        sa.Column(
            "risk_expansion_scenarios", sa.dialects.postgresql.JSONB(),
            nullable=False, server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("educational_overlay_basic",    sa.Text(), nullable=True),
        sa.Column("educational_overlay_advanced", sa.Text(), nullable=True),
        sa.Column(
            "regime_signals", sa.dialects.postgresql.JSONB(),
            nullable=False, server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("transparency_note",      sa.Text(), nullable=False),
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
        sa.CheckConstraint(
            "iv_regime_preference IN ('low','low_to_moderate','moderate',"
            "'moderate_to_high','high','any')",
            name="ck_ai_playbook_iv_pref",
        ),
        sa.CheckConstraint(
            "risk_character IN ('defined','limited','asymmetric','unbounded')",
            name="ck_ai_playbook_risk",
        ),
    )

    insert_sql = sa.text(
        """
        INSERT INTO options_ai_playbook
          (slug, name, one_liner, thematic_summary,
           when_it_fits, when_it_doesnt,
           suitability, typical_strategies,
           iv_regime_preference, typical_dte_range,
           risk_character, profit_taking_guidance,
           theta_expectations, iv_behavior_explainer,
           risk_expansion_scenarios,
           educational_overlay_basic, educational_overlay_advanced,
           regime_signals, transparency_note)
        VALUES
          (:slug, :name, :one_liner, :summary,
           CAST(:fits AS jsonb), CAST(:doesnt AS jsonb),
           CAST(:suitability AS text[]), CAST(:strats AS text[]),
           :iv_pref, CAST(:dte AS jsonb),
           :risk, :profit_take,
           :theta, :iv_beh,
           CAST(:expand AS jsonb),
           :basic, :advanced,
           CAST(:signals AS jsonb), :transparency)
        ON CONFLICT (slug) DO NOTHING
        """
    )
    for a in APPROACHES:
        op.execute(insert_sql.bindparams(
            slug=a["slug"], name=a["name"], one_liner=a["one_liner"],
            summary=a["thematic_summary"],
            fits=json.dumps(a["when_it_fits"]),
            doesnt=json.dumps(a["when_it_doesnt"]),
            suitability="{" + ",".join(a["suitability"]) + "}",
            strats="{" + ",".join(a["typical_strategies"]) + "}",
            iv_pref=a["iv_regime_preference"],
            dte=json.dumps(a["typical_dte_range"]),
            risk=a["risk_character"],
            profit_take=a["profit_taking_guidance"],
            theta=a["theta_expectations"],
            iv_beh=a["iv_behavior_explainer"],
            expand=json.dumps(a["risk_expansion_scenarios"]),
            basic=a["educational_overlay_basic"],
            advanced=a["educational_overlay_advanced"],
            signals=json.dumps(a["regime_signals"]),
            transparency=a["transparency_note"],
        ))


def downgrade() -> None:
    op.drop_table("options_ai_playbook")
