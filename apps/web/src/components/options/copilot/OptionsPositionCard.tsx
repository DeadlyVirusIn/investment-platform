// OptionsPositionCard — AI trade-management card.
//
// Consumes the canonical payload from /api/options/positions/intelligence.
// Each card explains:
//   * thesis health (single qualitative read)
//   * guidance action (hold / take_profit / stop_loss / roll / expiring / catalyst_caution)
//   * theta carry $/day
//   * IV expansion vs compression
//   * breakeven distance + spot relative to profit zone
//   * catalyst overlay (when one sits inside remaining DTE)
//   * per-leg structure
//
// Never renders raw greeks dashboards. Every metric paired with a
// one-line explanation surfaced from the server-side reason field.

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { fmtSignedUSD, fmtPct } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import OptionsBiasChip, { OptionsBias } from "./OptionsBiasChip";
import EducationalDrawer from "./EducationalDrawer";
import OptionsActionPills from "./OptionsActionPills";
import { OptionsShadowWatermark } from "./OptionsLiveStateChip";


export interface PositionLegPayload {
  leg_index: number;
  option_symbol: string;
  expiry?: string | null;
  strike: number;
  option_type: string;
  side: string;
  qty: number;
  entry_mid?: number | null;
  current_mid?: number | null;
  entry_iv?: number | null;
  current_iv?: number | null;
  current_delta?: number | null;
  current_theta?: number | null;
  current_vega?: number | null;
  quote_age_seconds?: number | null;
}


export interface PositionCatalystPayload {
  event_type: string;
  event_date: string;
  days_away: number;
  importance: string;
  title: string;
  explanation: string;
}


export interface PositionIntelligencePayload {
  trade_id: number;
  underlying: string;
  strategy_name: string;
  status: string;
  lifecycle_stage: string;
  opened_at: string | null;
  days_held: number;
  min_dte: number;
  legs: PositionLegPayload[];
  entry_credit_dollars: number | null;
  current_value_dollars: number | null;
  max_loss_dollars: number;
  max_profit_dollars: number;
  unrealized_pnl_dollars: number | null;
  unrealized_pnl_pct_vs_max: number | null;
  fees_total_dollars: number;
  breakeven_lower: number | null;
  breakeven_upper: number | null;
  spot_price: number | null;
  distance_to_breakeven_pct: number | null;
  theta_per_day_dollars: number | null;
  iv_change_pct: number | null;
  iv_change_label: string;
  delta_net: number | null;
  catalyst: PositionCatalystPayload | null;
  guidance: {
    action: string;
    label: string;
    reason: string;
  };
  thesis_health: string;
  thesis_health_reason: string | null;
  theta_impact_reason: string | null;
  iv_impact_reason: string | null;
  breakeven_reason: string | null;
  catalyst_reason: string | null;
}


function biasFromStrategy(s: string): OptionsBias {
  const u = (s || "").toUpperCase();
  if (u.includes("BULL")) return "bullish";
  if (u.includes("BEAR")) return "bearish";
  if (u.includes("IRON") || u.includes("CONDOR") || u.includes("STRANGLE")) return "neutral";
  if (u.includes("STRADDLE")) return "event";
  return "developing";
}


function strategyDisplayName(s: string): string {
  return (s || "Strategy")
    .replace(/_/g, " ").toLowerCase()
    .replace(/\b\w/g, c => c.toUpperCase());
}


function guidanceTone(action: string): "pos" | "neg" | "warn" | "neutral" {
  switch (action) {
    case "take_profit":       return "pos";
    case "stop_loss":         return "neg";
    case "expiring":          return "warn";
    case "catalyst_caution":  return "warn";
    case "roll":              return "warn";
    case "hold":              return "neutral";
    default:                  return "neutral";
  }
}


