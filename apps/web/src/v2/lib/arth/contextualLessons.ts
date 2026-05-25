// Phase 2D — Contextual lesson catalogue.
//
// Each lesson carries three tiers of content (per direction):
//   - primer:  30 seconds, popover-sized
//   - lesson:  2 minutes,  inline card
//   - deep:    5 minutes,  full read (links to /v2/learn archive)
//
// Lessons are NOT discoverable from a library. They are surfaced by
// the recommender at the moment a trigger fires. The /v2/learn archive
// shows only lessons the user has already encountered.
//
// Per honesty mandate: a lesson is "learned" only when the user passed
// the one-question check. Reading the primer marks it "read", not
// "learned".

export type LessonTier = 'primer' | 'lesson' | 'deep';

export interface ContextualLesson {
  slug: string;
  title: string;
  reads_in: { primer_seconds: number; lesson_minutes: number; deep_minutes: number };
  primer_body: string;            // ~30s
  lesson_body: string;            // ~2min  (rendered as paragraphs)
  deep_body?: string;             // ~5min  (optional; some lessons stop at 2min)
  check_question: string;
  check_answer_correct: string;
  check_answer_options: string[]; // 3-4 options including the correct one
  // Trigger metadata — what makes Arth surface this.
  trigger_label: string;          // e.g. "You skipped with reason 'Earnings risk'"
}

