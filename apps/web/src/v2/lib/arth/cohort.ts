// Phase 2A — Historical cohort indexing.
//
// Classifies recommendations into coarse cohorts so Task 1 (Decision
// Desk) + Task 4 (Arth Report Card) can answer "how have similar
// ideas performed."  Cohort key example: "long_call_spread_low_iv".
//
// Classifier is rule-based + deterministic. Inputs: Recommendation
// fields available today (kind/side/symbol/IV hints from action labels).
// Falls back to "uncategorized" if nothing matches.

import type { Recommendation } from '../../data/arthosData';
import { listDecisions, type Decision } from './decisions';

export type CohortKey = string;

interface CohortClassifier {
  key: CohortKey;
  match: (rec: Recommendation) => boolean;
}

const CLASSIFIERS: CohortClassifier[] = [
  {
    key: 'long_call_spread_low_iv',
    match: (r) =>
      r.kind === 'option' &&
      r.side === 'long-option' &&
      /call.*spread/i.test(r.actionLabel) &&
      /bottom quartile|low.*iv|iv<25/i.test(r.paragraph),
  },
  {
    key: 'short_credit_spread',
    match: (r) =>
      r.kind === 'option' &&
      r.side === 'short-option' &&
      /credit|premium/i.test(r.actionLabel + ' ' + r.paragraph),
  },
  {
    key: 'long_call_outright',
    match: (r) =>
      r.kind === 'option' &&
      r.side === 'long-option' &&
      !/spread/i.test(r.actionLabel),
  },
  {
    key: 'directional_long_stock',
    match: (r) => r.kind === 'stock' && r.side === 'long',
  },
  {
    key: 'directional_short_stock',
    match: (r) => r.kind === 'stock' && r.side === 'short',
  },
];

export function classifyCohort(rec: Recommendation): CohortKey {
  for (const c of CLASSIFIERS) {
    if (c.match(rec)) return c.key;
  }
  return 'uncategorized';
}

export interface CohortStats {
  cohort: CohortKey;
  closes: number;
  wins: number;
  losses: number;
  expired: number;
  avg_win_pct: number;       // 0 if no wins
  avg_loss_pct: number;      // 0 if no losses
  win_rate: number;          // 0..1, undefined if closes===0
  expectancy_pct: number;    // (win_rate * avg_win) + ((1-win_rate) * avg_loss)
  avg_hold_days: number;
}

const SUFFICIENT_SAMPLE = 5;

/** Compute per-cohort stats from closed decisions. */
export function cohortStats(cohort: CohortKey): CohortStats {
  const decisions = listDecisions();
  const inCohort = decisions.filter(
    (d) => (d as Decision & { cohort?: string }).cohort === cohort && d.outcome,
  );
  return summarize(cohort, inCohort);
}

export function allCohortStats(): CohortStats[] {
  const decisions = listDecisions();
  const groups: Record<string, Decision[]> = {};
  for (const d of decisions) {
    if (!d.outcome) continue;
    const key = (d as Decision & { cohort?: string }).cohort ?? 'uncategorized';
    groups[key] = groups[key] ?? [];
    groups[key].push(d);
  }
  return Object.entries(groups).map(([k, ds]) => summarize(k, ds));
}

export function sufficientSample(stats: CohortStats): boolean {
  return stats.closes >= SUFFICIENT_SAMPLE;
}

function summarize(cohort: CohortKey, decisions: Decision[]): CohortStats {
  const closes = decisions.filter((d) => d.outcome);
  const wins = closes.filter((d) => (d.outcome?.pnl_pct ?? 0) > 0);
  const losses = closes.filter((d) => (d.outcome?.pnl_pct ?? 0) < 0);
  const expired = closes.filter((d) => (d.outcome?.pnl_pct ?? 0) === 0);
  const avg_win =
    wins.length === 0
      ? 0
      : wins.reduce((s, d) => s + (d.outcome?.pnl_pct ?? 0), 0) / wins.length;
  const avg_loss =
    losses.length === 0
      ? 0
      : losses.reduce((s, d) => s + (d.outcome?.pnl_pct ?? 0), 0) / losses.length;
  const wr = closes.length === 0 ? 0 : wins.length / closes.length;
  const expectancy = wr * avg_win + (1 - wr) * avg_loss;
  const avg_hold =
    closes.length === 0
      ? 0
      : closes.reduce((s, d) => s + (d.outcome?.days_held ?? 0), 0) /
        closes.length;
  return {
    cohort,
    closes: closes.length,
    wins: wins.length,
    losses: losses.length,
    expired: expired.length,
    avg_win_pct: avg_win,
    avg_loss_pct: avg_loss,
    win_rate: wr,
    expectancy_pct: expectancy,
    avg_hold_days: avg_hold,
  };
}
