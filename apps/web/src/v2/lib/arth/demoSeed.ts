// Phase 2B — Demo seed for Report Card screenshots.
//
// Populates a realistic-looking decision history so the Report Card
// screenshots can demonstrate all 8 sections + expectancy panel +
// honesty modes. Only runs in demo mode (URL `?seedReportCard=1`)
// to avoid polluting real user data.

import { listDecisions,
         type Decision, type DecisionConfidence } from './decisions';
import { writeVersioned } from './storage';
import { KEYS } from './storage';
import type { Recommendation } from '../../data/arthosData';

interface Seed {
  rec_id: string;
  symbol: string;
  action: 'paper_traded' | 'skipped' | 'held_cash';
  arth_confidence: DecisionConfidence;
  ts_days_ago: number;
  thesis: string;
  rec?: Recommendation;
  cohort: string;
  outcome?: { pnl_pct: number; days_held: number };
  skip_reason?: string;
}

const SEED: Seed[] = [
  // Closed wins
  { rec_id: 'AAPL', symbol: 'AAPL', action: 'paper_traded',
    arth_confidence: 'medium', ts_days_ago: 28,
    thesis: 'AAPL $175/$180 call spread for $3.40 — IV bottom quartile.',
    cohort: 'long_call_spread_low_iv',
    outcome: { pnl_pct: +1.4, days_held: 8 } },
  { rec_id: 'MSFT', symbol: 'MSFT', action: 'paper_traded',
    arth_confidence: 'medium', ts_days_ago: 25,
    thesis: 'MSFT $385/$400 call spread — earnings cleared, IV reset.',
    cohort: 'long_call_spread_low_iv',
    outcome: { pnl_pct: +2.1, days_held: 6 } },
  { rec_id: 'XLE', symbol: 'XLE', action: 'paper_traded',
    arth_confidence: 'high', ts_days_ago: 21,
    thesis: 'XLE long — crack spreads widened without equity follow-through.',
    cohort: 'directional_long_stock',
    outcome: { pnl_pct: +1.2, days_held: 6 } },
  { rec_id: 'SPY', symbol: 'SPY', action: 'paper_traded',
    arth_confidence: 'medium', ts_days_ago: 18,
    thesis: 'SPY $540/$548 credit spread — realized < implied vol.',
    cohort: 'short_credit_spread',
    outcome: { pnl_pct: +0.8, days_held: 14 } },
  { rec_id: 'GOOGL', symbol: 'GOOGL', action: 'paper_traded',
    arth_confidence: 'medium', ts_days_ago: 12,
    thesis: 'GOOGL $160/$165 spread — pre-earnings IV crush setup.',
    cohort: 'long_call_spread_low_iv',
    outcome: { pnl_pct: +0.6, days_held: 5 } },

  // Closed losses
  { rec_id: 'NVDA', symbol: 'NVDA', action: 'paper_traded',
    arth_confidence: 'medium', ts_days_ago: 24,
    thesis: 'NVDA long — bullish gamma, IV cheap.',
    cohort: 'long_call_outright',
    outcome: { pnl_pct: -2.1, days_held: 4 } },
  { rec_id: 'META', symbol: 'META', action: 'paper_traded',
    arth_confidence: 'low', ts_days_ago: 16,
    thesis: 'META spread — speculative low-conf trade.',
    cohort: 'long_call_spread_low_iv',
    outcome: { pnl_pct: -1.8, days_held: 3 } },
  { rec_id: 'AMD', symbol: 'AMD', action: 'paper_traded',
    arth_confidence: 'low', ts_days_ago: 9,
    thesis: 'AMD breakout — speculative entry.',
    cohort: 'directional_long_stock',
    outcome: { pnl_pct: -2.4, days_held: 5 } },

  // Open positions
  { rec_id: 'COST', symbol: 'COST', action: 'paper_traded',
    arth_confidence: 'medium', ts_days_ago: 4,
    thesis: 'COST long — pre-earnings strength + reversion to channel.',
    cohort: 'directional_long_stock' },
  { rec_id: 'V', symbol: 'V', action: 'paper_traded',
    arth_confidence: 'medium', ts_days_ago: 2,
    thesis: 'V $280 calls — defended uptrend post-pullback.',
    cohort: 'long_call_outright' },

  // Skipped (with reason)
  { rec_id: 'TSLA', symbol: 'TSLA', action: 'skipped',
    arth_confidence: 'low', ts_days_ago: 20,
    thesis: 'TSLA short — catalyst fuzzy.',
    cohort: 'directional_short_stock',
    skip_reason: 'Bad timing' },
  { rec_id: 'JPM', symbol: 'JPM', action: 'skipped',
    arth_confidence: 'medium', ts_days_ago: 14,
    thesis: 'JPM earnings-week call spread.',
    cohort: 'long_call_spread_low_iv',
    skip_reason: 'Earnings risk' },
  { rec_id: 'WMT', symbol: 'WMT', action: 'skipped',
    arth_confidence: 'low', ts_days_ago: 11,
    thesis: 'WMT earnings-week spread.',
    cohort: 'long_call_spread_low_iv',
    skip_reason: 'Earnings risk' },
  { rec_id: 'BA', symbol: 'BA', action: 'skipped',
    arth_confidence: 'medium', ts_days_ago: 7,
    thesis: 'BA short into delivery report.',
    cohort: 'directional_short_stock',
    skip_reason: 'Too risky' },

  // Cash days
  { rec_id: 'CASH', symbol: 'CASH', action: 'held_cash',
    arth_confidence: 'low', ts_days_ago: 6,
    thesis: 'No setup beat the cash bar today.',
    cohort: 'uncategorized' },
];

export function seedReportCardDemo(): void {
  if (listDecisions().length > 0) return;     // do not double-seed

  const created: Decision[] = [];
  const now = Date.now();
  for (const s of SEED) {
    const ts = new Date(now - s.ts_days_ago * 86_400_000).toISOString();
    created.push({
      id: `seed-${s.rec_id}-${s.ts_days_ago}`,
      rec_id: s.rec_id,
      symbol: s.symbol,
      action: s.action,
      skip_reason: s.skip_reason,
      thesis_snapshot: s.thesis,
      ts,
      cohort: s.cohort,
      arth_confidence: s.arth_confidence,
      outcome: s.outcome
        ? {
            closed_at: new Date(
              new Date(ts).getTime() + s.outcome.days_held * 86_400_000,
            ).toISOString(),
            pnl_pct: s.outcome.pnl_pct,
            days_held: s.outcome.days_held,
            arth_was_right: s.outcome.pnl_pct > 0,
          }
        : undefined,
    });
  }
  writeVersioned(KEYS.decisions, created);
}
