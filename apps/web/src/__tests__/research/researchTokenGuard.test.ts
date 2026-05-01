// Phase 11W (Phase B) — client-side fail-closed token-guard tests.
//
// NOTE: Vitest is not yet installed in apps/web/package.json. These
// tests are written in vitest format and will execute as soon as
// vitest is added. They are intentionally framework-light so they
// can be ported to jest/RTL with no edits.

import { describe, it, expect } from 'vitest';
import {
  RESEARCH_BANNER_TEXT,
  scanForbiddenTokens,
} from '../../lib/research/forbiddenTokens';

describe('research token guard', () => {
  it('passes for empty / safe text', () => {
    expect(scanForbiddenTokens('').ok).toBe(true);
    expect(
      scanForbiddenTokens(
        'Narrative analysis of the firms operating environment.',
      ).ok,
    ).toBe(true);
  });

  it.each([
    ['buy', 'we should buy this asset'],
    ['sell', 'consider sell pressure here'],
    ['hold', 'we should hold the line'],
    ['recommend', 'we recommend caution'],
    ['signal', 'a strong signal of weakness'],
    ['allocate', 'we would allocate more'],
    ['execute', 'execute the plan now'],
    ['position', 'enter a position here'],
    ['leverage', 'leverage is too high'],
    ['outperform', 'this could outperform peers'],
  ])('rejects forbidden word: %s', (token, body) => {
    const r = scanForbiddenTokens(body);
    expect(r.ok).toBe(false);
    expect(r.matched?.toLowerCase()).toContain(token);
  });

  it.each([
    'target price of $200',
    'set a stop loss at the low',
    'take profit at resistance',
    'the portfolio manager will decide',
    'copy trade from the top performer',
    'best trade of the year',
    'trade now to capture',
  ])('rejects forbidden phrase: %s', (body) => {
    expect(scanForbiddenTokens(body).ok).toBe(false);
  });

  it.each([
    'household income trends are stable',
    'longitude of the asset basket spans EU',
    'shortlist of candidate tickers',
  ])('allows substring false-positive: %s', (body) => {
    expect(scanForbiddenTokens(body).ok).toBe(true);
  });

  it('exports the frozen banner text', () => {
    expect(RESEARCH_BANNER_TEXT).toContain('Research note');
    expect(RESEARCH_BANNER_TEXT).toContain('not execution logic');
    expect(RESEARCH_BANNER_TEXT).toContain('not financial advice');
  });
});
