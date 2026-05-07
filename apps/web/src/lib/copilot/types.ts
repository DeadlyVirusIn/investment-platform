// UX-3D Phase A — copilot type system.
//
// Single source of truth for the structured shapes that copy + derive
// + components share. NEVER imported by execution / paper-trading
// modules. NEVER carries values, only types.

export type PacingState =
  | "calm"
  | "meditative"
  | "lifted"
  | "grounded"
  | "slowed"
  | "released";


export type ToneKind =
  | "calm"        // grey
  | "healthy"     // green
  | "waiting"     // amber
  | "attention"   // red
  | "insight";    // sky


export type ConfidenceBand = "lower" | "medium" | "higher";


export type ViewMode = "brief" | "working";


/** Hero pattern keys. Each maps to a deterministic engine-state
 *  branch in derive.ts. The card composer never invents a pattern. */
export type HeroPattern =
  | "first_session"
  | "needs_attention"
  | "quiet_session"
  | "carrying_open_only"
  | "softened_with_new_setups"
  | "volatility_elevated"
  | "calmer_after_selloff"
  | "drawdown_from_peak";


export interface HeroCopy {
  /** The single short sentence shown in the hero. Always ≤100 chars,
   *  always exactly one sentence, never animated. */
  sentence: string;
  /** Tone for the dot before the hero sentence. */
  tone: ToneKind;
  /** Pacing state used by the slot to pick type weight + spacing. */
  pacing: PacingState;
  /** Provenance string — names the engine fields that drove this
   *  hero. Rendered as a `data-source` attribute. */
  dataSource: string;
}


/** localStorage flags for first-time onboarding clauses.
 *  See onboarding.ts. */
export type OnboardingFlag =
  | "ux_seen_quiet_day"
  | "ux_seen_first_position"
  | "ux_seen_first_exit";


export interface CopilotProvenance {
  /** Comma-separated list of engine fields that compose this prose
   *  line. Required on every synthesised sentence. */
  source: string;
}
