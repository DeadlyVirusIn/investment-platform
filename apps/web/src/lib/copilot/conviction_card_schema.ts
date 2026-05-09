// UX-10 Phase 10A — ActionCard refuses-to-render schema.
//
// Source of truth: docs/research/UX_10_CONVICTION_ENGINE.md
//   Section 5.2 (refuses-to-render conditions)
//
// Validation runs at composer time. Throwing in the composer is
// the correct behavior per the master spec — a card that fails
// validation MUST NOT render. We do NOT silently fall back; we
// surface the failure so the composer logic gets fixed.


/** The locked 4-verb set. Adding a new verb requires master doc revision. */
export const VERBS = ["OPEN", "HOLD", "TRIM", "EXIT"] as const;
export type Verb = typeof VERBS[number];


/** The locked 4 confidence tiers. */
export const CONFIDENCE_TIERS = ["Forming", "Working", "Confirmed", "Conviction"] as const;
export type ConfidenceTier = typeof CONFIDENCE_TIERS[number];


/** The locked 4 freshness states. */
export const FRESHNESS_STATES = ["Fresh", "Aging", "Stale", "Expired"] as const;
export type FreshnessState = typeof FRESHNESS_STATES[number];


/** Master-locked schema for an ActionCard. */
export interface ActionCardData {
  verb: Verb;
  ticker: string;
  thesisName: string;
  decisionSentence: string;     // 80–200 chars, declarative
  confidenceTier: ConfidenceTier;
  freshnessState: FreshnessState;
  lastReviewedAt: string;       // ISO timestamp
  expiryCondition: string;      // e.g., "earnings May 21 or close < $462"
  invalidation: string;         // structural, e.g., "Close below $158 on > 1.4× ADV"
  thesis: {
    driver: string;             // ~80 words bull case
    counter: string;            // ~80 words bear case (REQUIRED for Confirmed+)
    catalyst: string;           // single line: what would change conviction
  };
  target: {
    entry: string;
    t1?: string;
    t2?: string;
    t3?: string;
  };
  horizon: string;              // e.g., "6-18 months"
  bearCaseGlyph: boolean;
  snoozeOptions: ReadonlyArray<"24h" | "1w" | "forever">;
  riskTags: ReadonlyArray<string>;
}


/** Validation error — thrown by validateActionCard on failure. */
export class CardSchemaError extends Error {
  constructor(message: string, public readonly card: Partial<ActionCardData>) {
    super(`[UX-10 ActionCard refuses-to-render] ${message}`);
    this.name = "CardSchemaError";
  }
}


/** Returns the card unchanged on success; throws CardSchemaError on failure. */
export function validateActionCard(card: ActionCardData): ActionCardData {
  // S1 — verb in locked set
  if (!card.verb || !VERBS.includes(card.verb)) {
    throw new CardSchemaError(
      `verb '${card.verb}' is not in locked set [${VERBS.join(", ")}]`,
      card,
    );
  }

  // S5 — decision sentence length
  if (!card.decisionSentence || card.decisionSentence.length < 80) {
    throw new CardSchemaError(
      `decisionSentence missing or too short (${card.decisionSentence?.length ?? 0} chars; min 80)`,
      card,
    );
  }
  if (card.decisionSentence.length > 200) {
    throw new CardSchemaError(
      `decisionSentence too long (${card.decisionSentence.length} chars; max 200)`,
      card,
    );
  }

  // S2 — invalidation present + non-stub
  if (!card.invalidation) {
    throw new CardSchemaError("invalidation missing", card);
  }
  const stubMarkers = ["TBD", "varies", "n/a", "tbd"];
  if (stubMarkers.some(s => card.invalidation.toLowerCase().includes(s.toLowerCase()))) {
    throw new CardSchemaError(
      `invalidation contains stub marker (one of: ${stubMarkers.join(", ")})`,
      card,
    );
  }

  // L4 / S3 — bear case mandated for Confirmed+
  if (card.confidenceTier === "Confirmed" || card.confidenceTier === "Conviction") {
    if (!card.thesis?.counter || card.thesis.counter.length < 50) {
      throw new CardSchemaError(
        `${card.confidenceTier} tier requires thesis.counter >= 50 chars (got ${card.thesis?.counter?.length ?? 0})`,
        card,
      );
    }
  }

  // S2 — expiry condition present
  if (!card.expiryCondition) {
    throw new CardSchemaError("expiryCondition missing", card);
  }

  // S2 — last reviewed not stale
  if (!card.lastReviewedAt) {
    throw new CardSchemaError("lastReviewedAt missing", card);
  }
  const reviewedMs = Date.parse(card.lastReviewedAt);
  if (Number.isNaN(reviewedMs)) {
    throw new CardSchemaError(`lastReviewedAt is not a valid ISO timestamp: '${card.lastReviewedAt}'`, card);
  }
  const ageDays = (Date.now() - reviewedMs) / (1000 * 60 * 60 * 24);
  if (ageDays > 7) {
    throw new CardSchemaError(
      `lastReviewedAt is ${ageDays.toFixed(1)} days old (max 7 without re-review)`,
      card,
    );
  }

  // S2 — horizon present
  if (!card.horizon) {
    throw new CardSchemaError("horizon missing", card);
  }

  // Target — if t1/t2/t3 shown, entry + invalidation BOTH must be present.
  // (Invalidation already validated above; re-confirm entry.)
  const hasTarget = !!(card.target?.t1 || card.target?.t2 || card.target?.t3);
  if (hasTarget && !card.target?.entry) {
    throw new CardSchemaError("target tier shown without entry — refusing render", card);
  }

  return card;
}


/**
 * Compute freshness state from a timestamp.
 * Master spec windows: Fresh <24h · Aging 24h–72h · Stale 72h–6d · Expired >6d.
 */
export function computeFreshnessState(lastReviewedAt: string): FreshnessState {
  const ageHours = (Date.now() - Date.parse(lastReviewedAt)) / (1000 * 60 * 60);
  if (ageHours < 24) return "Fresh";
  if (ageHours < 72) return "Aging";
  if (ageHours < 144) return "Stale";  // 6 days
  return "Expired";
}


/** Returns a human-readable "Last reviewed Nh ago" string. */
export function freshnessTimestamp(lastReviewedAt: string): string {
  const ageHours = (Date.now() - Date.parse(lastReviewedAt)) / (1000 * 60 * 60);
  if (ageHours < 1) return `${Math.max(1, Math.round(ageHours * 60))}m ago`;
  if (ageHours < 24) return `${Math.round(ageHours)}h ago`;
  return `${Math.round(ageHours / 24)}d ago`;
}
