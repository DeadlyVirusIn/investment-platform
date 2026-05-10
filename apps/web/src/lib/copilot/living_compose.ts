// UX-13 Living Environment composer + PROOF fixtures.
//
// VISUAL HYPOTHESIS — not final truth.
//
// Source of truth: docs/research/UX_13_LIVING_ENVIRONMENT.md
// Inherits UX-12 substrate, UX-11 ConvictionTile schema, UX-10 ActionCardData.
//
// Three rooms (Solo / Duet / Field) chosen at session-load by AI's
// editorial read. URL ?room=solo|duet|field forces a room for visual
// validation. ?glyph=off kills verb-glyph (Codex R4 kill-trigger).

import type { ConvictionTileData } from "./tile_schema";
import type { ActionCardData } from "./conviction_card_schema";


export type RoomMode = "solo" | "duet" | "field";


export interface LivingPageData {
  room: RoomMode;
  date: string;
  ambientTime: string;          // "as of 09:24, market 41 min in"
  pageStateText: string;        // "3 to look at" / "Quiet morning"
  postureText: string;          // 36pt serif sentence (mode signature)
  sinceYouLeftText: string | null;  // "Since 09:18 yesterday: NVDA conviction +0.3"
  heroTile: ConvictionTileData | null;     // null in Field
  subordinateTiles: ConvictionTileData[];  // 0 in Solo, 1-2 in Duet, 4-6 in Field
  watchlistRows: WatchlistRow[];           // empty in Field; column in Duet; single line in Solo
  marketContextText: string;
  /** Operational layer — events the AI generated since user's last visit. */
  activity: ActivityEvent[];
  /** Operational meta cluster — "5 active · 12 watch · 3 new" */
  totals: { active: number; watch: number; newToday: number };
  /** Conviction trajectory keyed by ticker (drives sparklines). */
  conviction: Record<string, ConvictionSeries>;
  /** Pressure direction keyed by ticker. */
  pressure: Record<string, PressureDirection>;
  /** Upcoming catalysts (already filtered to relevance for this room). */
  catalysts: Catalyst[];
  /** Current market pulse. */
  marketPulse: MarketPulse;
}


export interface WatchlistRow {
  ticker: string;
  status: string;
}


/** Conviction trajectory — last N snapshots, normalized 0-1.
 *  Drives the inline sparkline. */
export type ConvictionSeries = number[];   // 7-12 points typically


/** Pressure direction — directional momentum since last review. */
export type PressureDirection = "strengthening" | "weakening" | "stable";


/** Catalyst — upcoming event affecting a thesis. */
export interface Catalyst {
  ticker: string;
  label: string;        // "Q4 earnings", "Fed minutes", "FOMC"
  daysAway: number;     // 0 = today
  hoursAway?: number;   // optional finer grain
}


/** Market pulse — single state of the broad tape. */
export interface MarketPulse {
  state: "risk-on" | "neutral" | "defensive" | "stressed";
  label: string;        // "Risk-on tape · semis leading"
}


/** AI activity event — proves AI was working while user was away. */
export interface ActivityEvent {
  /** Stable ID for React keys */
  id: string;
  /** Ticker the event is about (clickable → opens drawer) */
  ticker: string;
  /** Event type — drives icon glyph + color emphasis */
  type:
    | "conviction-up"     // tier promoted
    | "conviction-down"   // tier demoted
    | "thesis-strengthen" // bull case strengthened
    | "thesis-weaken"     // bear case strengthened
    | "catalyst-approach" // event in N days
    | "watchlist-warm"    // watchlist item warming
    | "review-stale";     // freshness aged
  /** Hours ago this happened (for relative time display) */
  hoursAgo: number;
  /** Compact one-line description */
  text: string;
}


function isoHoursAgo(hours: number): string {
  return new Date(Date.now() - hours * 3600_000).toISOString();
}


// PROOF tiles — UX-11 ConvictionTileData schema preserved
const PROOF_HERO_NVDA: ConvictionTileData = {
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
};


const PROOF_SUB_TSLA: ConvictionTileData = {
  verb: "TRIM",
  ticker: "TSLA",
  thesisName: "Cybertruck + energy",
  decisionSentence:
    "Take 30% off Tesla after the +18% run; upside-to-target compressed and event risk rising into delivery numbers.",
  confidenceTier: "Confirmed",
  freshnessState: "Aging",
  lastReviewedAt: isoHoursAgo(36),
  invalidationDistance: "Invalid > $260",
  horizon: "9-18mo",
  bullClause: "Energy storage margins",
  bearClause: "China BYD share loss",
};