export default function OptionsPositionCard({
  item, canaryEnabled = false,
}: {
  item: PositionIntelligencePayload;
  canaryEnabled?: boolean;
}) {
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const bias = biasFromStrategy(item.strategy_name);
  const guideTone = guidanceTone(item.guidance.action);
  // H-refine: when every leg's current_mid is missing, the unrealized
  // metric derives from entry credit only and reads as a misleading
  // −100% vs max. Surface "Awaiting quote refresh" instead — honest.
  const allLegsStaleQuote =
    item.legs.length > 0
    && item.legs.every(l => l.current_mid == null);
  const showQuoteWaiting =
    allLegsStaleQuote
    || item.current_value_dollars == null
    || (item.unrealized_pnl_dollars == null);

  return (
    <article
      className="opt-pos-card"
      data-test="opt-position-card"
      data-bias={bias}
      data-guide-action={item.guidance.action}
    >
      {/* H.3 — curated position card. Four elements:
            1. headline    underlying + strategy
            2. sentence    guidance.reason (engine-rendered guidance, one line)
            3. metric      unrealized P&L oversized
            4. action      Explain + Open in Research (drawer holds all detail) */}

      {/* 1. headline */}
      <header className="opt-pos-head">
        <div className="opt-pos-symbol">
          {item.underlying}
          <OptionsShadowWatermark />
        </div>
        <span className={cn("opt-pos-guidance-pill",
                            `opt-pos-guidance-pill-${guideTone}`)}>
          {item.guidance.label}
        </span>
      </header>

      <div className="opt-pos-strategy-row">
        <Link
          to={`/options/learn/${item.strategy_name}`}
          className="opt-pos-strategy opt-pos-strategy-link"
          title="Open strategy playbook"
        >
          {strategyDisplayName(item.strategy_name)}
        </Link>
        <OptionsBiasChip bias={bias} size="xs" />
      </div>

      {/* 2. strategist sentence */}
      <p className="opt-pos-sentence">{item.guidance.reason}</p>

      {/* 3. dominant metric */}
      {showQuoteWaiting ? (
        <div className="opt-pos-metric opt-pos-metric-waiting"
             data-test="opt-pos-metric-waiting">
          <div className="opt-pos-metric-value">—</div>
          <div className="opt-pos-metric-label">Awaiting quote refresh</div>
        </div>
      ) : (
        <div className={cn("opt-pos-metric",
                            item.unrealized_pnl_dollars != null
                              && item.unrealized_pnl_dollars >= 0
                              ? "opt-pos-metric-pos"
                              : "opt-pos-metric-neg")}>
          <div className="opt-pos-metric-value">
            {fmtSignedUSD(item.unrealized_pnl_dollars as number)}
          </div>
          <div className="opt-pos-metric-label">
            unrealized
            {item.unrealized_pnl_pct_vs_max != null && (
              <> · {fmtPct(item.unrealized_pnl_pct_vs_max * 100, 0)} vs max</>
            )}
          </div>
        </div>
      )}

      {/* 4. action */}
      <OptionsActionPills
        onExplain={() => setDrawerOpen(true)}
        onOpenResearch={() => navigate(`/options/research/${item.underlying}`)}
        canaryEnabled={canaryEnabled} />

      <EducationalDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={`Manage ${strategyDisplayName(item.strategy_name)} on ${item.underlying}`}
        strategyName={item.strategy_name}
        whyStrategy={item.thesis_health_reason ?? null}
        whyExpiry={item.breakeven_reason ?? null}
        whatInvalidates={[
          item.guidance.action === "stop_loss"
            ? "Already at stop-loss threshold — close now."
            : "Spot breaches breakeven on the wrong side.",
          item.guidance.action === "expiring"
            ? "DTE ≤ 3 — pin-risk window. Close before expiry."
            : "DTE compression past 7 days — roll candidate window.",
        ]}
        thetaIvImpact={[
          item.theta_impact_reason ?? "",
          item.iv_impact_reason ?? "",
        ].filter(Boolean).join("\n\n") || null}
        catalystTitle={item.catalyst?.title ?? null}
        catalystDate={item.catalyst?.event_date ?? null}
        catalystDaysAway={item.catalyst?.days_away ?? null}
        catalystImportance={item.catalyst?.importance ?? null}
        catalystExplanation={item.catalyst?.explanation ?? null}
        footer={
          <span>
            Guidance: <code>{item.guidance.action}</code> ·{" "}
            Lifecycle: <code>{item.lifecycle_stage}</code>
          </span>
        } />
    </article>
  );
}
