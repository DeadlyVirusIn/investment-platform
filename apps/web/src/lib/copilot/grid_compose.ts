// UX-9 Phase 9C — Intelligence Grid composer.
//
// Pure function. Returns IntelligenceGridProps with realistic
// fixture content for the visual proof.

import type {
  IntelligenceGridProps, SlotData, SlotName,
} from "@/components/copilot/IntelligenceGrid";


export interface GridComposeInputs {
  override?: Partial<Record<SlotName, Partial<SlotData>>>;
}


export function composeGrid(inp: GridComposeInputs = {}): IntelligenceGridProps {
  const slots: Record<SlotName, SlotData> = {
    "OPPORTUNITY": {
      primary: "3 ideas worth watching today.",
      ai: "Two in tech: AAPL, MSFT.",
      sparkline: [1, 2, 3, 4, 5, 7, 6, 8],
      isQuiet: false,
      isChanged: true,
    },
    "WHAT CHANGED": {
      primary: "Tech rotation accelerated overnight.",
      ai: "+2 new ideas since last visit.",
      sparkline: [6, 4, 2, 1, 2, 3, 5, 7],
      isQuiet: false,
      isChanged: true,
    },
    "WATCHLIST": {
      primary: "META · NFLX both warming.",
      ai: "Since Tuesday's open.",
      sparkline: [2, 4, 3, 5, 7, 8],
      isQuiet: false,
      isChanged: false,
    },
    "CATALYSTS THIS WEEK": {
      primary: "Earnings: AAPL Thu, MSFT Wed.",
      ai: "Fed minutes Wed.",
      isQuiet: false,
      isChanged: false,
    },
    "RISK": {
      primary: "Tech concentration: 64%.",
      ai: "Within range. No new exposures.",
      isQuiet: false,
      isChanged: false,
    },
    "YOUR DAY": {
      primary: "2 new ideas, 1 near target.",
      ai: "Nothing else pressing.",
      isQuiet: false,
      isChanged: false,
    },
  };

  // Apply overrides if provided.
  if (inp.override) {
    for (const [name, patch] of Object.entries(inp.override) as [SlotName, Partial<SlotData>][]) {
      slots[name] = { ...slots[name], ...patch };
    }
  }

  return { slots };
}


/** Quiet-day variants per slot. Observational, NOT reassurance.
 *  Used when the engine has no content for that slot today. */
export const QUIET_VARIANTS: Record<SlotName, SlotData> = {
  "OPPORTUNITY": {
    primary: "No new ideas today.", isQuiet: true, isChanged: false,
  },
  "WHAT CHANGED": {
    primary: "Today looks like yesterday.", isQuiet: true, isChanged: false,
  },
  "WATCHLIST": {
    primary: "Watchlist quiet.", isQuiet: true, isChanged: false,
  },
  "CATALYSTS THIS WEEK": {
    primary: "No catalysts this week.", isQuiet: true, isChanged: false,
  },
  "RISK": {
    primary: "No new exposures.", isQuiet: true, isChanged: false,
  },
  "YOUR DAY": {
    primary: "Nothing pressing today.", isQuiet: true, isChanged: false,
  },
};