const PROOF_SUB_MSFT: ConvictionTileData = {
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
};


// Field-mode 4-6 lower-tier theses (Working / Forming)
const PROOF_FIELD_TILES: ConvictionTileData[] = [
  {
    verb: "HOLD",
    ticker: "AAPL",
    thesisName: "Services growth ramp",
    decisionSentence:
      "Hold Apple while Services revenue mix continues climbing toward 28% of total and gross margins stabilize.",
    confidenceTier: "Working",
    freshnessState: "Fresh",
    lastReviewedAt: isoHoursAgo(4),
    invalidationDistance: "Invalid < $182",
    horizon: "12-24mo",
  },
  {
    verb: "HOLD",
    ticker: "AMZN",
    thesisName: "AWS reacceleration cycle",
    decisionSentence:
      "Hold Amazon as AWS reaccelerates and retail operating leverage continues into the back half of the year.",
    confidenceTier: "Working",
    freshnessState: "Aging",
    lastReviewedAt: isoHoursAgo(28),
    invalidationDistance: "Invalid < $172",
    horizon: "12mo",
  },
  {
    verb: "HOLD",
    ticker: "GOOG",
    thesisName: "Search durability",
    decisionSentence:
      "Hold Alphabet while Search ad revenue durability holds and Cloud margin trajectory continues improving sequentially.",
    confidenceTier: "Forming",
    freshnessState: "Fresh",
    lastReviewedAt: isoHoursAgo(8),
    invalidationDistance: "Invalid < $148",
    horizon: "12-18mo",
  },
  {
    verb: "HOLD",
    ticker: "META",
    thesisName: "Reels monetization",
    decisionSentence:
      "Hold Meta as Reels monetization improves and capex discipline emerges from the AI infrastructure buildout.",
    confidenceTier: "Forming",
    freshnessState: "Aging",
    lastReviewedAt: isoHoursAgo(40),
    invalidationDistance: "Invalid < $480",
    horizon: "6-12mo",
  },
  {
    verb: "HOLD",
    ticker: "AVGO",
    thesisName: "Custom silicon ramp",
    decisionSentence:
      "Hold Broadcom while custom AI silicon revenue ramps and VMware integration produces operating leverage.",
    confidenceTier: "Forming",
    freshnessState: "Fresh",
    lastReviewedAt: isoHoursAgo(6),
    invalidationDistance: "Invalid < $1,520",
    horizon: "12mo",
  },
];


function clockNow(): string {
  return new Date().toLocaleTimeString("en-US", {
    hour: "2-digit", minute: "2-digit", hour12: false,
  });
}


function dateNow(): string {
  return new Date().toLocaleDateString("en-US", {
    weekday: "long", month: "long", day: "numeric",
  });
}


