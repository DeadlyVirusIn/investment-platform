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

export function plainThesis(raw?: string | null): string | null {
  if (!raw) return null;
  let t = raw;
  t = t.replace(/^[A-Z.]{1,6}:\s*/, '');                       // leading "TICKER: "
  t = t.replace(/composite score[^.]*\.?/gi, '');
  t = t.replace(/trend\s*\/?\s*momentum score[^.]*\.?/gi, '');
  t = t.replace(/momentum score[^.]*\.?/gi, '');
  t = t.replace(/volatilit[^.]*\.?/gi, '');                    // volatility / volatilities
  t = t.replace(/exposure score[^.]*\.?/gi, '');
  t = t.replace(/[-+]?\d+\.\d+/g, '');                         // stray decimal scores
  t = t.replace(/→|->/g, ' ');
  t = t.replace(/\s*\.\s*(\.\s*)+/g, '. ');                    // collapse ". . ."
  t = t.replace(/\s{2,}/g, ' ').trim();
  t = t.replace(/^[.\s,;:–—-]+/, '').trim();                   // leading punctuation
  return t.length >= 12 ? t : null;
}
