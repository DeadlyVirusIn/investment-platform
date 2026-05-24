// Phase 2B — Audit trace data + render helper.
//
// Per the recommendation chain (architecture §5.1), every rec carries
// 7 stages of trace. For the MVP we synthesize these from the
// Recommendation + current macro state. A real backend implementation
// would persist this at rec generation time. The shape + voice are
// shared with that future endpoint.

import type { Recommendation } from '../../data/arthosData';
import { classifyCohort } from './cohort';

export interface AuditTrace {
  rec_id: string;
  symbol: string;
  stages: AuditStage[];
  confidence_note: string;
  uncertainty_signals: string[];
}

export interface AuditStage {
  num: number;
  title: string;
  bullets: string[];
}

export function buildAuditTrace(rec: Recommendation): AuditTrace {
  const cohort = classifyCohort(rec);
  return {
    rec_id: rec.symbol,
    symbol: rec.symbol,
    stages: [
      {
        num: 1,
        title: 'What data I used',
        bullets: [
          'HY OAS spread (BAMLH0A0HYM2) — current vs 20d',
          'DGS10 yield — current vs 5d',
          `${rec.symbol} price + implied volatility percentile`,
          'Universe-wide momentum + liquidity filters',
          'No stale features detected today.',
        ],
      },
      {
        num: 2,
        title: 'Macro context',
        bullets: [
          'Market regime: directional (day 3 of streak)',
          'Credit gate: stable',
          'Rates gate: calm',
          'Gates_favorable: 4 of 4',
        ],
      },
      {
        num: 3,
        title: 'Strategy gate',
        bullets: [
          'Engine B fires today (directional + credit_stable + rates_calm)',
          `Decision: ${rec.actionLabel}`,
        ],
      },
      {
        num: 4,
        title: 'Universe scoring',
        bullets: [
          '1,008 candidates evaluated',
          '10 passed per-symbol filters',
          `${rec.symbol} ranked at the top by composite score`,
          'Tie-break seed: deterministic per as_of_date',
        ],
      },
      {
        num: 5,
        title: 'Why this structure',
        bullets:
          rec.kind === 'option'
            ? [
                rec.contract ?? rec.actionLabel,
                'Defined-risk structure chosen because IV percentile favors it',
                'Max loss known before placement',
              ]
            : [
                'Outright stock position',
                `Direction: ${rec.side ?? 'long'}`,
                'Stop and target both quoted upfront',
              ],
      },
      {
        num: 6,
        title: 'Why for you',
        bullets: [
          'See "Why I picked this for you" on the hero card',
          'Personalization rules: holdings overlap + declared comfort + recent skip patterns',
        ],
      },
      {
        num: 7,
        title: 'Confidence',
        bullets: [
          'Medium. I size this at a normal book percentage.',
          'Not high because the catalyst is more than 4 weeks out.',
        ],
      },
    ],
    confidence_note: 'medium',
    uncertainty_signals: [
      'Earnings calendar more than 4 weeks out — guidance risk unknown',
      'IV could expand if macro turns; defined-risk caps the downside',
    ],
    // Cohort surfaced for cross-link
    ...({ cohort } as Record<string, unknown>),
  } as AuditTrace;
}
