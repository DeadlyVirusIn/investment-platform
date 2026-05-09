// UX-10 Phase 10C — ConvictionHero composer + PROOF fixtures.
//
// Source of truth: docs/research/UX_10_CONVICTION_ENGINE.md
//   Section 6 (Overview hero rules)
//
// Pure function. Returns hero data with realistic fixtures for
// the visual proof. Phase 10G replaces fixtures with composer
// reading paper_position + recommendation + regime_snapshot.

import type { ActionCardData } from "./conviction_card_schema";


export interface ConvictionHeroData {
  date: string;                 // Friday May 9 etc
  regime: {
    stance: string;             // "Selective, valuation-sensitive"
    clause: string;             // one supporting sentence
  };
  activePositions: ActionCardData[];   // existing holdings; max 3
  promotions: ActionCardData[];        // new since last visit; max 2
  isQuiet: boolean;
  quietCopy?: string;
}


function isoHoursAgo(hours: number): string {
  return new Date(Date.now() - hours * 3600_000).toISOString();
}


/** PROOF fixtures — replaced in 10G with real composer. */
const PROOF_HOLD_MSFT: ActionCardData = {
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
      "Cloud durability and AI capex absorption are creating a multi-quarter operating leverage story. Hyperscaler peers are reporting capex revisions up; MSFT's commercial cloud bookings ran ahead of the model in the last two quarters and the gross margin trend is positive despite AI infrastructure spend.",
    counter:
      "Valuation is full at ~33x forward earnings; AI capex risk is real if monetization slips. Enterprise IT spend is decelerating broadly. A miss on Azure growth or operating margin is the obvious downside catalyst — both are crowded estimates.",
    catalyst: "Watching Azure growth color and capex commentary at FY Q4 earnings.",
  },
  target: { entry: "$415", t1: "$445", t2: "$475" },
  horizon: "6–18 months",
  bearCaseGlyph: true,
  snoozeOptions: ["24h", "1w", "forever"],
  riskTags: ["Valuation risk", "AI capex risk"],
};


const PROOF_TRIM_TSLA: ActionCardData = {
  verb: "TRIM",
  ticker: "TSLA",
  thesisName: "Cybertruck + energy + FSD optionality",
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
      "Auto demand softening, China share losses, and brand damage from political exposure. The +18% run was sentiment-driven, not earnings-driven; reversion risk is high. China BYD remains a structural threat to the auto thesis.",
    catalyst: "Q2 delivery release will reset positioning in either direction.",
  },
  target: { entry: "trim 30%", t1: "$255", t2: "$280" },
  horizon: "9–18 months",
  bearCaseGlyph: true,
  snoozeOptions: ["24h", "1w", "forever"],
  riskTags: ["Demand risk", "China competition", "Sentiment-driven"],
};


const PROOF_EXIT_META: ActionCardData = {
  verb: "EXIT",
  ticker: "META",
  thesisName: "Reels monetization + AI infra leverage",
  decisionSentence:
    "Close Meta fully — the AI infrastructure story is now in the price and the next leg requires capex discipline that may not arrive.",
  confidenceTier: "Working",
  freshnessState: "Fresh",
  lastReviewedAt: isoHoursAgo(4),
  expiryCondition: "Q2 capex guide or close above $612",
  invalidation:
    "Close above $612 invalidates the exit; capex guide below 2026 consensus invalidates the bear case.",
  thesis: {
    driver:
      "Reels monetization story has played out and is now in consensus numbers. AI infrastructure capex is rising sharply with no clear monetization path beyond compute leverage on existing ad surface.",
    counter:
      "Capex discipline could re-rate the stock if Zuck pivots from 'spend whatever' to 'show me the AI ROI.' That pivot has happened twice before in META history. Reasonable people disagree on whether it happens this cycle.",
    catalyst: "Q2 capex guide will define the next 6-month tape.",
  },
  target: { entry: "exit at market", t1: "rebuy below $480", t2: "watch $440 zone" },
  horizon: "3–9 months",
  bearCaseGlyph: true,
  snoozeOptions: ["24h", "1w", "forever"],
  riskTags: ["Capex discipline reversal", "Crowded short risk"],
};


const PROOF_OPEN_NVDA: ActionCardData = {
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
      "Semiconductor revisions are still pointing up post-Q1 earnings season. Institutional inflows added $2.1B over the last 5 days and IV is compressing into earnings — favorable risk/reward setup. Data-center margin expansion has visibility through 2026.",
    counter:
      "Valuation is stretched at ~38x forward; cyclical reversal risk is real if hyperscaler capex normalizes. China export restrictions have been ignored as a tail risk for two quarters and could re-emerge. Semi cycles historically end abruptly.",
    catalyst: "Watching post-earnings reaction May 21; gap-up = invalidates short bears, gap-down = re-tests $158.",
  },
  target: { entry: "$172–$185", t1: "$208", t2: "$222", t3: "$245" },
  horizon: "6 weeks – 6 months",
  bearCaseGlyph: true,
  snoozeOptions: ["24h", "1w", "forever"],
  riskTags: ["Cyclical risk", "Valuation risk", "China export risk"],
};


const PROOF_OPEN_COST: ActionCardData = {
  verb: "OPEN",
  ticker: "COST",
  thesisName: "Membership compounding + traffic stickiness",
  decisionSentence:
    "Initiate Costco below $720 — the membership renewal compound and traffic data both moved up since Q1 results.",
  confidenceTier: "Confirmed",
  freshnessState: "Fresh",
  lastReviewedAt: isoHoursAgo(8),
  expiryCondition: "next monthly comp release or close below $680",
  invalidation:
    "Membership renewal rate slips below 92.5% in any quarter, OR same-store traffic turns negative, OR close below $680.",
  thesis: {
    driver:
      "Membership renewal at 93.1% (US) is at all-time highs and traffic is up despite a tough consumer backdrop. Q1 e-commerce was a positive surprise. Compounding member economics suggest 12-15% earnings growth durability through 2026.",
    counter:
      "Already a consensus crowded long; relative valuation premium to peers is at decade highs. Consumer normalization could compress traffic. Any membership fee increase would reset the renewal-rate narrative.",
    catalyst: "Monthly comp release is the next checkpoint; membership economic disclosure at FY Q3 earnings.",
  },
  target: { entry: "$695–$720", t1: "$780", t2: "$845" },
  horizon: "12–24 months",
  bearCaseGlyph: true,
  snoozeOptions: ["24h", "1w", "forever"],
  riskTags: ["Valuation premium", "Consumer normalization"],
};


export interface ComposeHeroInputs {
  forceQuiet?: boolean;
}


export function composeConvictionHero(inp: ComposeHeroInputs = {}): ConvictionHeroData {
  if (inp.forceQuiet) {
    return {
      date: new Date().toLocaleDateString("en-US", {
        weekday: "long", month: "long", day: "numeric",
      }),
      regime: {
        stance: "Noisy",
        clause: "Maintaining existing positions. No new entries recommended.",
      },
      activePositions: [],
      promotions: [],
      isQuiet: true,
      quietCopy: "Quiet day. Three theses unchanged. No new entries recommended.",
    };
  }

  return {
    date: new Date().toLocaleDateString("en-US", {
      weekday: "long", month: "long", day: "numeric",
    }),
    regime: {
      stance: "Selective, valuation-sensitive",
      clause: "Add only where earnings durability offsets valuation risk.",
    },
    activePositions: [PROOF_HOLD_MSFT, PROOF_TRIM_TSLA, PROOF_EXIT_META],
    promotions: [PROOF_OPEN_NVDA, PROOF_OPEN_COST],
    isQuiet: false,
  };
}
