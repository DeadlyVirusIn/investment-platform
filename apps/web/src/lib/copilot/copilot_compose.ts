// UX-11 Phase 11B — composer + PROOF fixtures.
//
// Source of truth: docs/research/UX_11_INTERACTIVE_COPILOT.md
//
// Pure function. Returns hero text + tile list. Phase 11G replaces
// fixtures with composer reading paper_position + recommendation +
// regime_snapshot + factor_snapshot.

import type { ConvictionTileData } from "./tile_schema";
import type { ActionCardData } from "./conviction_card_schema";

import { composeHeroFromGrammar, QUIET_DAY_HERO } from "./voice_composer";


export interface CopilotPageData {
  date: string;
  heroText: string;
  isQuiet: boolean;
  tiles: ConvictionTileData[];
  // Drawer data — keyed by ticker — full ActionCardData (UX-10 schema).
  // Drawer renders the SAME data UX-10 does, just with the UX-11 UI.
  drawerByTicker: Record<string, ActionCardData>;
}


function isoHoursAgo(hours: number): string {
  return new Date(Date.now() - hours * 3600_000).toISOString();
}


// PROOF tiles
const PROOF_TILES: ConvictionTileData[] = [
  {
    verb: "OPEN",
    ticker: "NVDA",
    thesisName: "Semis cycle continuation",
    decisionSentence:
      "Add through $172 while data-center margin expansion holds and hyperscaler capex stays above +18% YoY revisions.",
    confidenceTier: "Conviction",
    freshnessState: "Fresh",
    lastReviewedAt: isoHoursAgo(14),
    invalidationDistance: "Invalid < $158",
    horizon: "~6w",
    bullClause: "Capex +22% YoY",
    bearClause: "Hyperscaler rollover risk",
  },
  {
    verb: "TRIM",
    ticker: "TSLA",
    thesisName: "Cybertruck + energy",
    decisionSentence:
      "Take 30% off Tesla after the +18% run; upside-to-target compressed and event risk rising into delivery numbers.",
    confidenceTier: "Confirmed",
    freshnessState: "Aging",
    lastReviewedAt: isoHoursAgo(36),
    invalidationDistance: "Invalid > $260 vol-up",
    horizon: "9-18mo",
    bullClause: "Energy storage margins",
    bearClause: "China BYD share loss",
  },
  {
    verb: "HOLD",
    ticker: "MSFT",
    thesisName: "Cloud durability + leverage",
    decisionSentence:
      "Stay in Microsoft above $415 while Azure growth holds above 25% and operating margin keeps expanding into FY Q4.",
    confidenceTier: "Confirmed",
    freshnessState: "Fresh",
    lastReviewedAt: isoHoursAgo(11),
    invalidationDistance: "Invalid < $395",
    horizon: "6-18mo",
    bullClause: "Margin expansion durable",
    bearClause: "AI capex / ROI gap",
  },
];


// Drawer data — UX-10 ActionCardData per ticker. Drawer reuses
// the UX-10 schema unchanged (Section 14 inheritance).
const DRAWER_NVDA: ActionCardData = {
  verb: "OPEN",
  ticker: "NVDA",
  thesisName: "Semis cycle continuation",
  decisionSentence:
    "Add through $172 while data-center margin expansion holds and hyperscaler capex revisions stay above +18% YoY.",
  confidenceTier: "Conviction",
  freshnessState: "Fresh",
  lastReviewedAt: isoHoursAgo(14),
  expiryCondition: "earnings May 21 or close below $158",
  invalidation:
    "Close below $158 on > 1.4× ADV, OR hyperscaler capex revision below +18% YoY, OR QQQ regime break below 200MA.",
  thesis: {
    driver:
      "Semiconductor revisions still pointing up post-Q1. Institutional inflows added $2.1B over 5d and IV is compressing into earnings. Data-center margin expansion has visibility through 2026 with the cluster of recent capex commitments.",
    counter:
      "Valuation stretched at ~38x forward; cyclical reversal risk real if hyperscaler capex normalizes. China export restrictions ignored as tail risk for two quarters and could re-emerge. Semi cycles historically end abruptly without preparation.",
    catalyst: "Watching post-earnings reaction May 21; gap-up = invalidates short bears, gap-down = re-tests $158.",
  },
  target: { entry: "$172–$185", t1: "$208", t2: "$222", t3: "$245" },
  horizon: "6 weeks – 6 months",
  bearCaseGlyph: true,
  snoozeOptions: ["24h", "1w", "forever"],
  riskTags: ["Cyclical risk", "Valuation risk", "China export risk"],
};


