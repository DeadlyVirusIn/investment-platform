// Phase 2B — Trust metrics.
//
// Pure compute over the Decision[] log. No side effects. Powers:
//   - Today TrustBanner
//   - Per-card trust strip
//   - Report Card sections 1-8
//
// All thresholds + voice mode gating live here so consumers stay
// presentation-only.

import { listDecisions, type Decision } from './decisions';

export type Confidence = 'low' | 'medium' | 'high';

// Honesty thresholds — per ARTHOS_PHASE2_PRODUCT_EVOLUTION.md §4.4.7
export const TH_ACCURACY = 10;        // need 10 closed for accuracy number
export const TH_CALIBRATION = 5;      // per confidence bucket
export const TH_BEST_WORST = 3;       // for best/worst panels
export const TH_USER_OUTCOMES = 5;    // for "you vs hypothetical"

export interface ExpectancyBlock {
  closes: number;
  wins: number;
  losses: number;
  expired: number;
  win_rate: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  expectancy_pct: number;
  current_streak: { direction: 'win' | 'loss' | 'none'; count: number };
}

export interface CalibrationRow {
  confidence: Confidence;
  calls: number;
  closes: number;
  wins: number;
  losses: number;
  accuracy: number | null;     // null when below TH_CALIBRATION
  target: string;              // e.g. "65-75%"
}

export interface TrustMetrics {
  total_calls: number;
  total_closed: number;
  total_open: number;
  overall: ExpectancyBlock;
  by_confidence: CalibrationRow[];
  follow_rate: number;
  closed_decisions: Decision[];
  best_call?: Decision;
  worst_call?: Decision;
  // sample-size flags
  has_accuracy: boolean;
  has_best_worst: boolean;
  has_user_outcomes: boolean;
}

function isWin(d: Decision): boolean {
  return d.outcome != null && d.outcome.pnl_pct > 0;
}
function isLoss(d: Decision): boolean {
  return d.outcome != null && d.outcome.pnl_pct < 0;
}
function isExpired(d: Decision): boolean {
  return d.outcome != null && d.outcome.pnl_pct === 0;
}
function avg(nums: number[]): number {
  if (nums.length === 0) return 0;
  return nums.reduce((s, n) => s + n, 0) / nums.length;
}

function blockFor(decisions: Decision[]): ExpectancyBlock {
  const closes = decisions.filter((d) => !!d.outcome);
  const wins = closes.filter(isWin);
  const losses = closes.filter(isLoss);
  const expired = closes.filter(isExpired);
  const avgWin = avg(wins.map((d) => d.outcome!.pnl_pct));
  const avgLoss = avg(losses.map((d) => d.outcome!.pnl_pct));
  const wr = closes.length ? wins.length / closes.length : 0;
  const expectancy = wr * avgWin + (1 - wr) * avgLoss;

  // Streak — walk chronological closes from newest backward.
  const closesByTs = [...closes].sort(
    (a, b) => b.outcome!.closed_at.localeCompare(a.outcome!.closed_at),
  );
  let dir: 'win' | 'loss' | 'none' = 'none';
  let count = 0;
  for (const d of closesByTs) {
    const w = isWin(d), l = isLoss(d);
    if (!w && !l) break;
    if (dir === 'none') { dir = w ? 'win' : 'loss'; count = 1; continue; }
    if ((dir === 'win' && w) || (dir === 'loss' && l)) count++;
    else break;
  }
  return {
    closes: closes.length,
    wins: wins.length,
    losses: losses.length,
    expired: expired.length,
    win_rate: wr,
    avg_win_pct: avgWin,
    avg_loss_pct: avgLoss,
    expectancy_pct: expectancy,
    current_streak: { direction: dir, count },
  };
}

const CALIBRATION_TARGETS: Record<Confidence, string> = {
  high:   '85%+',
  medium: '65-75%',
  low:    '45-55%',
};

function calibrationRow(decisions: Decision[], c: Confidence): CalibrationRow {
  const calls = decisions.filter((d) => d.arth_confidence === c);
  const closes = calls.filter((d) => !!d.outcome);
  const wins = closes.filter(isWin);
  const losses = closes.filter(isLoss);
  const accuracy =
    closes.length >= TH_CALIBRATION
      ? wins.length / Math.max(wins.length + losses.length, 1)
      : null;
  return {
    confidence: c,
    calls: calls.length,
    closes: closes.length,
    wins: wins.length,
    losses: losses.length,
    accuracy,
    target: CALIBRATION_TARGETS[c],
  };
}

export function computeTrustMetrics(): TrustMetrics {
  const decisions = listDecisions();
  // "calls" = anything Arth recommended that the user acted on or
  // skipped on — held_cash is a recommendation outcome too.
  const calls = decisions.filter(
    (d) =>
      d.action === 'paper_traded' ||
      d.action === 'followed' ||
      d.action === 'skipped',
  );
  const closed = decisions.filter((d) => !!d.outcome);
  const open = decisions.filter(
    (d) => (d.action === 'paper_traded' || d.action === 'followed') && !d.outcome,
  );
  const overall = blockFor(decisions);
  const by_confidence: CalibrationRow[] = [
    calibrationRow(decisions, 'high'),
    calibrationRow(decisions, 'medium'),
    calibrationRow(decisions, 'low'),
  ];

  const follows = decisions.filter(
    (d) => d.action === 'paper_traded' || d.action === 'followed',
  );
  const follow_rate = calls.length ? follows.length / calls.length : 0;

  // Best/worst — only if we have at least TH_BEST_WORST closes
  const closesByPnl = [...closed].sort(
    (a, b) => (b.outcome!.pnl_pct) - (a.outcome!.pnl_pct),
  );
  const best_call =
    closed.length >= TH_BEST_WORST ? closesByPnl[0] : closesByPnl[0];
  const worst_call =
    closed.length >= TH_BEST_WORST
      ? closesByPnl[closesByPnl.length - 1]
      : undefined;

  return {
    total_calls: calls.length,
    total_closed: closed.length,
    total_open: open.length,
    overall,
    by_confidence,
    follow_rate,
    closed_decisions: closed,
    best_call,
    worst_call,
    has_accuracy: closed.length >= TH_ACCURACY,
    has_best_worst: closed.length >= TH_BEST_WORST,
    has_user_outcomes: closed.length >= TH_USER_OUTCOMES,
  };
}

/** Voice-aware accuracy phrase — used on TrustBanner. */
export function accuracyPhrase(m: TrustMetrics): string {
  if (m.total_closed === 0) {
    return `${m.total_calls} call${m.total_calls === 1 ? '' : 's'} so far — none closed yet.`;
  }
  if (!m.has_accuracy) {
    return `${m.total_closed} closed call${m.total_closed === 1 ? '' : 's'} so far — too early to claim accuracy.`;
  }
  const pct = Math.round(m.overall.win_rate * 100);
  return `Last 30 days: ${m.overall.closes} closes · ${m.overall.wins} wins · ${m.overall.losses} losses · accuracy ${pct}%`;
}

/** Voice-aware expectancy phrase — used on TrustBanner + Report Card. */
export function expectancyPhrase(m: TrustMetrics): string {
  if (m.total_closed === 0) return '';
  const e = m.overall.expectancy_pct;
  const sign = e > 0 ? '+' : '';
  return `Expectancy ${sign}${e.toFixed(2)}% per call`;
}
