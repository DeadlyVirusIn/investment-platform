// UX-5B Phase B-1 — Today (Overview) copy.
//
// Single source of truth for every string the new Layer-1
// Overview surfaces. Imported by overview_derive.ts and the six
// block components (B-2). NO inline strings in those components.
//
// Hard rules (UX-5 §3 + §12 + UX-5B §14b):
//   * No engine vocabulary. Banned tokens enforced by the lint
//     scope expansion landing in Phase B-4.
//   * No scores, conviction language, or urgency. Block 3 is
//     observational only.
//   * Quiet-day templates are first-class, not a fallback.
//   * Cadence variation: greeting + today-line + quiet-day
//     sentence rotate by local date (R-G).
//   * Empty blocks collapse — derive returns null and the
//     component returns null. NEVER placeholder copy.
//
// Each template is observed, never authored. Composition
// happens in overview_derive.ts; this file holds the strings.


// ---------------------------------------------------------------------
// 1. Time-of-day greeting (rotates per R-G)
// ---------------------------------------------------------------------
//
// Two variants per slot. The variant index is a deterministic
// function of the local date so a returning user sees subtle
// day-to-day variation.

export const GREETINGS = {
  morning: ["Good morning.", "Morning."],
  afternoon: ["Good afternoon.", "Afternoon."],
  evening: ["Good evening.", "Evening."],
} as const;


// ---------------------------------------------------------------------
// 2. Today-line — regime → calm sentence (rotates per R-G)
// ---------------------------------------------------------------------
//
// One sentence per regime. 2 variants each so the line varies
// gently across consecutive days with the same regime. Banned
// tokens absent: "regime", "stress", "trending" never reach the
// rendered sentence — only the calm phrasing does.

export const TODAY_LINE_BY_REGIME: Record<string, ReadonlyArray<string>> = {
  calm: [
    "Markets are calm today.",
    "Markets are quiet today.",
  ],
  trending: [
    "Markets are moving with direction today.",
    "Markets are trending steadily today.",
  ],
  choppy: [
    "Markets are bouncing around today.",
    "Markets are uneven today.",
  ],
  stress: [
    "Markets remain unstable today.",
    "Markets are unsettled today.",
  ],
} as const;


// Pipeline-failed override — replaces today-line entirely.
// Never narrates: just states the situation + the recovery hint.
export const PIPELINE_CATCHING_UP_LINE =
  "We're catching up. See the working below for system status.";


// First sentence of the today-line block. Composes with the
// regime sentence above; always present so the user has a
// "system reviewed today" anchor before the regime context.
export const SYSTEM_REVIEWED_LINE =
  "The system reviewed today's market activity.";


// ---------------------------------------------------------------------
// 3. Holdings summary — count + state-clause
// ---------------------------------------------------------------------

export const HOLDINGS_SUMMARY = {
  noneOpen: "No open paper positions today.",
  // Count + state-clause assemble: "{n} {positionNoun}. {clause}."
  positionNounSingular: "paper position",
  positionNounPlural: "paper positions",
  // State clauses indexed by deterministic input combinations.
  // Mark-dependent clauses (approaching target, etc.) stay
  // omitted until pricing is wired. R-E: empty data → omit
  // clause entirely, render only count.
  stateClauses: {
    allStable: "All quietly working",
    oneApproachingTarget:
      "Most are quietly working; one is approaching its target",
    allApproaching: "All are approaching their targets",
    oneNeedsAttention: "One needs attention",
  },
  link: "See my holdings",
} as const;


// ---------------------------------------------------------------------
// 4. Today's ideas — observational templates only (R-A)
// ---------------------------------------------------------------------
//
// Per-idea card composition: "{symbol} · Today\n{observation}."
// Observations are chart-context phrases, never scores, never
// conviction. Each idea picks the ONE template matching its
// data; no rotation across days for ideas (R-G).

