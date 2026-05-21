// Learn curriculum — schema + data exports for PR-5A Phase A.
//
// Phase A ships 4 sample lessons + 2 glossary terms + 1 concept stub
// to validate the visual + pedagogical pattern before authoring the
// remaining curriculum. All copy passes Tier-A 30-phrase lint.

export type Tier = 0 | 1 | 2 | 3;

export interface Path {
  slug: string;
  title: string;
  tier: Tier;
  tierLabel: string;          // "Foundations" / "Risk + reflection" / "Skill"
  synopsis: string;
  totalMinutes: number;       // estimated reading time across all lessons
  lessonSlugs: string[];      // ordered; empty paths show "Coming next release"
  outcome: string;            // "After this path"
  relatedConcepts: string[];  // concept slugs
}

export type LessonBlock =
  | { type: "paragraph"; text: string }
  | { type: "subhead"; text: string }
  | { type: "liveData"; description: string };

export interface Lesson {
  slug: string;
  pathSlug: string;
  order: number;              // 1-based within path
  title: string;
  minutes: number;
  openingLine: string;        // serif emphasis line
  body: LessonBlock[];
  reflectionPrompt: string;
  conceptTags: string[];
  termsReferenced: string[];
}

export interface Term {
  slug: string;
  term: string;
  category: "ai" | "portfolio" | "risk" | "general";
  definition: string;
  whyItMatters: string;
  howAIUses: string;
  relatedTerms: string[];
  lessonSlugs: string[];      // lessons that cover this term
}

export interface Concept {
  slug: string;
  label: string;
  isStub: boolean;            // Phase A ships stubs; PR-5B upgrades to full
  shortDefinition: string;
  howAIUses: string;
  lessonSlugs: string[];
}


// ---------------------------------------------------------------
// Paths — all 9 declared so PathList renders complete index.
// Lessons fill in Phase B; for now most paths are empty placeholders.
// ---------------------------------------------------------------

export const PATHS: Path[] = [
  {
    slug: "investing-basics",
    title: "Investing basics",
    tier: 0,
    tierLabel: "Foundations",
    synopsis:
      "Start here. The handful of concepts every investor needs before "
      + "anything else makes sense.",
    totalMinutes: 12,
    lessonSlugs: ["what-is-a-stock"],
    outcome:
      "You will know what a stock is, why long-term ownership matters, "
      + "and how to think about price versus value.",
    relatedConcepts: [],
  },
  {
    slug: "how-markets-actually-work",
    title: "How markets actually work",
    tier: 0,
    tierLabel: "Foundations",
    synopsis:
      "A short orientation to how markets behave when no one is watching. "
      + "Not how to predict them — how they actually move.",
    totalMinutes: 19,
    lessonSlugs: [
      "why-prices-move-when-nothing-happens",
      "why-great-investors-do-nothing-most-days",
    ],
    outcome:
      "You will understand why most market days are noise, why discipline "
      + "matters more than activity, and why most attempts to time the "
      + "market underperform doing nothing.",
    relatedConcepts: ["momentum"],
  },
  {
    slug: "how-this-ai-thinks",
    title: "How this AI thinks",
    tier: 1,
    tierLabel: "Foundations",
    synopsis:
      "What signals are, what they are not, and how the engine decides "
      + "when to act.",
    totalMinutes: 16,
    lessonSlugs: ["what-is-a-signal"],
    outcome:
      "You will understand that the engine flags patterns, not predictions, "
      + "and why confidence percentages are missing on purpose.",
    relatedConcepts: ["momentum"],
  },
  {
    slug: "reading-what-you-own",
    title: "Reading what you own",
    tier: 1,
    tierLabel: "Foundations",
    synopsis:
      "The numbers on the dashboard — what each one means and which "
      + "ones actually matter.",
    totalMinutes: 17,
    lessonSlugs: [],
    outcome:
      "You will be able to read every number on the Portfolio page "
      + "without help.",
    relatedConcepts: [],
  },
  {
    slug: "paper-trading-fundamentals",
    title: "Paper trading fundamentals",
    tier: 1,
    tierLabel: "Foundations",
    synopsis: "What is simulated, what is real, and why paper comes first.",
    totalMinutes: 13,
    lessonSlugs: [],
    outcome:
      "You will know exactly what is being simulated and where the "
      + "boundary between paper and real lives.",
    relatedConcepts: [],
  },
  {
    slug: "risk-literacy",
    title: "Risk literacy",
    tier: 2,
    tierLabel: "Risk + reflection",
    synopsis: "What protects a position and what does not.",
    totalMinutes: 18,
    lessonSlugs: [],
    outcome:
      "You will understand position sizing, concentration, and why "
      + "stop-losses protect against you, not the market.",
    relatedConcepts: [],
  },
  {
    slug: "portfolio-psychology",
    title: "Portfolio psychology",
    tier: 2,
    tierLabel: "Risk + reflection",
    synopsis:
      "The most expensive part of investing is usually inside your own "
      + "head. Naming the patterns is most of the cure.",
    totalMinutes: 17,
    lessonSlugs: [],
    outcome:
      "You will spot anchoring, sunk-cost reasoning, and over-trading "
      + "in your own thinking — before they affect decisions.",
    relatedConcepts: [],
  },
  {
    slug: "reading-signals-like-an-analyst",
    title: "Reading signals like an analyst",
    tier: 3,
    tierLabel: "Skill",
    synopsis: "How to read a Pick Detail page without the Learn chips.",
    totalMinutes: 20,
    lessonSlugs: [],
    outcome:
      "You will be able to interpret a fresh signal independently — "
      + "concept, evidence, invalidation, horizon — without help.",
    relatedConcepts: ["momentum"],
  },
  {
    slug: "when-the-ai-is-wrong",
    title: "When the AI is wrong",
    tier: 3,
    tierLabel: "Skill",
    synopsis:
      "Bad signals, bad regimes, and how to tell the difference. The "
      + "engine fails honestly; this path is how to read those failures.",
    totalMinutes: 18,
    lessonSlugs: [],
    outcome:
      "You will be able to distinguish a bad individual signal from a "
      + "mismatched market regime.",
    relatedConcepts: [],
  },
];