/** Compose page data based on room mode (force-state via ?room=). */
export function composeLivingPage(forcedRoom: RoomMode): LivingPageData {
  const ambientTime = `as of ${clockNow()} · market 41 min in`;
  const sinceYouLeftText = "Since 09:18 yesterday: NVDA conviction +0.3";

  switch (forcedRoom) {
    case "solo":
      return {
        room: "solo",
        date: dateNow(),
        ambientTime,
        pageStateText: "1 to look at",
        postureText: "One thesis stands alone today.",
        sinceYouLeftText,
        heroTile: PROOF_HERO_NVDA,
        subordinateTiles: [],
        watchlistRows: [],
        marketContextText: "Risk-on tape; semis leading the market into the close.",
        activity: [
          { id: "a1", ticker: "NVDA", type: "conviction-up", hoursAgo: 14, text: "Conviction +0.3 → 0.82" },
          { id: "a2", ticker: "NVDA", type: "thesis-strengthen", hoursAgo: 11, text: "Bull case deepened on capex revisions" },
          { id: "a3", ticker: "NVDA", type: "catalyst-approach", hoursAgo: 0, text: "Earnings in 12 days" },
        ],
        totals: { active: 1, watch: 4, newToday: 1 },
        conviction: {
          NVDA: [0.45, 0.50, 0.55, 0.62, 0.70, 0.78, 0.82],
        },
        pressure: { NVDA: "strengthening" },
        catalysts: [
          { ticker: "NVDA", label: "Q1 earnings", daysAway: 12, hoursAway: 6 },
        ],
        marketPulse: { state: "risk-on", label: "Risk-on tape · semis leading" },
      };

    case "duet":
      return {
        room: "duet",
        date: dateNow(),
        ambientTime,
        pageStateText: "3 to look at",
        postureText: "Two theses, one challenger.",
        sinceYouLeftText,
        heroTile: PROOF_HERO_NVDA,
        subordinateTiles: [PROOF_SUB_TSLA, PROOF_SUB_MSFT],
        watchlistRows: [
          { ticker: "AAPL", status: "near $172" },
          { ticker: "TSM", status: "warming" },
          { ticker: "COST", status: "slowing" },
        ],
        marketContextText: "Risk-on tape; semis leading. VIX 14, oil firm. Fed Wed.",
        activity: [
          { id: "a1", ticker: "NVDA", type: "conviction-up", hoursAgo: 14, text: "Conviction +0.3 → 0.82" },
          { id: "a2", ticker: "TSLA", type: "thesis-weaken", hoursAgo: 8, text: "Bear case deepened — China BYD share loss" },
          { id: "a3", ticker: "COST", type: "conviction-up", hoursAgo: 6, text: "Tier promoted to Confirmed" },
          { id: "a4", ticker: "TSM", type: "watchlist-warm", hoursAgo: 4, text: "Approaching entry zone" },
          { id: "a5", ticker: "MSFT", type: "catalyst-approach", hoursAgo: 0, text: "FY Q4 earnings in 8 days" },
        ],
        totals: { active: 3, watch: 12, newToday: 2 },
        conviction: {
          NVDA: [0.45, 0.50, 0.55, 0.62, 0.70, 0.78, 0.82],
          TSLA: [0.78, 0.76, 0.72, 0.70, 0.66, 0.62, 0.55],
          MSFT: [0.65, 0.66, 0.68, 0.69, 0.70, 0.71, 0.72],
        },
        pressure: {
          NVDA: "strengthening",
          TSLA: "weakening",
          MSFT: "stable",
        },
        catalysts: [
          { ticker: "MSFT", label: "FY Q4 earnings", daysAway: 8, hoursAway: 14 },
          { ticker: "TSLA", label: "Q2 deliveries", daysAway: 24, hoursAway: 6 },
          { ticker: "MARKET", label: "Fed minutes", daysAway: 1, hoursAway: 4 },
        ],
        marketPulse: { state: "risk-on", label: "Risk-on tape · semis leading" },
      };

    case "field":
      return {
        room: "field",
        date: dateNow(),
        ambientTime,
        pageStateText: "Five forming",
        postureText: "Five theses forming. None resolved.",
        sinceYouLeftText: "Since you left: nothing changed.",
        heroTile: null,
        subordinateTiles: PROOF_FIELD_TILES,
        watchlistRows: [],
        marketContextText: "Range-bound tape; conviction thin. Watching for resolution into earnings season.",
        activity: [
          { id: "a1", ticker: "AAPL", type: "review-stale", hoursAgo: 28, text: "Last review aging" },
          { id: "a2", ticker: "AMZN", type: "watchlist-warm", hoursAgo: 12, text: "AWS reaccel data point" },
          { id: "a3", ticker: "GOOG", type: "thesis-strengthen", hoursAgo: 8, text: "Cloud margin trajectory improving" },
          { id: "a4", ticker: "META", type: "thesis-weaken", hoursAgo: 18, text: "Capex discipline unclear" },
          { id: "a5", ticker: "AVGO", type: "watchlist-warm", hoursAgo: 6, text: "Custom silicon ramp signal" },
        ],
        totals: { active: 0, watch: 18, newToday: 5 },
        conviction: {
          AAPL: [0.55, 0.55, 0.54, 0.54, 0.53, 0.52, 0.52],
          AMZN: [0.48, 0.50, 0.51, 0.52, 0.54, 0.55, 0.57],
          GOOG: [0.46, 0.48, 0.50, 0.52, 0.54, 0.56, 0.58],
          META: [0.65, 0.62, 0.60, 0.58, 0.55, 0.52, 0.50],
          AVGO: [0.42, 0.44, 0.46, 0.48, 0.50, 0.52, 0.54],
        },
        pressure: {
          AAPL: "stable",
          AMZN: "strengthening",
          GOOG: "strengthening",
          META: "weakening",
          AVGO: "strengthening",
        },
        catalysts: [
          { ticker: "MARKET", label: "CPI release", daysAway: 5, hoursAway: 12 },
          { ticker: "MARKET", label: "Earnings season opens", daysAway: 14, hoursAway: 0 },
        ],
        marketPulse: { state: "neutral", label: "Range-bound · waiting for resolution" },
      };
  }
}


