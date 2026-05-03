// Shared selector hook: resolves the "active" paper portfolio id,
// persisting the user's choice across reloads/navigation.

import { useCallback, useEffect, useState } from 'react';
import type { PortfolioSummary } from '@/types';
import {
  clearSelectedPortfolioId,
  getSelectedPortfolioId,
  setSelectedPortfolioId,
} from './storage';

interface Result {
  selectedId: string | null;
  /** Returns the id that should actually be used (falls back to first if
   * stored id is stale or missing). */
  activeId: string | null;
  /** Persist the user's choice. */
  setId: (id: string) => void;
  /** Forget any saved choice. */
  clear: () => void;
}

export function useSelectedPortfolio(portfolios: PortfolioSummary[] | undefined): Result {
  const [selectedId, setSelectedIdState] = useState<string | null>(() => getSelectedPortfolioId());

  // If the saved id no longer corresponds to any portfolio, drop it.
  useEffect(() => {
    if (!portfolios || portfolios.length === 0) return;
    if (selectedId && !portfolios.some(p => p.id === selectedId)) {
      clearSelectedPortfolioId();
      setSelectedIdState(null);
    }
  }, [portfolios, selectedId]);

  const setId = useCallback((id: string) => {
    setSelectedPortfolioId(id);
    setSelectedIdState(id);
  }, []);

  const clear = useCallback(() => {
    clearSelectedPortfolioId();
    setSelectedIdState(null);
  }, []);

  const activeId =
    selectedId && portfolios?.some(p => p.id === selectedId)
      ? selectedId
      : portfolios?.[0]?.id ?? null;

  return { selectedId, activeId, setId, clear };
}
