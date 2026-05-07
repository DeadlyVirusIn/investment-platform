// UX-3D Phase A — single source of truth for copilot strings + grammar.
//
// Imported by every copilot component. NO inline strings allowed in
// component JSX — everything must trace back here. The CI lint at
// scripts/lint-copilot-copy.mjs scans this file + every copilot
// component and rejects banned tokens (anti-AI-theater rules).
//
// Hard rules:
//   * Heroes: ≤100 chars, exactly one sentence, observed never authored.
//   * Synthesis sentences: deterministic grammar templates, no LLM.
//   * Banned conjunctions: because, due to, driven by, as a result,
//     which means, so, hence, therefore.
//   * Banned vocabulary: AI / model / I noticed / we think / market wants
//     / likely / expected to / should / 🚀 / 🔥 / hot pick / streak /
//     personalised for you (full list in scripts/lint-copilot-copy.mjs).

import type {
  ConfidenceBand,
  HeroPattern,
  PacingState,
  ToneKind,
} from "./types";


// ---------------------------------------------------------------------
// 1. Locked strings
// ---------------------------------------------------------------------

export const COPILOT_BRAND = {
  modeBrief: "Brief view",
  modeWorking: "Working view",
  seeTheWorking: "See the working",
  seeTheWorkingIntro:
    "Where every claim above comes from. Open as much as you want.",
  readOnlyFooter:
    "Read-only research — paper trading only. Nothing on this page "
    + "places orders. Not financial advice.",
} as const;


// ---------------------------------------------------------------------
// 2. Onboarding clauses (3 only — UX-3D refinement reduced 5 → 3)
// ---------------------------------------------------------------------

export const ONBOARDING_CLAUSES = {
  ux_seen_quiet_day:
    "Days like this are common — the strategies sit out when nothing "
    + "fits. Hidden after this.",
  ux_seen_first_position:
    "Each open trade has a story. We'll keep it short.",
  ux_seen_first_exit:
    "Stop-losses and take-profits are deterministic — the strategy "
    + "closes the trade automatically when one triggers.",
} as const;


// ---------------------------------------------------------------------
// 3. Confidence band labels (3-band, never numeric)
// ---------------------------------------------------------------------

export const CONFIDENCE_LABELS: Record<ConfidenceBand, {
  short: string;
  long: string;
}> = {
  lower: {
    short: "Early",
    long: "Early signal — we'd want more data before leaning on it.",
  },
  medium: {
    short: "Medium",
    long: "Several conditions line up — still not a guarantee.",
  },
  higher: {
    short: "Higher",
    long:
      "Most conditions are aligned today. Past setups varied; "
      + "not a forecast.",
  },
};


// ---------------------------------------------------------------------
// 4. Status / state copy (replaces the alarming variants)
// ---------------------------------------------------------------------

export const STATUS_COPY = {
  // Per UX-3D refinement — softer than "Something needs attention.";
  // observational, not alarming.
  needs_attention: "System status changed today. Open *System status* below.",
  loading_status: "System status is loading.",
  paper_only_short: "Paper trading only · no real money",
} as const;


// ---------------------------------------------------------------------
// 5. Hero patterns (8 deterministic branches — UX-3D §1b refined)
// ---------------------------------------------------------------------

/** Slight cadence variation for repeated quiet states. The composer
 *  rotates through this list keyed on local-date so a returning user
 *  on day N sees a slightly different sentence than day N-1. Each
 *  variant is observational, never poetic, never authored. */
export const QUIET_HERO_VARIANTS: ReadonlyArray<string> = [
  "Quiet session so far.",
  "Quiet open.",
  "Calm session.",
  "Nothing pressing today.",
];


export const HERO_TEMPLATES: Record<HeroPattern, {
  /** A function rendering the hero sentence. Inputs must be plain
   *  values; outputs must be ≤100 chars, exactly 1 sentence. */
  render: (vars: Record<string, string | number>) => string;
  tone: ToneKind;
  pacing: PacingState;
}> = {
  first_session: {
    render: () =>
      "First session. This line will summarise the day once data lands.",
    tone: "calm",
    pacing: "calm",
  },
  needs_attention: {
    render: () => STATUS_COPY.needs_attention,
    tone: "attention",
    pacing: "grounded",
  },
  quiet_session: {
    render: ({ variantIndex = 0 }) => {
      const i = (typeof variantIndex === "number" ? variantIndex : 0)
        % QUIET_HERO_VARIANTS.length;
      return QUIET_HERO_VARIANTS[i];
    },
    tone: "calm",
    pacing: "meditative",
  },
  carrying_open_only: {
    render: ({ openCount = 0 }) => {
      const n = Number(openCount) || 0;
      const noun = n === 1 ? "open position" : "open positions";
      return `${n} ${noun}. Nothing new today.`;
    },
    tone: "calm",
    pacing: "calm",
  },
  softened_with_new_setups: {
    render: ({ newCount = 0 }) => {
      const n = Number(newCount) || 0;
      const word = n === 1 ? "new setup" : "new setups";
      return `Markets softened overnight. ${n} ${word} today.`;
    },
    tone: "calm",
    pacing: "calm",
  },
  volatility_elevated: {
    render: () => "Volatility is elevated today.",
    tone: "waiting",
    pacing: "slowed",
  },
  calmer_after_selloff: {
    render: () => "A calmer open after yesterday's selloff.",
    tone: "calm",
    pacing: "released",
  },
  drawdown_from_peak: {
    render: ({ pct = 0 }) => {
      const v = Number(pct) || 0;
      // Render absolute value; sign is implied by the noun.
      const abs = Math.abs(v).toFixed(0);
      return `The account is ${abs}% below its peak this week.`;
    },
    tone: "waiting",
    pacing: "grounded",
  },
};


// ---------------------------------------------------------------------
// 6. Quiet Day component copy
// ---------------------------------------------------------------------

export const QUIET_DAY_COPY = {
  headline: "Quiet day.",
  body:
    "The strategies didn't see a setup that fits today. "
    + "We're watching tomorrow's data.",
} as const;


// ---------------------------------------------------------------------
// 7. Lifecycle ribbon node labels
// ---------------------------------------------------------------------

export const LIFECYCLE_NODES = {
  idea: "Idea",
  bought: "Bought",
  held: "Day",        // suffixed at render time, e.g., "Day 4 of 10"
  exit: "Closed",
} as const;


// ---------------------------------------------------------------------
// 8. Disclosure row affordance
// ---------------------------------------------------------------------

export const DISCLOSURE = {
  caretClosed: "▸",
  caretOpen: "▾",
  expandAria: "Show details",
  collapseAria: "Hide details",
} as const;


// ---------------------------------------------------------------------
// 9. Tone-dot visible label (used by aria-label only; not visible)
// ---------------------------------------------------------------------

export const TONE_LABELS: Record<ToneKind, string> = {
  calm: "calm",
  healthy: "healthy",
  waiting: "waiting",
  attention: "needs attention",
  insight: "read-only insight",
};