export const IDEA_OBSERVATIONS = {
  // Returned when no specific data signal matches; safe default
  // observational sentence that doesn't narrate non-existent
  // movement.
  generic: "On the system's shortlist today.",
  // Each entry maps a data condition (computed in derive) to a
  // calm observed sentence. Order = preference; first match wins.
  entryZoneReached: "Entry zone reached.",
  pullbackHeld: "Pullback into support held.",
  baseBuilding: "Building a base near the {window}-day average.",
  earningsApproaching: "Reports earnings later this week.",
  recentlyMoved: "Recently moved.",
  sectorStrengthening: "{sector} continued strengthening.",
  sectorStable: "{sector} remained stable during today's weakness.",
} as const;


export const TODAYS_IDEAS = {
  header: "Today's ideas",
  link: "See all ideas",
  // R-H — fresh ideas use "Today", never "Day 0". The lint bans
  // "Day 0" outright in Layer-1/2 surfaces.
  freshTemporalCue: "Today",
} as const;


// ---------------------------------------------------------------------
// 5. What changed — tiny, editorial deltas (R-C)
// ---------------------------------------------------------------------

export const WHAT_CHANGED = {
  header: "What changed",
  // Each template is one sentence ≤ 80 chars. Composes from
  // deterministic delta inputs. R-C bans changelog/analytics
  // formatting.
  newIdeasSingular: "One new idea appeared overnight.",
  newIdeasPlural: "{n} new ideas appeared overnight.",
  positionApproachingTarget:
    "One position is approaching its target.",
  positionsApproachingTarget:
    "{n} positions are approaching their targets.",
  positionClosedSingular: "One position closed today.",
  positionsClosedPlural: "{n} positions closed today.",
  regimeShifted:
    "Markets shifted from {prev} to {now}.",
  // Quiet-day fallback when nothing changed in a meaningful way.
  // Still observational; never "no changes today" as a chip.
  quietChangeFallback:
    "Today looks much like yesterday.",
} as const;


// ---------------------------------------------------------------------
// 6. Risk line — conditional (renders ONLY when triggered)
// ---------------------------------------------------------------------

export const RISK_LINE = {
  header: "What needs attention",
  drawdownPercent: "The account is {pct}% below its peak this week.",
  stressContext: "Markets remain unstable today.",
  pausedSingular: "One strategy paused itself today.",
  pausedPlural: "{n} strategies paused themselves today.",
} as const;


// ---------------------------------------------------------------------
// 7. Watch this week — events translated to watchfulness (R-D)
// ---------------------------------------------------------------------
//
// Raw event codes (CPI, FOMC, NFP) NEVER reach the rendered
// surface. Translation map below resolves to human watchfulness
// phrases. Anything missing from the map omits silently.

export const WATCH_TRANSLATIONS: Record<string, string> = {
  CPI: "Inflation data arrives {day}.",
  FOMC: "The Fed meets {day}.",
  NFP: "Jobs data lands {day}.",
  ECI: "Wage data updates {day}.",
  GDP: "Growth figures publish {day}.",
  ECB: "The European central bank meets {day}.",
  BOJ: "The Japanese central bank meets {day}.",
  EARNINGS: "{symbol} reports {day}.",
} as const;


export const WATCH = {
  header: "What to watch this week",
  // No fallback content — R-E empty-collapse rule. If no
  // events translate, the block is absent.
} as const;


// ---------------------------------------------------------------------
// 8. Quiet-day rendering (R-B — first-class, NOT fallback)
// ---------------------------------------------------------------------
//
// Three variants for the one-sentence quiet-day body. Rotates
// by local date so a returning user sees subtle variation.
// The page still renders greeting + this sentence + footer —
// never "loading" or "empty state".

export const QUIET_DAY_VARIANTS: ReadonlyArray<string> = [
  "Quiet day. Nothing pressing today.",
  "A calm day. Nothing needs your attention.",
  "Quiet across the board. Watching tomorrow's data.",
] as const;


// ---------------------------------------------------------------------
// 9. Single-link footer (Layer-3 escape hatch — Decision 7)
// ---------------------------------------------------------------------

export const TODAY_FOOTER = {
  readOnly:
    "AI-generated research and paper-trading guidance · educational use only · "
    + "nothing on this page places live orders · not financial advice.",
  workingLink: "See the working",
} as const;
