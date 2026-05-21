// OptionsOpportunityCard — canonical card primitive.
//
// Single reusable unit for:
//   * Today spotlight (OptionsOpportunitySpotlight)
//   * Opportunities lanes (OpportunityLane)
//   * Research recommendations (Phase D)
//   * Position Intelligence recommendations (Phase C)
//
// Reads the canonical payload shape returned by
// /api/options/opportunities. No derivation; honest empty states for
// missing fields. Composed from the 8 Copilot primitives so visual
// language stays consistent across surfaces.

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import OptionsBiasChip, { OptionsBias } from "./OptionsBiasChip";
import OptionsActionPills from "./OptionsActionPills";
import OptionsCatalystChip from "./OptionsCatalystChip";
import EducationalDrawer from "./EducationalDrawer";
import { OptionsShadowWatermark } from "./OptionsLiveStateChip";

// Canonical payload shape — kept in lockstep with the backend
// `opportunity_to_dict` projection. Optional fields degrade gracefully.
export interface OpportunityPayload {
  observation_id: number;
  underlying: string;
  rule_id: string;
  option_symbol?: string;
  expiry?: string | null;
  strike?: number | null;
  option_type?: string;
  side?: string;
  run_date?: string;
  bias?: string;
  directional_view?: string;
  risk_profile?: string;
  score?: number;
  composite_score?: number;
  ranking_breakdown?: {
    score?: number; freshness?: number; liquidity?: number;
    iv_fit?: number; event?: number;
  };
  would_trade?: boolean;
  qualified?: boolean;
  dte?: number;
  earnings_between?: boolean;
  liquidity_tier?: string;
  iv_rank?: number | null;
  atm_iv?: number | null;
  premium_tier?: string;
  bid?: number | null;
  ask?: number | null;
  mid?: number | null;
  spread?: number | null;
  open_interest?: number | null;
  volume?: number | null;
  delta?: number | null;
  gamma?: number | null;
  theta?: number | null;
  vega?: number | null;
  iv?: number | null;
  quote_age_seconds?: number | null;
  provider?: string | null;
  rationale_points?: string[];
  template_name?: string | null;
  why_strategy?: string | null;
  why_expiry?: string | null;
  what_invalidates?: string[];
  theta_iv_impact?: string | null;
  // Phase B6 — explainability metadata from options_strategy_candidate
  why_emitted?: string | null;
  triggering_rule?: string | null;
  rejected_alternatives?: Array<{ rule_id?: string; reason?: string }>;
  strategy_fit_reason?: string | null;
  iv_fit_reason?: string | null;
  dte_fit_reason?: string | null;
  liquidity_fit_reason?: string | null;
  // Phase B7 — catalyst metadata.
  earliest_event_date?: string | null;
  earliest_event_type?: string | null;
  earliest_event_importance?: string | null;
  event_days_away?: number | null;
  catalyst_title?: string | null;
  catalyst_explanation?: string | null;
}


function normalizeBias(b: string | undefined): OptionsBias {
  if (!b) return "developing";
  const k = b.toLowerCase();
  if (k === "bullish" || k === "bearish" || k === "neutral"
      || k === "event" || k === "developing" || k === "conviction") {
    return k as OptionsBias;
  }
  return "developing";
}


function strategyDisplayName(ruleId: string | undefined): string {
  if (!ruleId) return "Strategy";
  return ruleId
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, c => c.toUpperCase());
}


function legSummary(item: OpportunityPayload): string | null {
  if (item.strike == null && !item.option_type) return null;
  const parts: string[] = [];
  if (item.option_type) parts.push(item.option_type.toUpperCase());
  if (item.strike != null) parts.push(`$${item.strike}`);
  if (item.side) parts.push(item.side.toUpperCase());
  return parts.join(" · ") || null;
}


export interface OptionsOpportunityCardProps {
  item: OpportunityPayload;
  /** When true, the educational drawer opens on Explain. Defaults true. */
  explainable?: boolean;
  /** Canary state — disables paper-trade pill when false. */
  canaryEnabled?: boolean;
  /** Optional callback hook for analytics / future Compare flow. */
  onOpenResearch?: (item: OpportunityPayload) => void;
  /** Phase J — conviction-grade emphasis. Parent surface decides which
   *  ONE card per render earns the gold stripe. Defaults false. */
  conviction?: boolean;
}


