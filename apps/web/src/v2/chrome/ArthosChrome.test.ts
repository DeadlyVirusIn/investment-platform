import { describe, expect, it } from 'vitest';
import { isPortfolioNavActive } from './ArthosChrome';

describe('isPortfolioNavActive', () => {
  it('matches the portfolio route as a path segment, not a prefix', () => {
    expect(isPortfolioNavActive('/portfolio')).toBe(true);
    expect(isPortfolioNavActive('/portfolio/activity')).toBe(true);
    expect(isPortfolioNavActive('/portfolios/model-growth')).toBe(false);
  });
});