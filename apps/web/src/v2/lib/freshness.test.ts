// Truthful freshness mapping — audit C1 regression guard: the label must
// always agree with the calendar, never claim "today" for older data.

import { describe, it, expect, vi, afterEach } from 'vitest';
import { freshnessInfo } from './freshness';

const NOW = new Date('2026-07-12T10:00:00');

function withNow<T>(fn: () => T): T {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  try { return fn(); } finally { vi.useRealTimers(); }
}

afterEach(() => vi.useRealTimers());

describe('freshnessInfo', () => {
  it('same calendar day → "Updated today", good tone', () => {
    withNow(() => {
      const f = freshnessInfo('2026-07-12T01:00:00');
      expect(f.label).toBe('Updated today');
      expect(f.tone).toBe('good');
      expect(f.ageDays).toBe(0);
    });
  });

  it('yesterday → "Updated yesterday" (the C1 bug: was "updated today" ≤30h)', () => {
    withNow(() => {
      const f = freshnessInfo('2026-07-11T23:42:00');
      expect(f.label).toBe('Updated yesterday');
      expect(f.tone).toBe('good');
      expect(f.ageDays).toBe(1);
    });
  });

  it('multi-day age → explicit day count with warn tone', () => {
    withNow(() => {
      const f = freshnessInfo('2026-07-08T12:00:00');
      expect(f.label).toBe('Updated 4 days ago');
      expect(f.tone).toBe('warn');
    });
  });

  it('backend stale flag forces warn tone even same-day', () => {
    withNow(() => {
      expect(freshnessInfo('2026-07-12T01:00:00', true).tone).toBe('warn');
    });
  });

  it('missing/invalid timestamps are never claimed fresh', () => {
    expect(freshnessInfo(null).label).toBe('Timing unavailable');
    expect(freshnessInfo(null).tone).toBe('warn');
    expect(freshnessInfo('not-a-date').tone).toBe('warn');
  });
});
