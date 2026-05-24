// Phase 2D — Demo seed for contextual learning capture.
//
// Forces enough skips of the same kind to push a pattern past the
// 5-observation threshold, so TodayLessonSlot has something to surface.

import { writeVersioned, KEYS } from './storage';
import type { Decision } from './decisions';

export function seed2dPatternDemo(): void {
  const now = Date.now();
  const decisions: Decision[] = [
    // 5 earnings-risk skips — crosses the min-5 threshold for
    // avoid_earnings_setups, which lessonForPattern maps to earnings_risk.
    ...['AAPL', 'MSFT', 'GOOG', 'AMZN', 'NVDA'].map((s, i) => ({
      id: `seed2d-skip-er-${s}`,
      rec_id: s,
      symbol: s,
      action: 'skipped' as const,
      skip_reason: 'Earnings risk',
      thesis_snapshot: `${s} setup ahead of earnings.`,
      ts: new Date(now - (5 - i) * 86_400_000).toISOString(),
      cohort: 'long_call_spread_low_iv',
      arth_confidence: 'medium' as const,
    })),
  ];
  writeVersioned(KEYS.decisions, decisions);
}