// ---------------------------------------------------------------
// Lessons — 4 sample lessons for Phase A.
// Order matters: visual review reads them in declared order.
// ---------------------------------------------------------------

export const LESSONS: Lesson[] = [
  {
    slug: "why-great-investors-do-nothing-most-days",
    pathSlug: "how-markets-actually-work",
    order: 2,
    title: "Why great investors do nothing most days",
    minutes: 4,
    openingLine:
      "Warren Buffett famously sits in Omaha most days reading. He does "
      + "not look at his portfolio. He does not check prices. He is not "
      + "bored.",
    body: [
      {
        type: "paragraph",
        text:
          "In a normal year, the U.S. market is open about 252 days. "
          + "Most of those days are noise — small moves that average out, "
          + "with no meaningful change to any well-formed thesis. An "
          + "investor who acts on every move is mostly trading noise, "
          + "not information.",
      },
      { type: "subhead", text: "What the engine does on a quiet day" },
      {
        type: "paragraph",
        text:
          "ArthOS fires roughly one to three signals per week in a "
          + "typical market regime. On most days, it does nothing. The "
          + "quiet is the discipline, not a flaw. When the engine has "
          + "nothing to do, the calm response is to have nothing to do.",
      },
      {
        type: "liveData",
        description:
          "How many signals fired in the last 30 days, vs total days "
          + "evaluated",
      },
      { type: "subhead", text: "Why this matters" },
      {
        type: "paragraph",
        text:
          "Every action has an opportunity cost. The cost is not only "
          + "the trade itself — it is also the cognitive load, the "
          + "anchoring on entry prices, the temptation to revisit, and "
          + "the loss of attention for actually important things.",
      },
      {
        type: "paragraph",
        text:
          "Holding is a decision. Doing nothing is a discipline. "
          + "Restraint compounds.",
      },
    ],
    reflectionPrompt:
      "Think back to the last time you opened your brokerage app three "
      + "times in one day. What did you do that you would not have done "
      + "if you had only opened it once? Was that better, or just busier?",
    conceptTags: ["discipline", "opportunity-cost"],
    termsReferenced: ["drawdown"],
  },

  {
    slug: "what-is-a-signal",
    pathSlug: "how-this-ai-thinks",
    order: 1,
    title: "What is a signal — and why isn't it a prediction?",
    minutes: 3,
    openingLine:
      "A weather forecaster says a 70 percent chance of rain. A trader "
      + "says a stock will hit a specific price by Friday. One of these "
      + "is a calibrated probability. The other is a guess wearing a "
      + "number.",
    body: [
      {
        type: "paragraph",
        text:
          "ArthOS does not forecast prices. It observes patterns. When a "
          + "pattern crosses a threshold the engine considers meaningful, "
          + "a signal fires. The signal says: this configuration has "
          + "historically tended to play out in a certain way. Not: this "
          + "will happen.",
      },
      { type: "subhead", text: "Why this distinction matters" },
      {
        type: "paragraph",
        text:
          "A forecast asks you to bet on a single future. A signal asks "
          + "you to consider whether the conditions for a particular kind "
          + "of outcome are present. The first is theatre; the second is "
          + "process.",
      },
      {
        type: "paragraph",
        text:
          "Every signal in ArthOS comes from a deterministic engine. "
          + "The inputs are public. The thresholds are fixed. You can "
          + "audit the signal in the Pick Detail page and see exactly "
          + "which conditions were met.",
      },
      {
        type: "paragraph",
        text:
          "Forecasts feel certain. Signals feel honest. The product is "
          + "built for honest.",
      },
    ],
    reflectionPrompt:
      "Have you ever confused a pattern in something you observed with a "
      + "forecast for what would happen next?",
    conceptTags: ["momentum"],
    termsReferenced: [],
  },

  {
    slug: "why-prices-move-when-nothing-happens",
    pathSlug: "how-markets-actually-work",
    order: 1,
    title: "Why prices move when nothing happens",
    minutes: 3,
    openingLine:
      "On any given day, the price of a stock can move two or three "
      + "percent without a single news headline, earnings release, or "
      + "analyst note. The price moves because someone, somewhere, "
      + "decided to buy or sell. That is the entire mechanism.",
    body: [
      {
        type: "paragraph",
        text:
          "Markets are not driven by news the way headlines suggest. "
          + "Most price movement is the aggregate of millions of small "
          + "decisions, each made for individual reasons — a fund "
          + "rebalancing, a portfolio manager taking a vacation, a "
          + "quantitative model rotating exposure. None of these are "
          + "newsworthy.",
      },
      { type: "subhead", text: "What this means for the rest of your investing life" },
      {
        type: "paragraph",
        text:
          "If most days produce price movement without news, then most "
          + "price movement is noise. If most price movement is noise, "
          + "then watching the daily price chart is mostly watching "
          + "noise.",
      },
      {
        type: "paragraph",
        text:
          "This is why ArthOS does not display a live ticker. The ticker "
          + "would tell you the truth — prices change — but it would not "
          + "help you act on truth.",
      },
    ],
    reflectionPrompt:
      "When was the last time a price move actually changed your view of "
      + "a company's underlying value? How often does price move per "
      + "year? How often does your view move?",
    conceptTags: [],
    termsReferenced: [],
  },

  {
    slug: "what-is-a-stock",
    pathSlug: "investing-basics",
    order: 1,
    title: "What is a stock?",
    minutes: 3,
    openingLine:
      "A stock is a fractional ownership share of a business. If you "
      + "own one share of a company that has issued 100 million shares, "
      + "you own one hundred-millionth of that company. The ownership is "
      + "real, even when the number feels abstract.",
    body: [
      {
        type: "paragraph",
        text:
          "When you own a stock, you have a claim on the company's "
          + "future profits. Some companies distribute those profits "
          + "directly as dividends. Most reinvest them to grow the "
          + "business, which over time makes the share more valuable. "
          + "Both outcomes are forms of ownership returning value to you.",
      },
      { type: "subhead", text: "Why people care about the price" },
      {
        type: "paragraph",
        text:
          "The price of a stock is what someone else is willing to pay "
          + "for that ownership today. The price moves because opinions "
          + "about future profits move. It is not the value of the "
          + "company; it is the auction-house value of the ownership at "
          + "a given moment.",
      },
      {
        type: "paragraph",
        text:
          "A long-term investor cares mostly about the company. A "
          + "short-term trader cares mostly about the price. ArthOS is "
          + "built for the first kind.",
      },
    ],
    reflectionPrompt:
      "If you owned ten percent of a small business in your hometown, "
      + "would you check the value every five minutes? Why or why not?",
    conceptTags: [],
    termsReferenced: [],
  },
];


