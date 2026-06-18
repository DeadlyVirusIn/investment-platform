// ideaPlan — derive a beginner-safe "what to do next" Plan for a stock idea
// from data the engine ALREADY produces (Sprint K/L). No fabrication.
//
// Data source: each recommendation carries an `evidence` array with real
// factor readings:
//   - price_vs_sma_long  narrative "Price 357.03 vs long SMA 306.73 (16.40%)"
//   - sma_20_vs_50       narrative "SMA(20)=328.64 vs SMA(50)=310.17 (5.96%)"
//   - atr_pct_14         value     "0.0327..."  (ATR over price, a fraction)
//
// When current price + ATR% are present (Option B), we compute conservative
// paper-PLANNING zones — explicitly labelled an estimate, NOT advice:
//   entry  = last close ± 0.5·ATR        (don't chase gaps)
//   exit   = last close − 2·ATR          (~2 ATR of room; or below SMA50 support)
//   target = last close + 3·ATR          (1.5R against the 2·ATR risk)
// When the data is absent (Option C), we fall back to honest language.

import type { RecApi } from '@/lib/operator/hooks';

interface Evidence {
  factor_key?: string;
  value?: string | null;
  narrative?: string;
}

export interface IdeaPlan {
  entry: string;
  target: string;
  exit: string;       // "Exit if wrong"
  timeframe: string;
  /** true = computed paper-planning estimate; false = honest placeholder */
  estimate: boolean;
}

const TIMEFRAME = 'Medium-term: weeks to months.';

// Honest placeholders (Option C) — used when price/ATR can't be derived,
// or for non-Buy actions where an entry plan doesn't apply.
const PLACEHOLDER: IdeaPlan = {
  entry: 'Consider only near today’s price; avoid chasing large gaps.',
  target: 'No fixed target yet — track in paper first.',
  exit: 'Exit paper trade if the thesis weakens or price breaks below recent support.',
  timeframe: TIMEFRAME,
  estimate: false,
};

function fnum(s: unknown): number {
  const v = typeof s === 'number' ? s : parseFloat(String(s ?? ''));
  return Number.isFinite(v) ? v : NaN;
}

function money(n: number): string {
  return '$' + n.toFixed(2);
}

export function ideaPlan(rec: RecApi): IdeaPlan {
  const action = (rec.adjusted_action ?? rec.action ?? '').toLowerCase();
  // Entry/target/exit planning only makes sense for a Buy idea. For
  // Hold/Trim/Sell show honest placeholder framing.
  if (action !== 'buy') return PLACEHOLDER;

  const ev = (rec.evidence ?? []) as Evidence[];
  const priceEv = ev.find((e) => e.factor_key === 'price_vs_sma_long');
  const atrEv = ev.find((e) => e.factor_key === 'atr_pct_14');
  const smaEv = ev.find((e) => e.factor_key === 'sma_20_vs_50');

  const price = fnum(priceEv?.narrative?.match(/Price\s+([\d.]+)/)?.[1]);
  const atrPct = fnum(atrEv?.value);                       // fraction of price
  const sma50 = fnum(smaEv?.narrative?.match(/SMA\(50\)\s*=\s*([\d.]+)/)?.[1]);

  if (!Number.isFinite(price) || !Number.isFinite(atrPct) || atrPct <= 0) {
    return PLACEHOLDER;
  }

  const atr = price * atrPct;
  const entryLo = price - 0.5 * atr;
  const entryHi = price + 0.5 * atr;
  const stop = price - 2 * atr;
  const target = price + 3 * atr;     // 1.5R vs the 2·ATR risk

  const exitLine = Number.isFinite(sma50) && sma50 < price
    ? `Below ${money(stop)} — or if it breaks support near ${money(sma50)}.`
    : `Below ${money(stop)} (about two volatility steps under entry).`;

  return {
    entry: `${money(entryLo)}–${money(entryHi)}, near last close ${money(price)}.`,
    target: `${money(target)} (paper planning estimate).`,
    exit: exitLine,
    timeframe: TIMEFRAME,
    estimate: true,
  };
}
