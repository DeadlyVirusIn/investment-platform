// UX-8B Phase 8B-1 — Portfolio Weather Room condition classifier.
//
// Three-state vocabulary (collapsed from UX-8 R3 attack on the
// original 7-state proposal). Deterministic precedence:
//
//   PRESSURED  >  OPPORTUNISTIC  >  STABLE
//
// Risk dominates always. Opportunity only with non-trivial signal.
// STABLE is the calm default.
//
// Output drives the body[data-condition] attribute and the
// CSS-variable swap on the ConditionBlock hero. NO mid-session
// shifts. NO ML. NO randomness. Pure function of engine state.

export type Condition = "OPPORTUNISTIC" | "PRESSURED" | "STABLE";


export interface ConditionInputs {
  /** Drawdown from peak as a fraction (e.g. -0.07 = 7% below). */
  drawdownFromPeak: number | null;
  /** True when stress regime is currently set. */
  stressContext: boolean;
  /** Count of strategies that paused themselves today. */
  pausedStrategies: number;
  /** Count of ideas currently inside their entry zone. */
  ideasInsideEntryZone: number;
  /** Recent signal-volume bucket. */
  recentSignalVolume: "low" | "normal" | "high";
}


/** Derive the Portfolio Weather Room condition from engine state.
 *  Deterministic. Same inputs always produce the same output.
 *  PRESSURED > OPPORTUNISTIC > STABLE. */
export function deriveCondition(inp: ConditionInputs): Condition {
  // PRESSURED — any active risk trigger overrides everything.
  const dd = inp.drawdownFromPeak ?? 0;
  if (
    dd <= -0.05
    || inp.stressContext
    || inp.pausedStrategies > 0
  ) {
    return "PRESSURED";
  }

  // OPPORTUNISTIC — opportunity present, no risk override,
  // non-trivial signal volume.
  if (
    inp.ideasInsideEntryZone >= 2
    && inp.recentSignalVolume !== "low"
  ) {
    return "OPPORTUNISTIC";
  }

  // STABLE — default calm.
  return "STABLE";
}


/** Phase 8B-1 — proof-state inputs. Hardcoded for the 8-hour
 *  PRESSURED proof. Real wiring lands in Phase 8B-2. */
export const PROOF_PRESSURED_INPUTS: ConditionInputs = {
  drawdownFromPeak: -0.07,
  stressContext: false,
  pausedStrategies: 0,
  ideasInsideEntryZone: 0,
  recentSignalVolume: "normal",
};


/** Phase 8B-1 — locked sample copy for the PRESSURED proof.
 *  Sentence MUST contain a numeric anchor per the visible-
 *  condition-explanation contract (UX-8 §4.3). The 7% anchor
 *  ties to PROOF_PRESSURED_INPUTS.drawdownFromPeak above. */
export const PROOF_PRESSURED_SENTENCE =
  "Account is 7% below its peak this week. "
  + "One holding is approaching its stop level.";
