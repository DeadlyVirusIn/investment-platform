import { describe, expect, it } from 'vitest';
import { isNavPathActive, isPortfolioNavActive } from './ArthosChrome';

describe('isPortfolioNavActive', () => {
  it('matches the portfolio route as a path segment, not a prefix', () => {
    expect(isPortfolioNavActive('/portfolio')).toBe(true);
    expect(isPortfolioNavActive('/portfolio/activity')).toBe(true);
    expect(isPortfolioNavActive('/portfolios/model-growth')).toBe(false);
  });

  it.each(['/try', '/try/a-lesson', '/track-record', '/track-record/detail'])(
    'matches portfolio-adjacent route segments (%s)',
    (path) => {
      const route = path.startsWith('/try') ? '/try' : '/track-record';
      expect(isNavPathActive(path, route)).toBe(true);
    },
  );

  it.each(['/trying', '/tryout', '/track-records', '/track-recording'])(
    'does not prefix-match unrelated routes (%s)',
    (path) => {
      const route = path.startsWith('/try') ? '/try' : '/track-record';
      expect(isNavPathActive(path, route)).toBe(false);
    },
  );
});