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

// --- Raw-key variants (no prefix) ---
// For PRE-EXISTING stores whose keys shipped before the prefix convention
// (operator flag, device id, one-time explainer flags). Concentrating them
// here keeps the frozen localStorage surface auditable in one file; new
// stores must use the prefixed helpers above.

export function lsGetRaw(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function lsSetRaw(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
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
