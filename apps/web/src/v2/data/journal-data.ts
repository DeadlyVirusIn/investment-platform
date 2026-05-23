// Decision Journal data — ported from wise-start-bloom (Phase 1, Lovable port).
// Verbatim content + types. Journal surface (index + entry pages) is deferred
// to Phase 6; this file exists so SixStepRibbon, GlossaryPopover, and future
// cross-links have stable references to import.

export type DecisionStep = "Idea" | "Thesis" | "Catalyst" | "Position" | "Outcome" | "Lesson";

export type Catalyst = {
  date: string; // e.g. "Jun 4"
  label: string;
  type: "earnings" | "macro" | "product" | "guidance";
  windowDays: number;
};

export type ThesisClaim = {
  text: string;
  confidence: "high" | "medium" | "low";
  evidence?: string;
};

export type AcademyTag = "Stocks" | "Options" | "Risk" | "AI Portfolio";

export type JournalEntry = {
  id: string;
  ticker: string;
  company: string;
  headline: string;
  summary: string;
  publishedAt: string; // human-readable
  publishedAtIso: string;
  currentStep: DecisionStep;
  status: "active" | "resolved" | "mistake";
  outcome?: { change: number; note: string }; // % change
  thesisClaims: ThesisClaim[];
  catalysts: Catalyst[];
  sizing: { weightPct: number; rationale: string };
  lesson: string;
  academies: AcademyTag[];
  risk: "low" | "medium" | "high";
};

export const journalEntries: JournalEntry[] = [
  {
    id: "trim-semis-cluster",
    ticker: "NVDA",
    company: "Nvidia Corporation",
    headline: "Trimmed semis exposure ahead of the earnings cluster",
    summary:
      "Concentration in a single sector going into three back-to-back prints is more risk than the setup compensates for. Took position from 8% to 4.5%.",
    publishedAt: "Today, 9:42",
    publishedAtIso: "2026-05-22T09:42:00Z",
    currentStep: "Position",
    status: "active",
    thesisClaims: [
      {
        text: "Hyperscaler capex commentary remains the dominant driver into year-end.",
        confidence: "high",
        evidence: "Last three guides re-rated peers ±9% on average.",
      },
      {
        text: "Implied move pricing is at the 78th percentile of the last 12 months — premium is rich.",
        confidence: "medium",
        evidence: "Straddle implies ~7.4% vs realized 4.9% trailing 30d.",
      },
      {
        text: "Trimming reduces single-sector concentration, not directional view.",
        confidence: "high",
      },
    ],
    catalysts: [
      { date: "May 28", label: "Nvidia FQ1 earnings", type: "earnings", windowDays: 6 },
      { date: "May 29", label: "AMD analyst day", type: "guidance", windowDays: 7 },
      { date: "Jun 4", label: "PCE inflation print", type: "macro", windowDays: 13 },
    ],
    sizing: {
      weightPct: 4.5,
      rationale:
        "Half-position keeps directional exposure without exceeding 5% per-name risk into the cluster.",
    },
    lesson:
      "When you can't separate conviction from concentration, the right move is almost always to size down — not out.",
    academies: ["Stocks", "Risk", "AI Portfolio"],
    risk: "medium",
  },
  {
    id: "energy-rotation",
    ticker: "XLE",
    company: "Energy Select SPDR",
    headline: "Started a quarter-position in energy on the basis trade",
    summary:
      "Crude inventories tightening into driving season while refiners trail the move. Small starter, scale on confirmation.",
    publishedAt: "Yesterday, 16:10",
    publishedAtIso: "2026-05-21T16:10:00Z",
    currentStep: "Catalyst",
    status: "active",
    thesisClaims: [
      {
        text: "Crack spreads have widened 12% in two weeks without follow-through in equities.",
        confidence: "high",
      },
      {
        text: "Positioning data shows energy at a 3-year underweight.",
        confidence: "medium",
        evidence: "CFTC commitment of traders, prior 3 cycles.",
      },
    ],
    catalysts: [
      { date: "May 24", label: "EIA inventory report", type: "macro", windowDays: 2 },
      { date: "Jun 2", label: "OPEC+ meeting", type: "macro", windowDays: 11 },
    ],
    sizing: {
      weightPct: 2,
      rationale: "Quarter-position — proves the thesis cheaply. Doubles on a second confirming inventory print.",
    },
    lesson:
      "Starter positions buy you the right to be wrong twice before you have to defend the call.",
    academies: ["Stocks", "Risk"],
    risk: "low",
  },
  {
    id: "regional-banks-failed",
    ticker: "KRE",
    company: "Regional Banks ETF",
    headline: "Closed regional banks long — thesis didn't survive the print",
    summary:
      "Bet on net interest margin recovery. Deposit cost commentary on the call moved the wrong way. Out flat.",
    publishedAt: "May 18",
    publishedAtIso: "2026-05-18T18:00:00Z",
    currentStep: "Lesson",
    status: "mistake",
    outcome: { change: -0.2, note: "Closed near entry — thesis broken, not stop-hit." },
    thesisClaims: [
      {
        text: "Higher-for-longer rates would re-price NIM upward across the regional cohort.",
        confidence: "high",
      },
      {
        text: "Deposit costs would lag — providing a 1–2 quarter tailwind.",
        confidence: "medium",
      },
    ],
    catalysts: [{ date: "May 16", label: "Regional banks earnings cluster", type: "earnings", windowDays: 0 }],
    sizing: { weightPct: 3, rationale: "Sized for a multi-quarter hold." },
    lesson:
      "When the second-order assumption breaks (deposit costs lagging), exit on the catalyst — don't wait for the price to confirm what the call already said.",
    academies: ["Stocks", "Risk", "AI Portfolio"],
    risk: "medium",
  },
];

export function getEntry(id: string) {
  return journalEntries.find((e) => e.id === id);
}

export const mistakes = journalEntries.filter((e) => e.status === "mistake");
export const activeEntries = journalEntries.filter((e) => e.status === "active");

// Opportunities derive from journal entries — never standalone.
export type Opportunity = {
  id: string;
  journalId: string;
  ticker: string;
  thesis: string;
  edge: string;
  daysToCatalyst: number;
  risk: "low" | "medium" | "high";
  academies: AcademyTag[];
};

export const opportunities: Opportunity[] = [
  {
    id: "opp-nvda-straddle",
    journalId: "trim-semis-cluster",
    ticker: "NVDA",
    thesis: "Trim exposure, don't reverse — concentration > conviction.",
    edge: "Implied move at 78th percentile makes premium-selling the cleaner expression.",
    daysToCatalyst: 6,
    risk: "medium",
    academies: ["Options", "Risk"],
  },
  {
    id: "opp-xle-starter",
    journalId: "energy-rotation",
    ticker: "XLE",
    thesis: "Crack spreads widened without equity follow-through.",
    edge: "Quarter-position with a clear add-on trigger on EIA print.",
    daysToCatalyst: 2,
    risk: "low",
    academies: ["Stocks"],
  },
];
