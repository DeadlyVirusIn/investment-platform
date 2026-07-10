// Honest Numbers — confidence PRESENTATION mapping (owner decision
// 2026-07-09, docs/research/CONFIDENCE_WORDING_DECISION.md).
//
// Basis: the calibration study showed High-band Buys resolving below the
// level the label implies and Medium outperforming High (label ordering
// inverted; AUC 0.52) — the High/Medium distinction currently carries no
// reliable signal for a beginner. Decision: collapse both to "Meets the
// buy bar".
//
// Presentation ONLY: numeric conviction and confidence_label are
// unchanged in the API and database. Gated by VITE_MEETS_BUY_BAR
// (absent by default — production copy unchanged until approved).

export function meetsBuyBarEnabled(): boolean {
  return import.meta.env.VITE_MEETS_BUY_BAR === '1';
}

/** Chip/inline text for a recommendation's confidence label.
 *  Flag off: legacy `"high confidence"` form. Flag on: High/Medium →
 *  `"meets the buy bar"`; anything else keeps the legacy form. */
export function confidenceDisplay(label: string | null | undefined): string {
  const l = label ?? 'Medium';
  if (meetsBuyBarEnabled() && (l === 'High' || l === 'Medium')) {
    return 'meets the buy bar';
  }
  return `${l.toLowerCase()} confidence`;
}

/** Suffix used inside narrative sentences (bullBear verdicts):
 *  legacy `" at high confidence"` → `" — it meets the buy bar"`. */
export function confidenceNarrativeSuffix(label: string | null | undefined): string {
  if (!label) return '';
  if (meetsBuyBarEnabled() && (label === 'High' || label === 'Medium')) {
    return ' — it meets the buy bar';
  }
  return ` at ${label.toLowerCase()} confidence`;
}

/** Glossary entry shown only while the presentation flag is on. */
export const MEETS_BUY_BAR_GLOSSARY = {
  term: 'Meets the buy bar',
  definition:
    "This idea passed ArthOS's current evidence rules — enough supportive " +
    'signals, on fresh data, to qualify as a Buy idea. It does not mean ' +
    'success is guaranteed or more likely than for other qualifying ideas; ' +
    'markets fall as well as rise, and every idea is practiced with paper ' +
    'money first.',
};
