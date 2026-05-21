// OpportunityLane — single lane (e.g. Bullish) of opportunity cards.
//
// Pure rendering. Parent passes the lane name + items. Honest empty
// states: when no signals exist in this lane, render a calm one-line
// explanation rather than hiding the lane entirely. Hidden lanes feel
// like missing data; calm empties feel like the strategist's voice.

import OptionsOpportunityCard, {
  OpportunityPayload,
} from "./OptionsOpportunityCard";
import OptionsBiasChip, { OptionsBias } from "./OptionsBiasChip";


export type LaneName =
  | "bullish" | "bearish" | "neutral"
  | "event"   | "developing" | "conviction";

const LANE_COPY: Record<LaneName, { label: string; sub: string }> = {
  bullish:    { label: "Bullish",       sub: "Setups expecting price ↑" },
  bearish:    { label: "Bearish",       sub: "Setups expecting price ↓" },
  neutral:    { label: "Neutral / Income", sub: "Range-bound time-decay plays" },
  event:      { label: "Event-driven",  sub: "Earnings & catalyst windows" },
  developing: { label: "Developing",    sub: "Setups forming — below the gate floor" },
  conviction: { label: "High conviction", sub: "Cross-lane top composite ≥ 0.78" },
};

const EMPTY_COPY: Record<LaneName, string> = {
  bullish:    "We don't have a bullish recommendation today.",
  bearish:    "We don't have a bearish recommendation today.",
  neutral:    "No range-bound setups fit today — the premium environment isn't right.",
  event:      "No catalysts sit inside the typical DTE window right now.",
  developing: "Nothing's forming yet. We're watching.",
  conviction: "Nothing has cleared our high-conviction bar today. We'd rather wait.",
};


export interface OpportunityLaneProps {
  lane: LaneName;
  items: OpportunityPayload[];
  canaryEnabled?: boolean;
  /** Optional: cap items rendered in this lane. */
  limit?: number;
  /** Optional: lane header is collapsible. Defaults open. */
  collapsible?: boolean;
}


export default function OpportunityLane({
  lane, items, canaryEnabled = false, limit, collapsible = false,
}: OpportunityLaneProps) {
  const copy = LANE_COPY[lane];
  const visible = limit ? items.slice(0, limit) : items;

  return (
    <section
      className="opt-lane"
      data-lane={lane}
      data-test={`opt-lane-${lane}`}
    >
      <header className="opt-lane-header">
        <div className="opt-lane-title">
          <OptionsBiasChip bias={lane as OptionsBias} size="sm" />
          <h3 className="opt-lane-name">{copy.label}</h3>
          <span className="opt-lane-count">
            {items.length} signal{items.length === 1 ? "" : "s"}
          </span>
        </div>
        <span className="opt-lane-sub">{copy.sub}</span>
      </header>

      {visible.length === 0 ? (
        <div className="opt-lane-empty" data-test={`opt-lane-empty-${lane}`}>
          <span className="opt-caption-muted">{EMPTY_COPY[lane]}</span>
        </div>
      ) : (
        <div className="opt-lane-cards">
          {visible.map(item => (
            <OptionsOpportunityCard
              key={String(item.observation_id)}
              item={item}
              canaryEnabled={canaryEnabled} />
          ))}
        </div>
      )}
      {/* If we'd limited the lane, surface the overflow count honestly. */}
      {limit && items.length > limit && (
        <div className="opt-lane-overflow">
          <span className="opt-caption-muted">
            {items.length - limit} more setup{items.length - limit === 1 ? "" : "s"} below the visible cut. Adjust limit to see all.
          </span>
        </div>
      )}
      {collapsible && null}
    </section>
  );
}
