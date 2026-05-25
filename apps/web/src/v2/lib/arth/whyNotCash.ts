// Phase 2C — Why-Not-Cash resolver.
//
// Every rec must explicitly justify itself vs holding cash. Three voice
// modes per Phase 2 doc §1.3.empty-day-variant:
//   - clears bar: expected edge well above risk-free
//   - thin edge: expected edge barely positive
//   - does not clear: cash is the better call
//
// Cash bar = current 1m T-bill yield / 252. Hardcoded today since we
// have no risk-free feed in v2; backend integration in Phase 3.

import type { Recommendation } from '../../data/arthosData';

const RISK_FREE_ANNUAL_PCT = 5.2;          // 1m T-bill ~5.2% annualized
const TRADING_DAYS_PER_YEAR = 252;

export interface WhyNotCash {
  line: string;
  mode: 'clears_bar' | 'thin_edge' | 'does_not_clear';
  expected_edge_pct_over_period: number;
  cash_yield_pct_over_period: number;
}

function pctOverPeriod(rec: Recommendation): { edge: number; cash: number } {
  const holdDays = rec.hold_estimate_days_max ?? 14;
  const cashDailyBp = (RISK_FREE_ANNUAL_PCT * 100) / TRADING_DAYS_PER_YEAR;
                                            // ~2.06 bp/d
  const cashOverPeriod = (cashDailyBp * holdDays) / 100;  // → pct
  const edgeBpPerDay = rec.expected_return_per_day_bp ?? 0;
  const edgeOverPeriod = (edgeBpPerDay * holdDays) / 100;  // → pct
  return { edge: edgeOverPeriod, cash: cashOverPeriod };
}

export function resolveWhyNotCash(rec: Recommendation): WhyNotCash {
  const { edge, cash } = pctOverPeriod(rec);
  const conf = rec.confidence_level ?? 'medium';
  const holdMax = rec.hold_estimate_days_max ?? 14;

  if (edge > cash * 1.5 && conf !== 'low') {
    return {
      mode: 'clears_bar',
      line:
        `Holding cash earns ~${RISK_FREE_ANNUAL_PCT.toFixed(1)}% annualized ` +
        `(${cash.toFixed(2)}% over ${holdMax} days at risk-free). Expected ` +
        `edge here is ~${edge.toFixed(2)}% over the same window AND defined-risk ` +
        `caps the downside. I'd take this over cash.`,
      expected_edge_pct_over_period: edge,
      cash_yield_pct_over_period: cash,
    };
  }
  if (edge > cash) {
    return {
      mode: 'thin_edge',
      line:
        `Edge is thin vs cash (cash ${cash.toFixed(2)}% vs my expected ` +
        `${edge.toFixed(2)}% over ${holdMax} days, both before costs). Smaller ` +
        `size, or skip and wait for cleaner.`,
      expected_edge_pct_over_period: edge,
      cash_yield_pct_over_period: cash,
    };
  }
  return {
    mode: 'does_not_clear',
    line:
      `Edge does not clear the cash bar (cash ${cash.toFixed(2)}% vs my expected ` +
      `${edge.toFixed(2)}%). I'm still surfacing this because the structure is ` +
      `interesting — but if you only act on edge-positive ideas, skip today.`,
    expected_edge_pct_over_period: edge,
    cash_yield_pct_over_period: cash,
  };
}

/** True when NO rec in the day's set clears the cash bar with non-low
 *  confidence. Triggers the "Cash is the call today" empty-day variant. */
export function cashIsTheCall(recs: Recommendation[]): boolean {
  if (recs.length === 0) return true;
  return recs.every((r) => resolveWhyNotCash(r).mode !== 'clears_bar');
}

export { RISK_FREE_ANNUAL_PCT };