/** Drawer payload — UX-10 ActionCardData per ticker. Reused from UX-11. */
export const PROOF_DRAWER_PAYLOADS: Record<string, ActionCardData> = {
  NVDA: {
    verb: "OPEN", ticker: "NVDA", thesisName: "Semis cycle continuation",
    decisionSentence:
      "Add through $172 while data-center margin expansion holds and hyperscaler capex revisions stay above +18% YoY.",
    confidenceTier: "Conviction", freshnessState: "Fresh",
    lastReviewedAt: isoHoursAgo(14),
    expiryCondition: "earnings May 21 or close below $158",
    invalidation:
      "Close below $158 on > 1.4× ADV, OR hyperscaler capex revision below +18% YoY, OR QQQ regime break below 200MA.",
    thesis: {
      driver:
        "Semiconductor revisions still pointing up post-Q1. Institutional inflows added $2.1B over 5d and IV is compressing into earnings. Data-center margin expansion has visibility through 2026.",
      counter:
        "Valuation stretched at ~38x forward; cyclical reversal risk real if hyperscaler capex normalizes. China export restrictions ignored as tail risk for two quarters.",
      catalyst: "Watching post-earnings reaction May 21.",
    },
    target: { entry: "$172–$185", t1: "$208", t2: "$222", t3: "$245" },
    horizon: "6 weeks – 6 months",
    bearCaseGlyph: true,
    snoozeOptions: ["24h", "1w", "forever"],
    riskTags: ["Cyclical risk", "Valuation risk", "China export risk"],
  },
  TSLA: {
    verb: "TRIM", ticker: "TSLA", thesisName: "Cybertruck + energy + FSD",
    decisionSentence: "Take 30% off Tesla after the +18% run; upside-to-target is compressed and event risk is rising.",
    confidenceTier: "Confirmed", freshnessState: "Aging",
    lastReviewedAt: isoHoursAgo(36),
    expiryCondition: "Q2 delivery release on July 2 or close above $260",
    invalidation:
      "Close above $260 with rising volume invalidates the trim; close below $215 invalidates the upside thesis.",
    thesis: {
      driver: "Energy storage gross margin is the genuinely good story; deliveries continue to disappoint but auto business is no longer the locomotive. FSD V12 transition is a real product milestone with optionality.",
      counter: "Auto demand softening, China share losses, brand damage. The +18% run was sentiment-driven, not earnings-driven; reversion risk is high.",
      catalyst: "Q2 delivery release will reset positioning in either direction.",
    },
    target: { entry: "trim 30%", t1: "$255", t2: "$280" },
    horizon: "9–18 months",
    bearCaseGlyph: true,
    snoozeOptions: ["24h", "1w", "forever"],
    riskTags: ["Demand risk", "China competition", "Sentiment-driven"],
  },
  MSFT: {
    verb: "HOLD", ticker: "MSFT", thesisName: "Cloud durability + operating leverage",
    decisionSentence: "Stay in Microsoft above $415 while Azure growth holds above 25% and operating margin keeps expanding.",
    confidenceTier: "Confirmed", freshnessState: "Fresh",
    lastReviewedAt: isoHoursAgo(11),
    expiryCondition: "FY Q4 earnings or close below $395",
    invalidation:
      "Azure growth decelerates below 25% YoY, OR operating margin compresses two consecutive quarters, OR close below $395.",
    thesis: {
      driver: "Cloud durability and AI capex absorption creating multi-quarter operating leverage story. MSFT commercial cloud bookings ran ahead in two quarters.",
      counter: "Valuation full at ~33x forward earnings; AI capex risk real if monetization slips. Enterprise IT spend decelerating broadly.",
      catalyst: "Watching Azure growth color and capex commentary at FY Q4 earnings.",
    },
    target: { entry: "$415", t1: "$445", t2: "$475" },
    horizon: "6–18 months",
    bearCaseGlyph: true,
    snoozeOptions: ["24h", "1w", "forever"],
    riskTags: ["Valuation risk", "AI capex risk"],
  },
};
