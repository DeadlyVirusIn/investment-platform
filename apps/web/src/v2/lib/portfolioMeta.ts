// portfolioMeta — humanize model-portfolio attributes for beginner surfaces
// (Build stage). Plain language, no quant jargon. All values derive from real
// portfolio fields (risk_label, track record) — nothing fabricated.

const RISK_LEVEL: Record<string, string> = {
  growth: 'Higher risk',
  balanced: 'Medium risk',
  conservative: 'Lower risk',
};

const RISK_WHO: Record<string, string> = {
  growth: 'Investors who can sit through bigger ups and downs for more long-term growth.',
  balanced: 'Investors who want growth without the wildest swings.',
  conservative: 'Investors who value steadiness and income over maximum growth.',
};

const RISK_WHY: Record<string, string> = {
  growth: 'Concentrated in fast-growing companies — more reward, but bigger drops along the way.',
  balanced: 'A middle path: steadier than pure growth, more upside than pure income.',
  conservative: 'Steadier, income-leaning companies — built to ride out rough patches.',
};

/** Plain risk level, or "Medium risk" when the code is unknown. */
export function riskLevel(code?: string | null): string {
  if (!code) return 'Medium risk';
  return RISK_LEVEL[code.trim().toLowerCase()] ?? 'Medium risk';
}

/** "Who is it for?" in one line. */
export function riskWho(code?: string | null): string {
  return RISK_WHO[(code ?? '').trim().toLowerCase()] ?? RISK_WHO.balanced;
}

/** "Why does it exist?" framing (complements the thesis). */
export function riskWhy(code?: string | null): string {
  return RISK_WHY[(code ?? '').trim().toLowerCase()] ?? RISK_WHY.balanced;
}

// These model portfolios are long-horizon buy-and-hold baskets (track records
// run from ~2008). They are not traded — they are held through cycles.
export const HOLD_PERIOD = 'Years — built to hold through market cycles, not to trade.';
