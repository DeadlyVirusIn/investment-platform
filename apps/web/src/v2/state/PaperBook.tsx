// V2 paper book — $100k virtual cash, positions, history.
// Storage key "v2-paper-book" isolated from any existing paper state.

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  createContext,
  useContext,
  type ReactNode,
} from 'react';
import type { Recommendation } from '../data/arthosData';

const STARTING_CASH = 100000;
const STORAGE_KEY = 'v2-paper-book';

export type Side = 'long' | 'short' | 'long-option' | 'short-option';

export interface PaperPosition {
  id: string;
  recId: string;
  symbol: string;
  kind: 'stock' | 'option';
  actionLabel: string;
  contract?: string;
  side: Side;
  quantity: number;
  entryPrice: number;
  currentPrice: number;
  multiplier: number;
  costBasis: number;
  maxLossPerContract?: number;
  target?: string;
  invalidate?: string;
  openedAt: number;
  // UX Phase 3A — optional pointer back to the lesson that produced
  // this trade. Set by /v2/try/:lessonSlug when openFromRec is called.
  // Existing positions without it continue loading fine.
  originLessonSlug?: string;
}

export interface PaperHistoryEntry {
  id: string;
  symbol: string;
  actionLabel: string;
  pnl: number;
  pnlPct: number;
  daysHeld: number;
  closedAt: number;
  // UX Phase 3A — carried over from PaperPosition on close so the
  // learning-loop chain on /v2/me and /v2/learn/lesson/:slug can show
  // outcomes alongside the lessons that produced them.
  originLessonSlug?: string;
}

interface PaperBookState {
  cash: number;
  positions: PaperPosition[];
  history: PaperHistoryEntry[];
}

const DEFAULT_STATE: PaperBookState = {
  cash: STARTING_CASH,
  positions: [],
  history: [],
};

interface PaperBookValue extends PaperBookState {
  startingCash: number;
  bookValue: number;
  unrealizedPnL: number;
  realizedPnL: number;
  openFromRec: (
    rec: Recommendation,
    quantity?: number,
    originLessonSlug?: string,
  ) => { ok: boolean; reason?: string };
  closePosition: (id: string) => void;
  resetBook: () => void;
}

const PaperBookContext = createContext<PaperBookValue | undefined>(undefined);

function load(): PaperBookState {
  if (typeof window === 'undefined') return DEFAULT_STATE;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_STATE;
    return { ...DEFAULT_STATE, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_STATE;
  }
}

function save(state: PaperBookState) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* noop */
  }
}

export function pnlForPosition(p: PaperPosition): number {
  const delta = p.currentPrice - p.entryPrice;
  switch (p.side) {
    case 'long':
      return delta * p.quantity;
    case 'short':
      return -delta * p.quantity;
    case 'long-option':
      return delta * p.quantity * p.multiplier;
    case 'short-option':
      return -delta * p.quantity * p.multiplier;
  }
}

export function pnlPctForPosition(p: PaperPosition): number {
  const pnl = pnlForPosition(p);
  if (p.costBasis === 0) return 0;
  return (pnl / p.costBasis) * 100;
}

