// Strip operator/quant vocabulary out of an engine-generated thesis so
// beginner surfaces never show "composite score -0.44 -> Trim. Trend/momentum
// score ...". Returns plain remainder, or null when the thesis is essentially
// all quant (caller should then fall back to a plain line / hide it).

// Translate the engine's family scores into plain investor language.
// Positive signals -> "Why this idea exists"; negative -> "Potential risks".
// Unknown families are dropped (never show raw keys / numbers to beginners).
const FAMILY_PHRASES: { match: RegExp; pos: string; neg: string }[] = [
  { match: /trend|momentum|sma|price/i, pos: 'Market trend is supportive', neg: 'Price trend is weakening' },
  { match: /valuation|value/i, pos: 'Valuation looks attractive', neg: 'Valuation looks stretched' },
  { match: /quality|profit/i, pos: 'Solid business quality', neg: 'Weaker business quality' },
  { match: /growth|revenue|earnings/i, pos: 'Growth is improving', neg: 'Growth is slowing' },
  { match: /vol|risk|beta/i, pos: 'Steadier, lower-risk profile', neg: 'Bigger price swings (more risk)' },
  { match: /sentiment|analyst|revision/i, pos: 'Sentiment is improving', neg: 'Sentiment is weakening' },
];

export interface IdeaSignals { why: string[]; risks: string[]; }

export function ideaSignals(
  familyScores?: Record<string, string | null> | null,
): IdeaSignals {
  const why: string[] = [];
  const risks: string[] = [];
  const seenWhy = new Set<string>();
  const seenRisk = new Set<string>();
  for (const [key, raw] of Object.entries(familyScores ?? {})) {
    const v = raw == null ? NaN : Number(raw);
    if (!Number.isFinite(v) || Math.abs(v) < 0.02) continue;   // ignore ~neutral
    const phrase = FAMILY_PHRASES.find((p) => p.match.test(key));
    if (!phrase) continue;
    if (v > 0 && !seenWhy.has(phrase.pos)) { why.push(phrase.pos); seenWhy.add(phrase.pos); }
    else if (v < 0 && !seenRisk.has(phrase.neg)) { risks.push(phrase.neg); seenRisk.add(phrase.neg); }
  }
  return { why, risks };
}

// A score number in the engine thesis: integer OR decimal (0.314, -0.45, 0).
// CRITICAL: clause patterns must consume the WHOLE number. The earlier
// `[^.]*` form stopped at the decimal point inside "0.314", leaving the
// fraction digits ("314") orphaned — which is exactly how
// "314 Buy. 716. 133. 000. Confidence: (High)." leaked onto the card.
const NUM = '[-+]?\\d+(?:\\.\\d+)?';

export function plainThesis(raw?: string | null): string | null {
  if (!raw) return null;
  let t = raw;
  t = t.replace(/^[A-Z.]{1,6}:\s*/, '');                       // leading "TICKER: "
  // "composite score 0.314 -> Buy." — eat the number, the arrow, the action word.
  t = t.replace(new RegExp(`composite score\\s*${NUM}\\s*(?:->|→)?\\s*[A-Za-z]*\\.?`, 'gi'), '');
  t = t.replace(new RegExp(`trend\\s*/?\\s*momentum score\\s*${NUM}\\.?`, 'gi'), '');
  t = t.replace(new RegExp(`momentum score\\s*${NUM}\\.?`, 'gi'), '');
  t = t.replace(new RegExp(`volatilit\\w*(?:\\s*/?\\s*risk)?\\s*score\\s*${NUM}\\.?`, 'gi'), '');
  t = t.replace(new RegExp(`exposure score\\s*${NUM}\\.?`, 'gi'), '');
  // "Confidence: 83.33 (High)." — drop the whole clause incl. the (Label).
  t = t.replace(new RegExp(`confidence:\\s*${NUM}?\\s*(?:\\([^)]*\\))?\\.?`, 'gi'), '');
  t = t.replace(new RegExp(NUM, 'g'), '');                     // any stray score number
  t = t.replace(/→|->/g, ' ');
  t = t.replace(/\(\s*\)/g, '');                               // empty parens left behind
  t = t.replace(/\s*\.\s*(\.\s*)+/g, '. ');                    // collapse ". . ."
  t = t.replace(/\s{2,}/g, ' ').trim();
  t = t.replace(/^[.\s,;:–—()-]+/, '').trim();                 // leading punctuation
  // If only quant residue is left (no real sentence), bail so the caller
  // falls back to plain language instead of showing punctuation soup.
  const letters = (t.match(/[A-Za-z]/g) ?? []).length;
  return letters >= 8 ? t : null;
}
