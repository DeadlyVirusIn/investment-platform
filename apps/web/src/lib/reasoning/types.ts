// Phase L UI-1 — typed shape of the deterministic reasoning envelope
// as returned by GET /api/v2/decisions/{paper_trade_id}/reasoning.
//
// Mirrors apps/api/src/api/reasoning.py response. Frontend NEVER
// paraphrases these fields — they pass through verbatim to the
// renderer.

export type ReasoningSource =
  | "live"
  | "replay"
  | "backfill"
  | "operator_manual";

export interface ReasoningRendered {
  /** Skeleton-driven sentence(s) — vocabulary-substituted. */
  setup: string;
  /** Thesis sentence (horizon + expected outcome). */
  thesis: string;
  /** Uncertainty marker copy, verbatim from locked catalog. ≤3. */
  uncertainty: string[];
}

export interface ReasoningEnvelopeFields {
  slot_fills: Record<string, string | string[]>;
  invalidation: {
    condition_vocab: string;
    threshold: unknown;
  };
  thesis: {
    horizon: string;
    expected_signal: string;
  };
  uncertainty_markers: string[];
  source: ReasoningSource;
  generated_at: string;
}

export interface ReasoningResponse {
  paper_trade_id: string;
  envelope_hash: string;
  skeleton_id: string;
  rendered: ReasoningRendered;
  envelope: ReasoningEnvelopeFields;
}