const DRAWER_TSLA: ActionCardData = {
  verb: "TRIM",
  ticker: "TSLA",
  thesisName: "Cybertruck + energy + FSD",
  decisionSentence:
    "Take 30% off Tesla after the +18% run; the upside-to-target is compressed and event risk is rising into delivery numbers.",
  confidenceTier: "Confirmed",
  freshnessState: "Aging",
  lastReviewedAt: isoHoursAgo(36),
  expiryCondition: "Q2 delivery release on July 2 or close above $260",
  invalidation:
    "Close above $260 with rising volume invalidates the trim; close below $215 invalidates the upside thesis entirely.",
  thesis: {
    driver:
      "Energy storage gross margin is the genuinely good story; deliveries continue to disappoint but the auto business is no longer the locomotive. FSD V12 transition is a real product milestone with optionality.",
    counter:
      "Auto demand softening, China share losses, brand damage from political exposure. The +18% run was sentiment-driven, not earnings-driven; reversion risk is high. China BYD remains a structural threat to the auto thesis.",
    catalyst: "Q2 delivery release will reset positioning in either direction.",
  },
  target: { entry: "trim 30%", t1: "$255", t2: "$280" },
  horizon: "9–18 months",
  bearCaseGlyph: true,
  snoozeOptions: ["24h", "1w", "forever"],
  riskTags: ["Demand risk", "China competition", "Sentiment-driven"],
};


const DRAWER_MSFT: ActionCardData = {
  verb: "HOLD",
  ticker: "MSFT",
  thesisName: "Cloud durability + operating leverage",
  decisionSentence:
    "Stay in Microsoft above $415 while Azure growth holds above 25% and operating margin keeps expanding.",
  confidenceTier: "Confirmed",
  freshnessState: "Fresh",
  lastReviewedAt: isoHoursAgo(11),
  expiryCondition: "FY Q4 earnings or close below $395",
  invalidation:
    "Azure growth decelerates below 25% YoY, OR operating margin compresses two consecutive quarters, OR close below $395.",
  thesis: {
    driver:
      "Cloud durability and AI capex absorption creating multi-quarter operating leverage story. Hyperscaler peers reporting capex revisions up; MSFT commercial cloud bookings ran ahead in two quarters. Gross margin trend positive despite AI infrastructure spend.",
    counter:
      "Valuation full at ~33x forward earnings; AI capex risk real if monetization slips. Enterprise IT spend decelerating broadly. Miss on Azure growth or operating margin is the obvious downside catalyst — both are crowded estimates.",
    catalyst: "Watching Azure growth color and capex commentary at FY Q4 earnings.",
  },
  target: { entry: "$415", t1: "$445", t2: "$475" },
  horizon: "6–18 months",
  bearCaseGlyph: true,
  snoozeOptions: ["24h", "1w", "forever"],
  riskTags: ["Valuation risk", "AI capex risk"],
};


export interface ComposeInputs {
  forceQuiet?: boolean;
}


export function composeCopilotPage(inp: ComposeInputs = {}): CopilotPageData {
  const date = new Date().toLocaleDateString("en-US", {
    weekday: "long", month: "long", day: "numeric",
  });

  if (inp.forceQuiet) {
    return {
      date,
      heroText: QUIET_DAY_HERO,
      isQuiet: true,
      tiles: [],
      drawerByTicker: {},
    };
  }

  // Wrap voice composition so a lint failure in fixtures does NOT
  // blank-page the route. Real engine wiring (11G) will mean a
  // composer-side throw, not a UI-side throw — but during fixture
  // iteration, fail-safe to the locked quiet-day copy.
  let heroText: string;
  try {
    heroText = composeHeroFromGrammar({
      stanceVerb: "is becoming more selective",
      qualifier: "after this rally",
      consequence: "Add only where earnings durability offsets valuation risk",
    });
  } catch (e) {
    console.warn("[ux11] hero composition failed; falling back to quiet copy", e);
    heroText = QUIET_DAY_HERO;
  }

  return {
    date,
    heroText,
    isQuiet: false,
    tiles: PROOF_TILES,
    drawerByTicker: {
      NVDA: DRAWER_NVDA,
      TSLA: DRAWER_TSLA,
      MSFT: DRAWER_MSFT,
    },
  };
}
