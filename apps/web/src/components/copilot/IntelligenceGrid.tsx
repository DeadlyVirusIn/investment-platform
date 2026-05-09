// UX-9 Phase 9B — Intelligence Grid.
//
// 6 named fixed slots in a 2×3 layout. Slot positions NEVER
// move. Only contents update daily. Quiet-day variants use
// observational copy, not reassurance prose.
//
// State-change emphasis: when a card's `isChanged` flag is
// true, a 2px left-edge bar fires the scaleY entrance animation
// (CSS keyframe). Reduced-motion strips it.

import Sparkline from "./Sparkline";


export type SlotName =
  | "OPPORTUNITY"
  | "WHAT CHANGED"
  | "WATCHLIST"
  | "CATALYSTS THIS WEEK"
  | "RISK"
  | "YOUR DAY";


export interface SlotData {
  /** Primary user-facing line (≤ 80 chars). */
  primary: string;
  /** Optional secondary AI interpretation line. */
  ai?: string;
  /** Optional 4-32 point sparkline series. */
  sparkline?: number[];
  /** Quiet variant — content is the calm/observational form. */
  isQuiet: boolean;
  /** Has this slot's content changed since the user's last
   *  visit? Triggers the left-edge state-change emphasis. */
  isChanged: boolean;
}


export interface IntelligenceGridProps {
  slots: Record<SlotName, SlotData>;
  /** Per-card admin lineage (used by overlay tooltip). */
  onCardHover?: (slot: SlotName, anchor: HTMLElement) => void;
}


// Locked slot order. Reading flow: hero → opportunity → what
// changed → watchlist → catalysts → risk → your day.
export const SLOT_ORDER: SlotName[] = [
  "OPPORTUNITY",
  "WHAT CHANGED",
  "WATCHLIST",
  "CATALYSTS THIS WEEK",
  "RISK",
  "YOUR DAY",
];


export default function IntelligenceGrid(
  { slots, onCardHover }: IntelligenceGridProps,
) {
  return (
    <section className="ux9-grid" data-test="ux9-grid">
      {SLOT_ORDER.map((name) => {
        const d = slots[name];
        return (
          <article
            key={name}
            className="ux9-card"
            data-slot={name}
            data-quiet={d.isQuiet ? "true" : "false"}
            data-changed={d.isChanged ? "true" : "false"}
            data-test="ux9-card"
            onMouseEnter={(e) => onCardHover?.(name, e.currentTarget)}
          >
            <h3 className="ux9-card-header">{name}</h3>
            <p className="ux9-card-primary">{d.primary}</p>
            {d.sparkline && d.sparkline.length >= 2 && (
              <Sparkline
                points={d.sparkline}
                className="ux9-card-sparkline"
              />
            )}
            {d.ai && <p className="ux9-card-ai">{d.ai}</p>}
          </article>
        );
      })}
    </section>
  );
}
