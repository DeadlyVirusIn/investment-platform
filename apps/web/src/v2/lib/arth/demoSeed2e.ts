// Phase 2E — Demo seed for Mentor Profile capture.
//
// Provides enough observations across reflections + decisions +
// patterns so every section of the Mentor Profile has populated
// content. Without seed: all sections render their honesty-mode
// "Too early to tell." copy.

import { KEYS, writeVersioned } from './storage';
import type { Decision } from './decisions';
import type { ArthEvent } from './events';
import type { MemoryNote } from './memory';
import { scanPatterns } from './patternEngine';

export function seed2eMentorDemo(): void {
  const now = Date.now();

  // ── Decisions — 18 total: 8 closed (5 wins/3 losses), 5 follows
  // open, 5 skipped, with varied reasons.
  const decisions: Decision[] = [];
  const closedWins = [
    ['AAPL', 1.4, 8], ['MSFT', 2.1, 6], ['XLE', 1.2, 6],
    ['GOOGL', 0.6, 5], ['SPY', 0.8, 14],
  ] as const;
  const closedLosses = [
    ['NVDA', -2.4, 4], ['META', -1.8, 3], ['AMD', -2.6, 5],
  ] as const;
  const opens = ['COST', 'V', 'WFC', 'BAC', 'XOM'] as const;
  const skips = [
    ['TSLA', 'Earnings risk'], ['JPM', 'Earnings risk'],
    ['WMT', 'Earnings risk'], ['BA', 'Bad timing'],
    ['HD', 'Bad timing'],
  ] as const;

  let i = 0;
  for (const [s, pnl, days] of closedWins) {
    const ts = new Date(now - (30 - i++) * 86_400_000).toISOString();
    decisions.push({
      id: `s2e-${s}`,
      rec_id: s,
      symbol: s,
      action: 'paper_traded',
      thesis_snapshot: `${s} setup — closed +${pnl.toFixed(1)}%.`,
      ts,
      cohort: 'long_call_spread_low_iv',
      arth_confidence: 'medium',
      outcome: {
        closed_at: new Date(new Date(ts).getTime() + days * 86_400_000).toISOString(),
        pnl_pct: pnl,
        days_held: days,
        arth_was_right: pnl > 0,
      },
    });
  }
  for (const [s, pnl, days] of closedLosses) {
    const ts = new Date(now - (24 - i++) * 86_400_000).toISOString();
    decisions.push({
      id: `s2e-${s}`,
      rec_id: s,
      symbol: s,
      action: 'paper_traded',
      thesis_snapshot: `${s} setup — closed ${pnl.toFixed(1)}%.`,
      ts,
      cohort: 'long_call_outright',
      arth_confidence: 'medium',
      outcome: {
        closed_at: new Date(new Date(ts).getTime() + days * 86_400_000).toISOString(),
        pnl_pct: pnl,
        days_held: days,
        arth_was_right: pnl > 0,
      },
    });
  }
  for (const s of opens) {
    decisions.push({
      id: `s2e-${s}`,
      rec_id: s,
      symbol: s,
      action: 'paper_traded',
      thesis_snapshot: `${s} thesis open.`,
      ts: new Date(now - (10 - opens.indexOf(s)) * 86_400_000).toISOString(),
      cohort: 'directional_long_stock',
      arth_confidence: 'medium',
    });
  }
  for (const [s, reason] of skips) {
    decisions.push({
      id: `s2e-skip-${s}`,
      rec_id: s,
      symbol: s,
      action: 'skipped',
      skip_reason: reason,
      thesis_snapshot: `${s} skipped.`,
      ts: new Date(now - (12 - skips.findIndex(([x]) => x === s)) * 86_400_000).toISOString(),
      cohort: 'long_call_spread_low_iv',
      arth_confidence: 'low',
    });
  }
  writeVersioned(KEYS.decisions, decisions);

  // ── Events — reflections + concept taps so strengths fire.
  const events: ArthEvent[] = [];
  for (let k = 0; k < 8; k++) {
    events.push({
      id: `s2e-evt-refl-${k}`,
      ts: new Date(now - (20 - k * 2) * 86_400_000).toISOString(),
      chapter: 'reflect',
      kind: 'reflection_written',
      entity: closedWins[k % closedWins.length][0],
    });
  }
  // Same-day reflections on followed trades — drives the
  // "reflect at decision" strength.
  for (const d of decisions.slice(0, 6)) {
    if (d.action !== 'paper_traded') continue;
    events.push({
      id: `s2e-evt-refl-decision-${d.symbol}`,
      ts: new Date(new Date(d.ts).getTime() + 3 * 3600_000).toISOString(),
      chapter: 'reflect',
      kind: 'reflection_written',
      entity: d.symbol,
    });
  }
  // Lesson opens for competence map population.
  for (const slug of ['earnings_risk', 'iv_crush', 'cut_winners_early']) {
    events.push({
      id: `s2e-evt-lesson-${slug}`,
      ts: new Date(now - 4 * 86_400_000).toISOString(),
      chapter: 'learn',
      kind: 'lesson_opened',
      entity: slug,
      meta: { tier: 'lesson' },
    });
  }
  writeVersioned(KEYS.events, events);

  // ── Memory — declared (told_me) + a couple observed.
  const memory: MemoryNote[] = [
    {
      id: 's2e-mem-1',
      category: 'told_me',
      text: 'You told me your level is "beginner".',
      source: 'onboarding',
      pinned: true,
      ts: new Date(now - 30 * 86_400_000).toISOString(),
    },
    {
      id: 's2e-mem-2',
      category: 'told_me',
      text: 'You picked these interests: semis, energy.',
      source: 'onboarding',
      pinned: true,
      ts: new Date(now - 30 * 86_400_000).toISOString(),
    },
    {
      id: 's2e-mem-3',
      category: 'told_me',
      text: 'You said you read around 8:00pm.',
      source: 'onboarding',
      ts: new Date(now - 30 * 86_400_000).toISOString(),
    },
    {
      id: 's2e-mem-4',
      category: 'seen',
      text: 'You opened a paper trade on AAPL.',
      source: 'decision',
      ts: new Date(now - 8 * 86_400_000).toISOString(),
    },
    {
      id: 's2e-mem-5',
      category: 'seen',
      text: 'You wrote a one-line reflection when opening MSFT.',
      source: 'reflection',
      ts: new Date(now - 6 * 86_400_000).toISOString(),
    },
  ];
  writeVersioned(KEYS.memory, memory);

  // ── Competence — drives the competence map section.
  // Use the lesson-opened events above to derive read status.
  const competence = [
    { lesson_slug: 'earnings_risk', status: 'learned',
      first_encountered_at: new Date(now - 5 * 86_400_000).toISOString(),
      read_at: new Date(now - 4 * 86_400_000).toISOString(),
      learned_at: new Date(now - 4 * 86_400_000).toISOString(),
      recall_count: 0 },
    { lesson_slug: 'iv_crush', status: 'read',
      first_encountered_at: new Date(now - 6 * 86_400_000).toISOString(),
      read_at: new Date(now - 4 * 86_400_000).toISOString(),
      recall_count: 0 },
    { lesson_slug: 'cut_winners_early', status: 'read',
      first_encountered_at: new Date(now - 4 * 86_400_000).toISOString(),
      read_at: new Date(now - 4 * 86_400_000).toISOString(),
      recall_count: 0 },
    { lesson_slug: 'why_stops_exist', status: 'encountered',
      first_encountered_at: new Date(now - 3 * 86_400_000).toISOString(),
      recall_count: 0 },
  ];
  writeVersioned(`${KEYS.memory}.competence`, competence);

  // ── Streak — pre-populate to Day 12.
  writeVersioned(KEYS.streak, {
    current_day: 12,
    longest_day: 12,
    last_active_date: new Date(now).toISOString().slice(0, 10),
    visit_dates: Array.from({ length: 12 }, (_, k) =>
      new Date(now - k * 86_400_000).toISOString().slice(0, 10),
    ).reverse(),
    grace_remaining: 1,
  });

  // Trigger pattern scan AFTER seeding so the Patterns I'm watching
  // section has populated rows for capture. Without this call,
  // patternEngine never runs against the synthetic decisions/events.
  scanPatterns();
}
