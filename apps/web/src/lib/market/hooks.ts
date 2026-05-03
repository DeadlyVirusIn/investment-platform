// Phase UI-TICKER — market quote hook.
// Stub with seeded snapshot + polled jitter so ticker feels alive.
// Swap queryFn with apiGet<"/market/quotes">(…) once backend endpoint lands.

import { useQuery } from "@tanstack/react-query";

export interface Quote {
  symbol: string;
  label: string;
  price: number;
  change: number;
  changePct: number;
  history?: number[];   // last ~24 points for sparkline (optional)
}

// Symbols that get a sparkline in the ticker
export const SPARK_SYMBOLS = new Set(["SPX", "VIX", "SPY", "QQQ"]);

// Reasonable 2026-ish snapshot anchors. Purely for visual fidelity — the
// app never uses these for trading decisions.
const SEEDS: Record<string, { label: string; base: number; vol: number }> = {
  SPX:  { label: "S&P 500", base: 5312.44,  vol: 0.006 },
  DJI:  { label: "Dow",     base: 39826.10, vol: 0.006 },
  NDX:  { label: "Nasdaq",  base: 18541.30, vol: 0.009 },
  VIX:  { label: "VIX",     base: 14.82,    vol: 0.025 },
  TNX:  { label: "10Y",     base: 4.284,    vol: 0.005 },
  SPY:  { label: "SPY",     base: 529.12,   vol: 0.006 },
  QQQ:  { label: "QQQ",     base: 451.78,   vol: 0.008 },
  AAPL: { label: "AAPL",    base: 212.34,   vol: 0.010 },
  MSFT: { label: "MSFT",    base: 424.90,   vol: 0.009 },
  NVDA: { label: "NVDA",    base: 930.42,   vol: 0.018 },
  AMZN: { label: "AMZN",    base: 184.10,   vol: 0.012 },
  META: { label: "META",    base: 491.80,   vol: 0.013 },
  TSLA: { label: "TSLA",    base: 176.75,   vol: 0.022 },
};

// Daily-open baselines so change/change% are deterministic per session day.
// Random daily drift from base, fixed after first read.
const dailyOpens: Record<string, number> = {};

function dailyOpenFor(sym: string): number {
  if (dailyOpens[sym] !== undefined) return dailyOpens[sym];
  const seed = SEEDS[sym];
  if (!seed) return 0;
  const drift = (Math.random() - 0.5) * seed.vol * 0.8;
  const open = seed.base * (1 + drift);
  dailyOpens[sym] = open;
  return open;
}

// Cached spark history per symbol, appended each refresh.
const sparkHistory: Record<string, number[]> = {};
const SPARK_MAX = 24;

function snapshotFor(sym: string): Quote {
  const seed = SEEDS[sym];
  if (!seed) return { symbol: sym, label: sym, price: 0, change: 0, changePct: 0 };
  const open = dailyOpenFor(sym);
  const intra = (Math.random() - 0.5) * seed.vol;
  const price = open * (1 + intra);
  const change = price - open;
  const changePct = (change / open) * 100;

  // Seed + rolling spark history
  let history: number[] | undefined;
  if (SPARK_SYMBOLS.has(sym)) {
    if (!sparkHistory[sym]) {
      // Prime with backfilled random walk anchored to open
      const backfill: number[] = [];
      let v = open * (1 + (Math.random() - 0.5) * seed.vol);
      for (let i = 0; i < SPARK_MAX - 1; i++) {
        v = v * (1 + (Math.random() - 0.5) * seed.vol * 0.6);
        backfill.push(v);
      }
      sparkHistory[sym] = backfill;
    }
    sparkHistory[sym].push(price);
    if (sparkHistory[sym].length > SPARK_MAX) {
      sparkHistory[sym] = sparkHistory[sym].slice(-SPARK_MAX);
    }
    history = [...sparkHistory[sym]];
  }

  return {
    symbol: sym, label: seed.label,
    price, change, changePct,
    history,
  };
}

function buildSnapshot(symbols: string[]): Quote[] {
  return symbols.map(snapshotFor);
}

export function useMarketQuotes(symbols: string[]) {
  const key = symbols.join(",");
  return useQuery<Quote[]>({
    queryKey: ["market", "quotes", key],
    queryFn: async () => {
      // Tiny timeout to feel fetched. Replace with real API once wired.
      await new Promise(r => setTimeout(r, 60));
      return buildSnapshot(symbols);
    },
    initialData: () => buildSnapshot(symbols),
    refetchInterval: 8000,
    staleTime: 4000,
    refetchOnWindowFocus: false,
  });
}
