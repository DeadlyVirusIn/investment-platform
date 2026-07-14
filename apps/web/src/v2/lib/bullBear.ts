// Bull-vs-Bear deriver (P0-1, investor-demo).
//
// Turns the recommendation's REAL stored evidence (RecEvidence[] from
// GET /recommendations) into a beginner-legible "both sides" view:
//   - Why bulls like it   = bullish factors, plain-translated
//   - Why bears worry      = bearish factors, plain-translated
//   - Why ArthOS still likes it = an honest synthesis templated from the
//     composite score / confidence / post-policy dampers (no LLM prose).
//
// CRITICAL: this is a beginner default surface, so it NEVER emits the raw
// engine narratives (SMA/RSI/ATR strings). Each factor is mapped to a plain
// phrase; unknown factors fall back to their family phrase or are dropped.
// The raw narratives live only in the Layer-3 Recommendation Trace.

import type { RecApi, RecEvidence } from '@/lib/operator/hooks';
import { confidenceNarrativeSuffix } from './confidenceDisplay';

export interface SidePoint {
  key: string;
  phrase: string;
  score: number; // abs contribution, for ordering
}

export interface BullBear {
  bull: SidePoint[];
  bear: SidePoint[];
  bullCount: number;
  bearCount: number;
  action: string; // effective action, Title-case
  confidenceLabel: string | null;
  net: number; // composite (post-policy if present)
  dampers: string[]; // plain "what trimmed the call" notes
  verdictLabel: string; // section heading, action-aware
  verdict: string; // the honest synthesis sentence
}

// Plain translations per known engine factor. Optional `fmt` injects a
// beginner-meaningful number (e.g. a drawdown %) from the real value.
const FACTOR: Record<
  string,
  { bull?: string; bear?: string; fmt?: (v: number) => string }
> = {
  price_vs_sma_long: {
    bull: 'Trading well above its long-term average price',
    bear: 'Trading below its long-term average price',
  },
  sma_20_vs_50: {
    bull: 'Short-term trend is rising faster than the long-term trend',
    bear: 'Short-term trend is fading versus the long-term trend',
  },
  trend_strength: {
    bull: 'In a strong, established uptrend',
    bear: 'Trend strength is weak or rolling over',
  },
  rsi_14: {
    bull: 'Momentum is firmly positive',
    bear: 'Momentum looks stretched',
  },
  atr_pct_14: {
    bull: 'Day-to-day price swings are relatively calm',
    bear: 'Day-to-day price swings add risk',
  },
  max_drawdown: {
    bull: 'Has held up without a severe drop recently',
    bear: 'Has seen a notable past drawdown',
    fmt: (v) => ` (~${Math.round(Math.abs(v) * 100)}%)`,
  },
  beta_vs_spy: {
    bull: 'Moves more steadily than the broad market',
    bear: 'Swings harder than the broad market',
  },
  portfolio_weight: {
    bull: 'Adds useful diversification to the book',
    bear: 'Would concentrate the book further',
  },
};

// Family-level fallback when a factor_key isn't individually mapped.
const FAMILY: { match: RegExp; bull: string; bear: string }[] = [
  { match: /trend|momentum|sma|price/i, bull: 'Market trend is supportive', bear: 'Price trend is weakening' },
  { match: /vol|risk|beta|drawdown/i, bull: 'Steadier, lower-risk profile', bear: 'Bigger price swings (more risk)' },
  { match: /valuation|value/i, bull: 'Valuation looks attractive', bear: 'Valuation looks stretched' },
  { match: /quality|profit/i, bull: 'Solid business quality', bear: 'Weaker business quality' },
  { match: /growth|revenue|earnings/i, bull: 'Growth is improving', bear: 'Growth is slowing' },
  { match: /exposure|weight/i, bull: 'Fits current exposure well', bear: 'Stretches current exposure' },
  { match: /sentiment|analyst|revision/i, bull: 'Sentiment is improving', bear: 'Sentiment is weakening' },
];

function num(s: string | null | undefined): number {
  const v = s == null ? NaN : Number(s);
  return Number.isFinite(v) ? v : NaN;
}

function phraseFor(e: RecEvidence, side: 'bull' | 'bear'): string | null {
  const mapped = FACTOR[e.factor_key];
  if (mapped && mapped[side]) {
    let p = mapped[side] as string;
    const v = num(e.value);
    if (mapped.fmt && Number.isFinite(v)) p += mapped.fmt(v);
    return p;
  }
  const fam = FAMILY.find((f) => f.match.test(e.factor_key) || (e.family != null && f.match.test(e.family)));
  return fam ? fam[side] : null;
}

