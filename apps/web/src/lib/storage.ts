// Tiny wrappers around localStorage. Defensive: treats any throw (Safari
// private mode, SSR, etc.) as "no storage" and returns safe defaults.

const PREFIX = 'investiq:';

export function lsGet(key: string): string | null {
  try {
    return localStorage.getItem(PREFIX + key);
  } catch {
    return null;
  }
}

export function lsSet(key: string, value: string): void {
  try {
    localStorage.setItem(PREFIX + key, value);
  } catch {
    /* noop */
  }
}

export function lsRemove(key: string): void {
  try {
    localStorage.removeItem(PREFIX + key);
  } catch {
    /* noop */
  }
}

// --- Selected paper portfolio helpers ---

const SELECTED_PORTFOLIO_KEY = 'selected_portfolio_id';

export function getSelectedPortfolioId(): string | null {
  return lsGet(SELECTED_PORTFOLIO_KEY);
}

export function setSelectedPortfolioId(id: string): void {
  lsSet(SELECTED_PORTFOLIO_KEY, id);
}

export function clearSelectedPortfolioId(): void {
  lsRemove(SELECTED_PORTFOLIO_KEY);
}