export default function OptionsOpportunityCard({
  item, explainable = true, canaryEnabled = false,
  onOpenResearch, conviction = false,
}: OptionsOpportunityCardProps) {
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const goToResearch = onOpenResearch
    ? () => onOpenResearch(item)
    : () => navigate(`/options/research/${item.underlying}`);

  const bias = normalizeBias(item.bias);
  const compositeScore = item.composite_score
    ?? item.score
    ?? null;
  const legText = legSummary(item);

  // H.3 — curated card. Four elements:
  //   1. headline    — underlying + strategy name (linked to playbook)
  //   2. sentence    — strategist's one-line read (why_emitted or fallback)
  //   3. metric      — composite confidence %, oversized
  //   4. action      — Explain (opens drawer where ALL detail lives)
  //
  // Catalyst chip surfaces ONLY when high-importance event is in DTE
  // window — earned, not decorated.
  const strategistSentence =
       item.why_emitted
    ?? item.strategy_fit_reason
    ?? item.directional_view
    ?? null;
  const confidencePct = compositeScore != null
    ? Math.round(compositeScore * 100)
    : null;
  const isCatalystImportant =
    item.earliest_event_type != null
    && item.earliest_event_importance === "high";

  return (
    <article
      className="opt-opp-card opt-opp-card-curated"
      data-test="opt-opportunity-card"
      data-bias={bias}
      data-conviction={conviction ? "true" : undefined}
    >
      {/* 1. headline */}
      <header className="opt-opp-head">
        <div className="opt-opp-symbol">
          {item.underlying}
          <OptionsShadowWatermark />
        </div>
        <OptionsBiasChip bias={bias} />
      </header>

      <div className="opt-opp-strategy-row">
        <Link
          to={`/options/learn/${item.rule_id}`}
          className="opt-opp-strategy opt-opp-strategy-link"
          data-test={`opt-opp-playbook-link-${item.rule_id}`}
          title="Open strategy playbook"
        >
          {strategyDisplayName(item.rule_id)}
        </Link>
        {legText && <span className="opt-opp-leg">{legText}</span>}
      </div>

      {/* 2. strategist sentence */}
      {strategistSentence && (
        <p className="opt-opp-sentence">{strategistSentence}</p>
      )}

      {/* 3. dominant metric — caption anchors what the number means
            against today's market, not an abstract score. */}
      <div className="opt-opp-metric">
        <div className="opt-opp-metric-value">
          {confidencePct != null ? `${confidencePct}%` : "—"}
        </div>
        <div className="opt-opp-metric-label">fit with today's market</div>
      </div>

      {/* Catalyst chip — earned visibility only when high-importance */}
      {isCatalystImportant && (
        <div className="opt-opp-meta">
          <OptionsCatalystChip
            eventType={item.earliest_event_type}
            eventDate={item.earliest_event_date}
            daysAway={item.event_days_away}
            importance={item.earliest_event_importance}
            title={item.catalyst_title}
            explanation={item.catalyst_explanation} />
        </div>
      )}

      {/* 4. action */}
      <OptionsActionPills
        onExplain={explainable ? () => setDrawerOpen(true) : undefined}
        onOpenResearch={goToResearch}
        canaryEnabled={canaryEnabled} />

      {explainable && (
        <EducationalDrawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          title="Why this setup"
          strategyName={strategyDisplayName(item.rule_id)}
          whyStrategy={
            item.why_strategy
            ?? item.strategy_fit_reason
            ?? item.why_emitted
            ?? item.directional_view
            ?? null
          }
          whyExpiry={item.why_expiry ?? item.dte_fit_reason ?? null}
          whatInvalidates={
            item.what_invalidates
            ?? (item.rejected_alternatives && item.rejected_alternatives.length > 0
                ? item.rejected_alternatives.map(
                    r => `${r.rule_id ?? "alternative"}: ${r.reason ?? "considered + dismissed"}`,
                  )
                : undefined)
          }
          thetaIvImpact={item.theta_iv_impact ?? item.iv_fit_reason ?? null}
          catalystTitle={item.catalyst_title}
          catalystDate={item.earliest_event_date}
          catalystDaysAway={item.event_days_away}
          catalystImportance={item.earliest_event_importance}
          catalystExplanation={item.catalyst_explanation}
          footer={item.triggering_rule
            ? <span>Triggering rule: <code>{item.triggering_rule}</code></span>
            : null} />
      )}
    </article>
  );
}