export const CONTEXTUAL_LESSONS: Record<string, ContextualLesson> = {
  earnings_risk: {
    slug: 'earnings_risk',
    title: 'Why earnings days are tricky',
    reads_in: { primer_seconds: 30, lesson_minutes: 2, deep_minutes: 5 },
    primer_body:
      "Earnings reports carry an IV crush — implied volatility usually " +
      "collapses immediately after the print. If you bought premium expecting " +
      "a move, you can be right on the direction AND wrong on the trade " +
      "because the option's value evaporated. That's the trap.",
    lesson_body:
      "When a company reports earnings, traders pile into options ahead of " +
      "the print because nobody knows which way the stock will move. Implied " +
      "volatility — the market's expectation of future swings — rises. After " +
      "the report releases, the uncertainty is gone. Volatility immediately " +
      "collapses, often by 30-50%, even if the stock moves in the direction " +
      "you predicted.\n\n" +
      "Two practical takeaways:\n" +
      "• If you buy options before earnings, you need a BIG move just to " +
      "  break even. The stock has to move more than the implied move.\n" +
      "• Selling premium before earnings (credit spreads, iron condors) is " +
      "  often the better edge — but only when defined-risk structures cap " +
      "  the tail loss.\n\n" +
      "Arth filters earnings setups by default when the report is < 6 weeks " +
      "out, unless you tell me otherwise.",
    deep_body:
      "[Full lesson with examples + edge case studies + position sizing notes. " +
      "5 minutes, available on demand.]",
    check_question:
      "If a stock moves +5% on an earnings beat but you bought call options " +
      "with implied vol at the 80th percentile, what's MOST likely to happen?",
    check_answer_correct:
      "Your calls may still lose value because IV crushed back to normal.",
    check_answer_options: [
      "Your calls double in value.",
      "Your calls may still lose value because IV crushed back to normal.",
      "The market will halt the stock.",
      "Earnings doesn't affect option prices.",
    ],
    trigger_label: "You skipped with reason 'Earnings risk'",
  },

  too_risky: {
    slug: 'too_risky',
    title: 'How to read your own risk filter',
    reads_in: { primer_seconds: 30, lesson_minutes: 2, deep_minutes: 5 },
    primer_body:
      "When you skip a setup as 'too risky,' you're using a personal " +
      "tolerance filter — not a wrong-vs-right judgment. The question to ask: " +
      "is the SETUP too risky, or is the SIZE too big? Same idea at half the " +
      "size is a different trade.",
    lesson_body:
      "Risk is two things: the probability of loss, and the size of the loss. " +
      "When you mark a setup 'too risky,' you may be reacting to either one " +
      "without knowing which. Splitting them matters because they have " +
      "different fixes.\n\n" +
      "If the probability is what bothers you (50/50 setup), pass — there's " +
      "no number small enough to make a bad setup a good one.\n\n" +
      "If the size is what bothers you, scale down. A 1% position has a " +
      "different psychology than a 5% position. Arth's default size " +
      "recommendations assume you're comfortable with the structure — feel " +
      "free to halve or quarter them.\n\n" +
      "Track your skip-with-reason history. If 'too risky' is your most " +
      "common reason and your overall PnL is fine, your filter is working. " +
      "If 'too risky' is your most common reason and you're underperforming, " +
      "you may be too tight.",
    check_question: "If 'too risky' is your most-used skip reason, the BEST first move is to:",
    check_answer_correct: "Check whether the size — not the setup — is what's making it feel risky.",
    check_answer_options: [
      "Stop following Arth.",
      "Check whether the size — not the setup — is what's making it feel risky.",
      "Trade more to overcome it.",
      "Switch to options only.",
    ],
    trigger_label: "You skipped with reason 'Too risky'",
  },

  exposure: {
    slug: 'exposure',
    title: 'When concentration outweighs conviction',
    reads_in: { primer_seconds: 30, lesson_minutes: 2, deep_minutes: 5 },
    primer_body:
      "Already exposed is a real reason to pass. Even a high-conviction idea " +
      "becomes a worse idea if your book is already pointed the same way. " +
      "Correlation eats diversification faster than most novices expect.",
    lesson_body:
      "Diversification is about correlation, not just count. Holding NVDA + AMD + " +
      "MSFT looks like 3 positions; in practice it's one bet on the semi/AI " +
      "complex with three tickers attached. When the cycle turns, all three move " +
      "together.\n\n" +
      "Two checks when an 'already too exposed' signal fires:\n" +
      "• Sector / theme overlap — is this idea adding new risk or stacking " +
      "  existing risk?\n" +
      "• Beta to your existing book — would this position move ±X% on the same " +
      "  days the rest of your book moves ±X%?\n\n" +
      "If the answer to both is no, the idea adds genuine diversification " +
      "and concentration isn't a good reason to pass. If yes — pass even at " +
      "high conviction, because you're already in.",
    check_question: "Holding 4 different mega-cap tech names is BEST described as:",
    check_answer_correct: "One concentrated bet with four tickers attached.",
    check_answer_options: [
      "Real diversification across four positions.",
      "One concentrated bet with four tickers attached.",
      "A safer portfolio than holding one of them.",
      "A different sector exposure per name.",
    ],
    trigger_label: "You skipped with reason 'Already too exposed here'",
  },

  bad_timing: {
    slug: 'bad_timing',
    title: 'The discipline of waiting',
    reads_in: { primer_seconds: 30, lesson_minutes: 2, deep_minutes: 5 },
    primer_body:
      "Waiting is a position. Pass-with-reason 'Bad timing' is a real " +
      "decision — Arth treats it as a thesis. Most setups don't disappear; " +
      "they reset. The catalyst either arrives on your schedule or you ignored " +
      "the right setup at the wrong moment.",
    lesson_body:
      "Time is the most underrated input. A setup with a fuzzy catalyst is " +
      "a different trade than the same setup with a defined catalyst in 6 days. " +
      "Two patterns worth recognizing:\n\n" +
      "• 'I'll wait for X' — write down X. Tomorrow check whether X happened. " +
      "  If X happened and you didn't act, you talked yourself out of your own " +
      "  plan.\n" +
      "• 'Bad timing' on the same setup three times in a row — the setup may " +
      "  not be wrong; you may be missing the catalyst. Re-read the thesis " +
      "  with the original date stamp.\n\n" +
      "Arth surfaces this lesson because you marked timing as the reason. " +
      "Next time you skip with 'bad timing,' I'll prompt you to name what " +
      "you're waiting for so we can both track it.",
    check_question: "Pass-with-reason 'Bad timing' three times on the same setup means:",
    check_answer_correct:
      "You may be missing the catalyst — worth rereading the thesis.",
    check_answer_options: [
      "The setup is wrong and should be retired.",
      "You may be missing the catalyst — worth rereading the thesis.",
      "Always skip — your gut is correct.",
      "Arth's recommendations are bad.",
    ],
    trigger_label: "You skipped with reason 'Bad timing'",
  },

  iv_crush: {
    slug: 'iv_crush',
    title: 'Implied volatility and the IV crush',
    reads_in: { primer_seconds: 30, lesson_minutes: 2, deep_minutes: 5 },
    primer_body:
      "Implied volatility (IV) is the market's expectation of how big the " +
      "next move will be. When IV is high, options are expensive. When IV " +
      "is low, they're cheap. After a known event (earnings, FDA approval), " +
      "IV collapses — that's the 'crush.'",
    lesson_body:
      "Option prices have two main inputs: where the stock might go " +
      "(intrinsic), and how uncertain people are about it (implied vol).\n\n" +
      "Before a known event, uncertainty piles in. Traders bid up options " +
      "because nobody knows the outcome. The implied vol number rises — " +
      "sometimes from 30% to 70% over a week.\n\n" +
      "When the event releases, the uncertainty is gone. IV reverts to its " +
      "normal level, often in a single session. If you bought options at IV " +
      "70 and IV crushes back to 30, the option loses a large fraction of " +
      "its value REGARDLESS of which direction the stock moved.\n\n" +
      "Practical move: track IV percentile (where IV sits in its trailing " +
      "1y range). When percentile < 25, options are cheap. When > 75, " +
      "options are expensive. Buy low, sell high — applies to vol too.",
    check_question:
      "AAPL IV at 22%ile means:",
    check_answer_correct:
      "Options are unusually cheap vs the trailing year.",
    check_answer_options: [
      "Options are unusually expensive vs the trailing year.",
      "Options are unusually cheap vs the trailing year.",
      "The stock is at a 22% loss.",
      "The expiry is 22 days out.",
    ],
    trigger_label: "You tapped on 'implied volatility' in a card",
  },

  why_stops_exist: {
    slug: 'why_stops_exist',
    title: 'Why stops exist (and why you should honor them)',
    reads_in: { primer_seconds: 30, lesson_minutes: 2, deep_minutes: 5 },
    primer_body:
      "Your invalidate line is the price at which the original thesis is " +
      "wrong. Holding past it isn't 'patience' — it's a new trade you " +
      "didn't decide to enter. The discipline of the stop is what makes " +
      "the position size affordable to lose.",
    lesson_body:
      "Every trade Arth recommends has an invalidate condition stated " +
      "before you enter. The number isn't arbitrary — it's the level " +
      "where the original signal stops working. Past that price, the " +
      "thesis is broken; staying in means you're now trading hope, not " +
      "the thesis.\n\n" +
      "The math is brutal: a -10% loss requires +11% to recover. A -25% " +
      "loss needs +33%. A -50% loss needs +100%. Honoring the stop early " +
      "preserves the ammo to take the next clean trade. Hoping for a " +
      "recovery is how small losses become career-ending ones.\n\n" +
      "The hardest part isn't writing the stop — it's executing it when " +
      "the price hits. Arth's job is to remind you that the original " +
      "decision was made with a clear head; the moment of the stop is " +
      "the moment that decision needs you to honor it.",
    check_question:
      "Why does Arth quote the invalidate price BEFORE you enter the trade?",
    check_answer_correct:
      "So the decision to exit is made before emotion makes it harder.",
    check_answer_options: [
      "Regulators require it.",
      "So the decision to exit is made before emotion makes it harder.",
      "To make the trade look safer.",
      "It's just a placeholder.",
    ],
    trigger_label: "You held a paper trade past its invalidate condition",
  },

  cut_winners_early: {
    slug: 'cut_winners_early',
    title: 'Why investors cut winners early',
    reads_in: { primer_seconds: 30, lesson_minutes: 2, deep_minutes: 5 },
    primer_body:
      "The most common loss-prevention move in novice portfolios is exiting " +
      "winners early. The reasoning: 'I'm up — I might give it back.' The " +
      "result: your average winner is smaller than your average loser, and " +
      "even a 60% win rate produces negative expectancy.",
    lesson_body:
      "Profitable trading is asymmetric. You need your winners to be larger " +
      "than your losers, because losers are inevitable and the math has to " +
      "work across many trades.\n\n" +
      "The cognitive bias at play is loss aversion: a $1 unrealized loss " +
      "feels twice as painful as a $1 unrealized gain feels good. When " +
      "you're in profit, every tick lower feels like a partial loss — so " +
      "you exit to lock it in.\n\n" +
      "Two fixes:\n" +
      "• Decide the target BEFORE the trade. If you set $5.00 as the " +
      "  target and the trade hits $4.60, the discipline is to hold to $5 " +
      "  unless the invalidate condition triggers.\n" +
      "• Trail your stop instead of exiting flat. Move the invalidate up " +
      "  as the trade works — you bank profit if it reverses without " +
      "  capping the upside.",
    check_question:
      "A 60% win rate where your avg winner is +1% and avg loser is -2% has:",
    check_answer_correct: "Negative expectancy — you'll lose money on average.",
    check_answer_options: [
      "Positive expectancy — you'll make money.",
      "Negative expectancy — you'll lose money on average.",
      "Break-even — neither.",
      "Not enough information to tell.",
    ],
    trigger_label: "You closed a winner before its target",
  },

  showing_up: {
    slug: 'showing_up',
    title: 'The discipline of showing up',
    reads_in: { primer_seconds: 30, lesson_minutes: 2, deep_minutes: 5 },
    primer_body:
      "Day 7. You've shown up every day this week — not to trade, but to " +
      "read. That discipline compounds. Most novices skim a briefing for " +
      "two weeks and disappear. You don't have to be brilliant to beat " +
      "that — you just have to keep showing up.",
    lesson_body:
      "Investing rewards consistency more than intelligence. The hardest " +
      "thing about a daily practice isn't reading the briefing — it's " +
      "reading the briefing on days when nothing exciting happens.\n\n" +
      "Why the discipline matters:\n" +
      "• You see Arth's track record build in real time. That trust takes " +
      "  weeks of observation, not one good call.\n" +
      "• You build mental reference points. When NVDA shows up six months " +
      "  from now, you'll remember what the signal looked like the first " +
      "  time.\n" +
      "• Your skip-with-reason data accumulates. Arth's 'why for you' line " +
      "  becomes meaningfully personal only after ~30 days of observed " +
      "  behavior.\n\n" +
      "Don't aim for streaks. Aim for the next briefing. Streaks happen " +
      "as a side effect.",
    check_question: "Why does Arth bother surfacing this lesson at Day 7?",
    check_answer_correct:
      "Because the habit is the product — and acknowledging it makes it stickier.",
    check_answer_options: [
      "To pad the lesson list.",
      "Because the habit is the product — and acknowledging it makes it stickier.",
      "To prevent you from quitting.",
      "Because seven is a special number.",
    ],
    trigger_label: "You hit a 7-day streak",
  },
};

export function getLesson(slug: string): ContextualLesson | undefined {
  return CONTEXTUAL_LESSONS[slug];
}

export const CONTEXTUAL_LESSON_SLUGS = Object.keys(CONTEXTUAL_LESSONS);