function titleAction(a: string | null): string {
  if (!a) return 'Hold';
  return a.charAt(0).toUpperCase() + a.slice(1).toLowerCase();
}

// Post-policy dampers → SHORT plain labels (never raw rule/reason debug text).
const DAMPER_LABELS: { match: RegExp; label: string }[] = [
  { match: /volatil/i, label: 'high volatility' },
  { match: /invers|confidence/i, label: 'recent misses' },
  { match: /drawdown/i, label: 'recent drawdown' },
  { match: /exposure|concentrat/i, label: 'position size' },
  { match: /stale|fresh/i, label: 'data freshness' },
];

function readDampers(policy: unknown): string[] {
  const out: string[] = [];
  const adj = (policy as { adjustments?: unknown })?.adjustments;
  if (!Array.isArray(adj)) return out;
  for (const a of adj) {
    const rule = (a as { rule?: string })?.rule ?? '';
    const reason = (a as { reason?: string })?.reason ?? '';
    const hay = `${rule} ${reason}`;
    const m = DAMPER_LABELS.find((d) => d.match.test(hay));
    const label = m ? m.label : (rule ? rule.replace(/_/g, ' ').replace(/damping|cap/gi, '').trim() : '');
    if (label && !out.includes(label)) out.push(label);
  }
  return out.slice(0, 2);
}

export function bullBear(rec: RecApi): BullBear {
  const evidence = rec.evidence ?? [];
  const bull: SidePoint[] = [];
  const bear: SidePoint[] = [];
  const seenBull = new Set<string>();
  const seenBear = new Set<string>();

  for (const e of evidence) {
    const score = num(e.score);
    const dir = (e.direction ?? '').toLowerCase();
    const isBull = dir === 'bullish' || (dir !== 'bearish' && Number.isFinite(score) && score > 0.02);
    const isBear = dir === 'bearish' || (dir !== 'bullish' && Number.isFinite(score) && score < -0.02);
    if (dir === 'neutral' || (!isBull && !isBear)) continue;
    const side: 'bull' | 'bear' = isBull ? 'bull' : 'bear';
    const phrase = phraseFor(e, side);
    if (!phrase) continue;
    const mag = Number.isFinite(score) ? Math.abs(score) : 0;
    if (side === 'bull' && !seenBull.has(phrase)) { bull.push({ key: e.factor_key, phrase, score: mag }); seenBull.add(phrase); }
    else if (side === 'bear' && !seenBear.has(phrase)) { bear.push({ key: e.factor_key, phrase, score: mag }); seenBear.add(phrase); }
  }

  bull.sort((a, b) => b.score - a.score);
  bear.sort((a, b) => b.score - a.score);

  const action = titleAction(rec.adjusted_action ?? rec.action);
  const net = num(rec.adjusted_composite_score ?? rec.composite_score);
  const dampers = readDampers(rec.policy);
  const conf = rec.confidence_label;

  // Honest, action-aware synthesis — derived from real numbers only.
  const lead = bear.length === 0
    ? 'No major risk factors are flagged'
    : `Even with ${bear.length} risk${bear.length === 1 ? '' : 's'} on the table`;
  let verdictLabel: string;
  let verdict: string;
  const a = action.toLowerCase();
  if (a === 'buy') {
    verdictLabel = 'Why ArthOS still likes it';
    verdict = `${lead}, ${bull.length} supportive signal${bull.length === 1 ? '' : 's'} outweigh them — enough to clear the buy line${confidenceNarrativeSuffix(conf)}.`;
  } else if (a === 'sell' || a === 'trim') {
    verdictLabel = 'Why ArthOS is stepping back';
    verdict = `The risks currently outweigh the supportive signals, so ArthOS rates this a ${action}${confidenceNarrativeSuffix(conf)}.`;
  } else {
    verdictLabel = 'Where ArthOS lands';
    verdict = `The bullish and bearish signals roughly balance, so ArthOS keeps this a ${action} rather than a buy${conf ? ` (${conf.toLowerCase()} confidence)` : ''}.`;
  }
  return {
    bull, bear,
    bullCount: bull.length, bearCount: bear.length,
    action, confidenceLabel: conf, net: Number.isFinite(net) ? net : 0,
    dampers, verdictLabel, verdict,
  };
}
