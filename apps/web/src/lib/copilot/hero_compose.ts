// UX-9 Phase 9C — Hero card composer.
//
// Pure function. Takes engine state (positions, summary) and
// returns HeroCardProps. No fetch, no I/O, no LLM.
//
// Phase 9D-default — uses fixture data for the visual proof at
// /overview?view=stream. Real wiring to ExecutedPosition +
// PaperSummary lands when the day-1 acceptance test passes.

import type {
  HeroCardProps, PositionWeight, PositionHue,
} from "@/components/copilot/HeroCard";


export interface HeroComposeInputs {
  positions?: ReadonlyArray<{ symbol: string; weight: number }>;
  todayDeltaPct?: number;
  read?: string;
  miniObjects?: ReadonlyArray<{ label: string; value: string }>;
}


/** Deterministic hue assignment by symbol stability — same
 *  symbol always gets the same hue across sessions. Cash slot
 *  always uses the cash hue. Cap at 7 hues; cycle if >7. */
export function pickHue(symbol: string, index: number): PositionHue {
  if (symbol.toLowerCase() === "cash") return "cash";
  return ((index % 7) + 1) as PositionHue;
}


export function composeHero(inp: HeroComposeInputs): HeroCardProps {
  const positions: PositionWeight[] = (inp.positions ?? PROOF_POSITIONS)
    .map((p, i) => ({
      symbol: p.symbol,
      weight: p.weight,
      hue: pickHue(p.symbol, i),
    }));

  return {
    todayDeltaPct: inp.todayDeltaPct ?? 0.008,
    positions,
    read: inp.read ?? PROOF_READ,
    miniObjects: inp.miniObjects?.map(m => ({ ...m })) ?? PROOF_MINI,
  };
}


// ---------------------------------------------------------------
// Proof fixtures — used when no real data wired. Realistic
// weights + symbols a portfolio user would recognize.
// ---------------------------------------------------------------

export const PROOF_POSITIONS = [
  { symbol: "AAPL",  weight: 0.22 },
  { symbol: "MSFT",  weight: 0.18 },
  { symbol: "NVDA",  weight: 0.16 },
  { symbol: "GOOGL", weight: 0.13 },
  { symbol: "TSLA",  weight: 0.10 },
  { symbol: "META",  weight: 0.08 },
  { symbol: "cash",  weight: 0.13 },
] as const;

export const PROOF_READ =
  "Tech-heavy day. NVDA carrying the move; "
  + "one position approaching its target.";

export const PROOF_MINI = [
  { label: "Top mover", value: "AAPL +1.3%" },
  { label: "Lifecycle", value: "AAPL · Day 4 mature" },
  { label: "Status", value: "Near target" },
];
