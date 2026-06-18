// Strip operator/quant vocabulary out of an engine-generated thesis so
// beginner surfaces never show "composite score -0.44 -> Trim. Trend/momentum
// score ...". Returns plain remainder, or null when the thesis is essentially
// all quant (caller should then fall back to a plain line / hide it).

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
