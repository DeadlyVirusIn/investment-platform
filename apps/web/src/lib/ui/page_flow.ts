// Page-flow definitions — drive narrative operating-system progression.
//
// Each page belongs to a SECTION and a STEP. SideNav uses sections to
// group items; PageChapter / NextStepCard use steps to render the
// "current chapter / next chapter" rail and the bottom CTA.

export type FlowSection = "market" | "signals" | "execution" | "portfolio" | "system";


export interface FlowStep {
  to: string;
  label: string;
  section: FlowSection;
  hot: string;
  /** Page-level narrative — WHY this page exists. */
  why: string;
  /** What the user learns / does on this page. */
  what: string;
  /** Optional natural next step in the OS chapter chain. */
  next?: string;
}


// Ordered chain — drives "next step" highlighting + cross-page CTAs.
export const FLOW: FlowStep[] = [
  // MARKET
  { to: "/overview", label: "Overview", section: "market", hot: "O",
    why: "5-second answer for the entire portfolio + what changed today.",
    what: "Snapshot, AI posture, top action, launchers into deeper pages.",
    next: "/events" },
  { to: "/events", label: "Events & Catalysts", section: "market", hot: "E",
    why: "Catalysts explain WHY signals are changing.",
    what: "SEC filings, earnings windows, news, and catalysts per symbol.",
    next: "/action-queue" },

  // SIGNALS
  { to: "/action-queue", label: "Action Queue", section: "signals", hot: "Q",
    why: "All AI recommendations, grouped by what to do.",
    what: "Buy / Trim / Hold / Sell with confidence, rationale, event badges.",
    next: "/signal-lab" },
  { to: "/signal-lab", label: "Signal Lab", section: "signals", hot: "L",
    why: "Validate model quality before acting on signals.",
    what: "Action distribution, freshness, event-feature coverage, readiness score.",
    next: "/decisions" },
  { to: "/decisions", label: "Decisions", section: "signals", hot: "D",
    why: "Audit the decision trace and rationale behind each signal.",
    what: "Decision review, rationale traces, factor evidence.",
    next: "/strategies" },

  // EXECUTION
  { to: "/strategies", label: "Strategies", section: "execution", hot: "T",
    why: "Translate a signal into a strategy that fits the regime.",
    what: "Wheel, covered calls, CSPs, LEAPS, spreads · trade lifecycle + premium.",
    next: "/options" },
  { to: "/options", label: "Options", section: "execution", hot: "X",
    why: "Construct and observe options trades in detail.",
    what: "Chain, features, paper trades, observatory, performance.",
    next: "/portfolio" },

  // PORTFOLIO
  { to: "/portfolio", label: "Portfolio", section: "portfolio", hot: "P",
    why: "How exposed are we, and to what?",
    what: "Positions, exposure, sector / strategy concentration, P&L.",
    next: "/risk" },
  { to: "/risk", label: "Risk", section: "portfolio", hot: "R",
    why: "Where is the next problem most likely to come from?",
    what: "Risk dashboard · drawdowns · concentration warnings.",
    next: "/research" },

  // SYSTEM
  { to: "/research", label: "Alpha Lab", section: "system", hot: "A",
    why: "Research, backtests, and engine experiments.",
    what: "Alpha tooling, candidate research, regime modelling.",
    next: "/ops" },
  { to: "/ops", label: "Ops", section: "system", hot: "S",
    why: "Confirm the engine is actually running.",
    what: "Pipeline health, scheduler markers, data freshness, recovery state.",
  },
];


export const SECTIONS: { key: FlowSection; label: string }[] = [
  { key: "market",    label: "MARKET" },
  { key: "signals",   label: "SIGNALS" },
  { key: "execution", label: "EXECUTION" },
  { key: "portfolio", label: "PORTFOLIO" },
  { key: "system",    label: "SYSTEM" },
];


export function findStep(pathname: string): FlowStep | undefined {
  // Match longest prefix so /options/* still resolves to the Options step
  return [...FLOW]
    .sort((a, b) => b.to.length - a.to.length)
    .find(s => pathname === s.to || pathname.startsWith(s.to + "/"));
}


export function nextStep(pathname: string): FlowStep | undefined {
  const cur = findStep(pathname);
  if (!cur || !cur.next) return undefined;
  return FLOW.find(s => s.to === cur.next);
}