// ---------------------------------------------------------------
// Terms — 2 sample terms for Phase A.
// ---------------------------------------------------------------

export const TERMS: Term[] = [
  {
    slug: "drawdown",
    term: "Drawdown",
    category: "risk",
    definition:
      "The peak-to-trough percent decline of an investment from its most "
      + "recent high.",
    whyItMatters:
      "Every long-term investor experiences drawdowns. The mathematics of "
      + "returns is asymmetric: a 50 percent decline requires a 100 "
      + "percent gain to recover. Understanding drawdown is the "
      + "difference between staying invested through a difficult period "
      + "and abandoning a sound strategy at the worst moment.",
    howAIUses:
      "ArthOS tracks the portfolio's drawdown daily on the Track Record "
      + "page. The chart shows every period of decline and recovery since "
      + "inception. Losses are rendered at the same visual weight as "
      + "gains — by design.",
    relatedTerms: ["peak", "trough", "recovery", "volatility"],
    lessonSlugs: ["why-great-investors-do-nothing-most-days"],
  },
  {
    slug: "stop-loss",
    term: "Stop-loss",
    category: "risk",
    definition:
      "A pre-committed price level below which a position will be closed, "
      + "regardless of the holder's feelings at the moment.",
    whyItMatters:
      "The hardest part of selling a losing position is the moment of "
      + "selling. A stop-loss makes that decision in advance, when the "
      + "holder is calm and the position is profitable. By the time the "
      + "price reaches the stop, the decision has already been made.",
    howAIUses:
      "ArthOS attaches a stop-loss reference price to most signals at the "
      + "time of entry. The stop is not automatically executed — it is a "
      + "threshold the engine watches. When the threshold is breached, a "
      + "Sell signal is fired and surfaced on the Today page.",
    relatedTerms: ["invalidation", "take-profit", "position-sizing"],
    lessonSlugs: [],
  },
];