export function PaperBookProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PaperBookState>(() => load());

  useEffect(() => {
    save(state);
  }, [state]);

  useEffect(() => {
    if (state.positions.length === 0) return;
    const id = setInterval(() => {
      setState((prev) => ({
        ...prev,
        positions: prev.positions.map((p) => {
          const bias =
            p.side === 'long' || p.side === 'long-option' ? 0.0008 : -0.0008;
          const noise = (Math.random() - 0.5) * 0.008;
          const factor = 1 + bias + noise;
          const next = Math.max(0.01, p.currentPrice * factor);
          return { ...p, currentPrice: parseFloat(next.toFixed(4)) };
        }),
      }));
    }, 15000);
    return () => clearInterval(id);
  }, [state.positions.length]);

  const openFromRec = useCallback(
    (
      rec: Recommendation,
      quantityOverride?: number,
      originLessonSlug?: string,
    ) => {
      if (!rec.placeable || !rec.side || rec.entryPrice === undefined) {
        return {
          ok: false,
          reason: 'This idea cannot be placed as a new position.',
        };
      }
      const quantity = quantityOverride ?? rec.defaultQuantity ?? 1;
      if (quantity <= 0)
        return { ok: false, reason: 'Quantity must be at least 1.' };
      const multiplier = rec.kind === 'option' ? 100 : 1;
      let cashRequired: number;
      if (rec.side === 'long' || rec.side === 'short') {
        cashRequired = rec.entryPrice * quantity;
      } else if (rec.side === 'long-option') {
        cashRequired = rec.entryPrice * quantity * multiplier;
      } else {
        cashRequired =
          (rec.maxLossPerContract ?? rec.entryPrice * multiplier) * quantity;
      }
      if (cashRequired > state.cash + 0.0001) {
        return { ok: false, reason: 'Not enough cash in the paper book.' };
      }
      const initialBias =
        rec.side === 'long' || rec.side === 'long-option' ? 0.001 : -0.001;
      const initialNoise = (Math.random() - 0.5) * 0.004;
      const currentPrice = parseFloat(
        (rec.entryPrice * (1 + initialBias + initialNoise)).toFixed(4)
      );
      const position: PaperPosition = {
        id: `pos-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        recId: `${rec.symbol}-${rec.kind}`,
        symbol: rec.symbol,
        kind: rec.kind,
        actionLabel: rec.actionLabel,
        contract: rec.contract,
        side: rec.side,
        quantity,
        entryPrice: rec.entryPrice,
        currentPrice,
        multiplier,
        costBasis: cashRequired,
        maxLossPerContract: rec.maxLossPerContract,
        target: rec.target,
        invalidate: rec.invalidate,
        openedAt: Date.now(),
        originLessonSlug: originLessonSlug ?? rec.lessonSlug,
      };
      setState((prev) => ({
        ...prev,
        cash: prev.cash - cashRequired,
        positions: [...prev.positions, position],
      }));
      return { ok: true };
    },
    [state.cash]
  );

  const closePosition = useCallback((id: string) => {
    setState((prev) => {
      const p = prev.positions.find((x) => x.id === id);
      if (!p) return prev;
      const pnl = pnlForPosition(p);
      const pnlPct = pnlPctForPosition(p);
      const daysHeld = Math.max(
        0,
        Math.floor((Date.now() - p.openedAt) / (1000 * 60 * 60 * 24))
      );
      const cashReturned = p.costBasis + pnl;
      const entry: PaperHistoryEntry = {
        id: p.id,
        symbol: p.symbol,
        actionLabel: p.actionLabel,
        pnl,
        pnlPct,
        daysHeld,
        closedAt: Date.now(),
        originLessonSlug: p.originLessonSlug,
      };
      return {
        ...prev,
        cash: prev.cash + cashReturned,
        positions: prev.positions.filter((x) => x.id !== id),
        history: [entry, ...prev.history],
      };
    });
  }, []);

  const resetBook = useCallback(() => {
    setState(DEFAULT_STATE);
  }, []);

  const value = useMemo<PaperBookValue>(() => {
    const positionsValue = state.positions.reduce(
      (sum, p) => sum + p.costBasis + pnlForPosition(p),
      0
    );
    const bookValue = state.cash + positionsValue;
    const unrealizedPnL = state.positions.reduce(
      (sum, p) => sum + pnlForPosition(p),
      0
    );
    const realizedPnL = state.history.reduce((sum, h) => sum + h.pnl, 0);
    return {
      ...state,
      startingCash: STARTING_CASH,
      bookValue,
      unrealizedPnL,
      realizedPnL,
      openFromRec,
      closePosition,
      resetBook,
    };
  }, [state, openFromRec, closePosition, resetBook]);

  return (
    <PaperBookContext.Provider value={value}>
      {children}
    </PaperBookContext.Provider>
  );
}

export function usePaperBook() {
  const ctx = useContext(PaperBookContext);
  if (!ctx) throw new Error('usePaperBook must be used within PaperBookProvider');
  return ctx;
}
