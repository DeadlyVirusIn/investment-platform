// Phase Opt-C1 Step 3 — Setup quality dot scale.
//
// Maps a shadow-eval `score` to a 5-bucket dot scale + label.
//
// CRITICAL: this is RELATIVE quality, not win probability. The
// percentile is computed against past 30 days of would_trade=true
// rows for the same strategy family. Without that history (dormant
// mode, or first 30 days of activation), the helper returns
// "early read" and the dots remain at floor.
//
// NEVER use this to surface a "win probability" pill.

export type DotCount = 1 | 2 | 3 | 4 | 5;

export interface SetupQuality {
  dots: DotCount;
  label: string;
  /** True when the percentile cohort had < 10 samples (dormant
   *  state, fresh activation, or sparse strategy). */
  underpowered: boolean;
}


/** Pure helper. Pass in:
 *   - candidate score (from options_shadow_decision_log.score)
 *   - sorted ascending peer scores (other recent would_trade scores
 *     for the SAME strategy family within the last 30d)
 *
 * Returns a 5-bucket dot count + label. Underpowered when peer
 * cohort < 10. Always returns at minimum 1 dot. */
export function computeSetupQuality(
  candidate_score: number | null,
  peer_scores_sorted_asc: number[],
): SetupQuality {
  // Underpowered → "early read" + 1 dot
  if (
    candidate_score == null ||
    peer_scores_sorted_asc.length < 10
  ) {
    return { dots: 1, label: "early read", underpowered: true };
  }

  // Compute percentile of candidate among peers
  // (count of peers strictly less than candidate / total)
  let strictlyLess = 0;
  for (const p of peer_scores_sorted_asc) {
    if (p < candidate_score) strictlyLess++;
    else break; // sorted asc — bail early
  }
  const percentile = (strictlyLess / peer_scores_sorted_asc.length) * 100;

  if (percentile >= 90) {
    return { dots: 5, label: "exceptional setup", underpowered: false };
  }
  if (percentile >= 70) {
    return { dots: 4, label: "strong setup", underpowered: false };
  }
  if (percentile >= 50) {
    return { dots: 3, label: "moderate setup", underpowered: false };
  }
  if (percentile >= 30) {
    return { dots: 2, label: "weak setup", underpowered: false };
  }
  return { dots: 1, label: "early read", underpowered: false };
}


/** Render-only helper: returns the dot string used by tracker rows
 *  and suggestion cards. Filled char + empty char. */
export function dotsString(count: DotCount): string {
  const FILLED = "●";
  const EMPTY = "○";
  return FILLED.repeat(count) + EMPTY.repeat(5 - count);
}