// ---------------------------------------------------------------
// Concepts — 1 stub for Phase A.
// ---------------------------------------------------------------

export const CONCEPTS: Concept[] = [
  {
    slug: "momentum",
    label: "Momentum",
    isStub: true,
    shortDefinition:
      "Momentum is the tendency for prices that have been rising to "
      + "continue rising — and for prices that have been falling to "
      + "continue falling — over short to medium horizons.",
    howAIUses:
      "ArthOS uses momentum as one of several factors in signal "
      + "generation. A momentum-based signal might fire when a stock has "
      + "been trending above its longer-term average and recent volume "
      + "has expanded. The full methodology page will follow in a future "
      + "release.",
    lessonSlugs: ["why-great-investors-do-nothing-most-days", "what-is-a-signal"],
  },
];


// ---------------------------------------------------------------
// Lookup helpers
// ---------------------------------------------------------------

export function getPath(slug: string): Path | undefined {
  return PATHS.find(p => p.slug === slug);
}

export function getLesson(slug: string): Lesson | undefined {
  return LESSONS.find(l => l.slug === slug);
}

export function getLessonsForPath(pathSlug: string): Lesson[] {
  return LESSONS.filter(l => l.pathSlug === pathSlug)
                .sort((a, b) => a.order - b.order);
}

export function getNextLesson(currentSlug: string): Lesson | undefined {
  const current = getLesson(currentSlug);
  if (!current) return undefined;
  return LESSONS.find(
    l => l.pathSlug === current.pathSlug && l.order === current.order + 1,
  );
}

export function getTerm(slug: string): Term | undefined {
  return TERMS.find(t => t.slug === slug);
}

export function getConcept(slug: string): Concept | undefined {
  return CONCEPTS.find(c => c.slug === slug);
}

export function getPathsByTier(tier: Tier): Path[] {
  return PATHS.filter(p => p.tier === tier);
}

export function getAllTermsAlphabetical(): Term[] {
  return [...TERMS].sort((a, b) => a.term.localeCompare(b.term));
}
