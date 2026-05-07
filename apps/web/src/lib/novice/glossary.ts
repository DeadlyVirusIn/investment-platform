// Phase NOVICE-UX (Commit 1) — central beginner glossary.
//
// Single source of truth for plain-English term definitions used by
// MetricHelpTooltip, AdvancedDetails, EmptyStateGuide, and any
// future novice surfaces. NEVER imply recommendations, live trading,
// or financial advice. NEVER hide uncertainty, small-sample, or
// missing-data caveats.
//
// Tooltip text rule:
//   1) plain definition (1 short sentence)
//   2) optional "healthy / concerning" interpretation
//   3) optional "not a prediction / paper only" caveat where the
//      term is review-context (e.g., trade-review score)

export interface GlossaryEntry {
  /** Stable key — referenced by `MetricHelpTooltip term="..."`. */
  term: string;
  /** User-facing label (already in plain English). */
  label: string;
  /** Tooltip body — 1–3 short sentences. */
  description: string;
}


export const GLOSSARY: Record<string, GlossaryEntry> = {
  account_value: {
    term: "account_value",
    label: "Account value",
    description:
      "Total value of your paper account: cash plus the current " +
      "value of every open position. Updates as prices move.",
  },
  available_cash: {
    term: "available_cash",
    label: "Available cash",
    description:
      "Money in your paper account that isn't currently invested.",
  },
  money_invested: {
    term: "money_invested",
    label: "Money currently invested",
    description:
      "Sum of the current value of every open position. " +
      "When a market mark is missing we say so explicitly — " +
      "we never substitute zero.",
  },
  percent_invested: {
    term: "percent_invested",
    label: "Percent invested",
    description:
      "What share of your account value is currently held in " +
      "positions. 100% means cash is fully deployed.",
  },
  realized_pnl: {
    term: "realized_pnl",
    label: "Profit/loss from closed trades",
    description:
      "Sum of profit and loss from trades you've already closed. " +
      "These numbers are settled.",
  },
  unrealized_pnl: {
    term: "unrealized_pnl",
    label: "Profit/loss if you closed now",
    description:
      "What you'd gain or lose if every open position closed at " +
      "today's price. Not real until you close — prices move.",
  },
  drawdown: {
    term: "drawdown",
    label: "Biggest drop from peak",
    description:
      "The largest percent drop in account value from a previous " +
      "high. A larger number means a bigger past dip.",
  },
  concentration: {
    term: "concentration",
    label: "How spread out your money is",
    description:
      "Lower means money is split across many positions. " +
      "Higher means a few positions dominate the account.",
  },
  pending_next_bar: {
    term: "pending_next_bar",
    label: "Waiting for the next market price",
    description:
      "We never fill on the same bar a signal arrives. We wait for " +
      "the next price bar to be honest about timing. This is " +
      "intentional, not an error.",
  },
  next_bar_guard: {
    term: "next_bar_guard",
    label: "Honest fill rule",
    description:
      "Safety rule: orders never fill on the same bar the signal " +
      "arrived. We always wait for the next price bar.",
  },
  replay: {
    term: "replay",
    label: "Rebuilt historical simulation",
    description:
      "Trades reconstructed from past data. Not new live activity. " +
      "Hidden by default in headline counts.",
  },
  market_condition: {
    term: "market_condition",
    label: "Market condition",
    description:
      "Plain summary of whether the market has been calm, " +
      "trending, or volatile recently. Backward-looking only.",
  },
  signals: {
    term: "signals",
    label: "Today's trade ideas",
    description:
      "The list of stocks the system flagged as candidates today. " +
      "Each is reviewed by safety rules before any order is placed.",
  },
  safety_check: {
    term: "safety_check",
    label: "Safety check",
    description:
      "A pre-trade rule. A trade can be skipped because a safety " +
      "check refused it — that's the system working as intended, " +
      "not an accident.",
  },
  take_profit: {
    term: "take_profit",
    label: "Take-profit exit",
    description:
      "A pre-set rule that closes a position once it has gained a " +
      "target percentage.",
  },
  stop_loss: {
    term: "stop_loss",
    label: "Stop-loss exit",
    description:
      "A pre-set rule that closes a position once it has lost more " +
      "than a target percentage.",
  },
  max_hold: {
    term: "max_hold",
    label: "Time-limit exit",
    description:
      "A pre-set rule that closes a position once it has been held " +
      "longer than a maximum number of days.",
  },
  win_rate: {
    term: "win_rate",
    label: "Percent of trades that made money",
    description:
      "Of trades you've closed, the share that ended in profit. " +
      "Shown as null until at least one trade closes — never as 0%.",
  },
  trade_review_score: {
    term: "trade_review_score",
    label: "Trade quality score",
    description:
      "Internal quality score, 0–100. This score reviews how a " +
      "trade behaved afterward. It is NOT a prediction of future " +
      "performance.",
  },
  trade_review_grade: {
    term: "trade_review_grade",
    label: "Trade quality rating",
    description:
      "Letter rating for the quality score. A 85+, B 70+, C 55+, " +
      "D 40+, F under 40. Review-only, not a forecast.",
  },
  thesis: {
    term: "thesis",
    label: "Reason category",
    description:
      "Plain bucket explaining how the trade ended: stopped out, " +
      "hit profit target, held to time limit, etc.",
  },
  small_sample: {
    term: "small_sample",
    label: "Not enough data yet",
    description:
      "Statistics need a meaningful number of closed trades to be " +
      "reliable. Below that threshold, numbers are directional " +
      "only — treat them as a hint, not a conclusion.",
  },
  read_only_insight: {
    term: "read_only_insight",
    label: "Read-only system insight",
    description:
      "Plain-English summary generated for review. Read-only. " +
      "Never trades on your behalf. Not financial advice.",
  },
  spend_limit: {
    term: "spend_limit",
    label: "Spend limit",
    description:
      "Hard ceiling on AI-generated explanation spend per running " +
      "process. When reached, new explanations are blocked until " +
      "the process is restarted.",
  },
  paper_only: {
    term: "paper_only",
    label: "Paper trading only",
    description:
      "Every trade on this site is simulated. No real money or " +
      "real broker is involved.",
  },
};


/** Lookup helper. Returns null when the term is missing so callers
 *  can degrade gracefully rather than crash on a typo. */
export function getGlossary(term: string): GlossaryEntry | null {
  return GLOSSARY[term] ?? null;
}
