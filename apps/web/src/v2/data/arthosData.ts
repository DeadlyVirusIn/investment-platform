// Seed data for ArthOS — paths, lessons, glossary, concepts, portfolio.
// All copy follows the voice rules: first-person plural, no "AI", no exclamations, no questions back to the user.

export type Tier = 'Foundations' | 'Risk + reflection' | 'Skill';

export interface Path {
  slug: string;
  tier: Tier;
  title: string;
  synopsis: string;
  lessonSlugs: string[];
}

export interface Lesson {
  slug: string;
  pathSlug: string;
  order: number;
  title: string;
  abstract: string;
  readMinutes: number;
  read: boolean;
  body: LessonBlock[];
  connectedSymbol: string; // links to a real trade
}

export type LessonBlock =
| {type: 'p';text: string;} // paragraph; supports <term:slug>…</term> markup
| {type: 'pullquote';text: string;}
// Lovable port (Phase 3): richer block types for academy lessons.
| {type: 'h2';text: string;}
| {type: 'callout';tone: 'insight' | 'caution' | 'reflect';title: string;text: string;}
| {type: 'list';items: string[];};

export interface GlossaryTerm {
  slug: string;
  term: string;
  shortDefinition: string; // ~1 sentence for the index
  longDefinition: string; // ~40 words for hover popover
  body: string; // full term page body, ~60 words
  examples: TermExample[];
  lessonRefs: string[]; // slugs of lessons that reference it
}

export interface Concept {
  slug: string;
  title: string;
  definition: string; // ~60 words
  body: string;
  examples: TermExample[];
}

export interface TermExample {
  symbol: string;
  date: string;
  outcome: string;
}

export interface Position {
  symbol: string;
  company: string;
  costBasis: number;
  current: number;
  dayHeld: number;
  thesisShort: string;
}

export interface PortfolioSnapshot {
  edition: number;
  dateLong: string;
  dateShort: string;
  dayMovePct: number; // signed
  lifetimeMovePct: number; // signed, since Day 1
  equity: number;
  positions: Position[];
}

// ============================================================================
// TRACK RECORD — closed trades, lifetime equity, and quarterly retrospectives
// ============================================================================

export interface ClosedTrade {
  symbol: string;
  company: string;
  opened: string; // ISO date
  closed: string; // ISO date
  daysHeld: number;
  movePct: number; // signed
  outcome: 'win' | 'loss';
  side: 'long' | 'short' | 'long-option' | 'short-option';
  exitReason: string;
  statedHorizon: 'short' | 'medium' | 'long'; // for calibration
  quarter: 'Q3-2025' | 'Q4-2025' | 'Q1-2026' | 'Q2-2026';
}

export const TRACK_RECORD_CLOSED: ClosedTrade[] = [
// Q3 2025
{
  symbol: 'ORCL',
  company: 'Oracle',
  opened: '2025-07-08',
  closed: '2025-08-22',
  daysHeld: 45,
  movePct: 4.8,
  outcome: 'win',
  side: 'long',
  exitReason:
  'Cloud bookings reset expectations modestly; we took the gain and rotated.',
  statedHorizon: 'medium',
  quarter: 'Q3-2025'
},
{
  symbol: 'XOM',
  company: 'Exxon Mobil',
  opened: '2025-08-04',
  closed: '2025-09-10',
  daysHeld: 37,
  movePct: -2.6,
  outcome: 'loss',
  side: 'long',
  exitReason:
  'Crude curve flattened faster than the thesis assumed. Stopped out cleanly.',
  statedHorizon: 'short',
  quarter: 'Q3-2025'
},
{
  symbol: 'HD',
  company: 'Home Depot',
  opened: '2025-07-22',
  closed: '2025-09-18',
  daysHeld: 58,
  movePct: 6.2,
  outcome: 'win',
  side: 'long',
  exitReason: 'Closed on multiple-expansion target. The discipline held.',
  statedHorizon: 'medium',
  quarter: 'Q3-2025'
},
{
  symbol: 'BA',
  company: 'Boeing',
  opened: '2025-09-02',
  closed: '2025-09-26',
  daysHeld: 24,
  movePct: -4.4,
  outcome: 'loss',
  side: 'long',
  exitReason:
  'A second supply-chain item we did not foresee. We exited; the size was right.',
  statedHorizon: 'short',
  quarter: 'Q3-2025'
},
// Q4 2025
{
  symbol: 'ADBE',
  company: 'Adobe',
  opened: '2025-10-30',
  closed: '2025-12-15',
  daysHeld: 46,
  movePct: 11.8,
  outcome: 'win',
  side: 'long',
  exitReason:
  'Held through an earnings event. Closed when the post-event drift looked extended.',
  statedHorizon: 'medium',
  quarter: 'Q4-2025'
},
{
  symbol: 'PEP',
  company: 'PepsiCo',
  opened: '2025-12-04',
  closed: '2026-01-22',
  daysHeld: 49,
  movePct: 3.2,
  outcome: 'win',
  side: 'long',
  exitReason:
  'Modest win. Trimmed in tranches as the position drifted larger than warranted.',
  statedHorizon: 'long',
  quarter: 'Q4-2025'
},
{
  symbol: 'F',
  company: 'Ford Motor',
  opened: '2025-11-18',
  closed: '2025-12-09',
  daysHeld: 21,
  movePct: -3.4,
  outcome: 'loss',
  side: 'long',
  exitReason:
  'The momentum signal weakened before it confirmed; we had sized for that.',
  statedHorizon: 'short',
  quarter: 'Q4-2025'
},
{
  symbol: 'TGT',
  company: 'Target',
  opened: '2025-11-04',
  closed: '2025-12-19',
  daysHeld: 45,
  movePct: -7.2,
  outcome: 'loss',
  side: 'long',
  exitReason:
  'Margin compression came earlier than we expected. The clearest miss of the quarter.',
  statedHorizon: 'medium',
  quarter: 'Q4-2025'
},
{
  symbol: 'QQQ',
  company: 'NASDAQ-100 calls',
  opened: '2025-12-08',
  closed: '2025-12-22',
  daysHeld: 14,
  movePct: 18.5,
  outcome: 'win',
  side: 'long-option',
  exitReason:
  'A defined-risk call spread bought into low IV. Held to nearly the full spread.',
  statedHorizon: 'short',
  quarter: 'Q4-2025'
},
// Q1 2026
{
  symbol: 'CRM',
  company: 'Salesforce',
  opened: '2026-01-08',
  closed: '2026-02-20',
  daysHeld: 43,
  movePct: 7.4,
  outcome: 'win',
  side: 'long',
  exitReason:
  'Closed on a multiple-expansion target. Held for a defined catalyst and exited cleanly.',
  statedHorizon: 'medium',
  quarter: 'Q1-2026'
},
{
  symbol: 'NVDA',
  company: 'NVIDIA',
  opened: '2026-02-12',
  closed: '2026-03-04',
  daysHeld: 21,
  movePct: -6.1,
  outcome: 'loss',
  side: 'long',
  exitReason:
  'Exited at the stop. The thesis had broken — capex commentary at a competitor reset expectations.',
  statedHorizon: 'medium',
  quarter: 'Q1-2026'
},
{
  symbol: 'WMT',
  company: 'Walmart',
  opened: '2026-01-22',
  closed: '2026-03-18',
  daysHeld: 55,
  movePct: 5.6,
  outcome: 'win',
  side: 'long',
  exitReason: 'A quiet position that did exactly what the thesis suggested.',
  statedHorizon: 'long',
  quarter: 'Q1-2026'
},
{
  symbol: 'IWM',
  company: 'Russell 2000 puts',
  opened: '2026-02-04',
  closed: '2026-02-25',
  daysHeld: 21,
  movePct: -45.0,
  outcome: 'loss',
  side: 'long-option',
  exitReason:
  'Hedge that did not need to pay off. Defined-risk; small loss as planned.',
  statedHorizon: 'short',
  quarter: 'Q1-2026'
},
{
  symbol: 'MA',
  company: 'Mastercard',
  opened: '2026-03-08',
  closed: '2026-04-22',
  daysHeld: 45,
  movePct: 4.2,
  outcome: 'win',
  side: 'long',
  exitReason:
  'Sister trade to V. Closed half; the other half stayed and now sits in the portfolio.',
  statedHorizon: 'long',
  quarter: 'Q1-2026'
},
{
  symbol: 'XLE',
  company: 'Energy Sector ETF (short)',
  opened: '2026-03-18',
  closed: '2026-04-30',
  daysHeld: 43,
  movePct: 3.1,
  outcome: 'win',
  side: 'short',
  exitReason:
  'Short into a momentum exhaustion. Took the gain at the target.',
  statedHorizon: 'short',
  quarter: 'Q1-2026'
}];


// Weekly equity timeline — generated to show two realistic drawdown periods
// that the calibration narrative can reference.
export interface EquityPoint {
  date: string;
  equity: number;
}

export const STARTING_EQUITY = 100000;

export const EQUITY_TIMELINE: EquityPoint[] = [
{ date: '2025-10-24', equity: 100000 },
{ date: '2025-10-31', equity: 100820 },
{ date: '2025-11-07', equity: 101940 },
{ date: '2025-11-14', equity: 103120 },
{ date: '2025-11-21', equity: 102340 },
{ date: '2025-11-28', equity: 101180 },
{ date: '2025-12-05', equity: 99840 }, // drawdown #1 trough
{ date: '2025-12-12', equity: 100920 },
{ date: '2025-12-19', equity: 103420 },
{ date: '2025-12-26', equity: 105180 },
{ date: '2026-01-02', equity: 106940 },
{ date: '2026-01-09', equity: 108220 },
{ date: '2026-01-16', equity: 109480 },
{ date: '2026-01-23', equity: 110260 },
{ date: '2026-01-30', equity: 111840 },
{ date: '2026-02-06', equity: 110920 },
{ date: '2026-02-13', equity: 108740 },
{ date: '2026-02-20', equity: 106420 }, // drawdown #2 trough
{ date: '2026-02-27', equity: 108180 },
{ date: '2026-03-06', equity: 110480 },
{ date: '2026-03-13', equity: 112620 },
{ date: '2026-03-20', equity: 113840 },
{ date: '2026-03-27', equity: 114920 },
{ date: '2026-04-03', equity: 115480 },
{ date: '2026-04-10', equity: 116240 },
{ date: '2026-04-17', equity: 117380 },
{ date: '2026-04-24', equity: 117840 },
{ date: '2026-05-01', equity: 118120 },
{ date: '2026-05-08', equity: 118420 },
{ date: '2026-05-15', equity: 118620 },
{ date: '2026-05-21', equity: 118742 }];


export interface QuarterlyRetro {
  quarter: string;
  label: string; // e.g. "Q1 2026"
  theme: string; // single sentence
  body: string[]; // 2-3 paragraphs
  trades: string[]; // ticker references
  honestMiss: string; // one named mistake
}

export const QUARTERLY_RETROS: QuarterlyRetro[] = [
{
  quarter: 'Q1-2026',
  label: 'Q1 2026',
  theme:
  'The quarter taught us that our medium-horizon book is sharper than our short-horizon book.',
  body: [
  'Six trades closed in the quarter. Four wins, two losses. The wins were quiet — held to their target without drama — and the losses were small enough that they did not move the lifetime number.',
  'Where we got better: medium-horizon positions (CRM, WMT, MA) all worked. Where we got worse: a hedge in IWM puts that we admit was sized for an outcome we did not need to defend against. We will be slower to hedge in Q2.'],

  trades: ['CRM', 'NVDA', 'WMT', 'IWM', 'MA', 'XLE'],
  honestMiss:
  'NVDA exited at the stop after capex commentary at a competitor broke the thesis. We were 11 days from earnings; we should have sized lighter going in.'
},
{
  quarter: 'Q4-2025',
  label: 'Q4 2025',
  theme:
  'A choppy quarter where the wins were larger than the losses by accident more than design.',
  body: [
  'Five trades closed. Three wins, two losses. The QQQ call spread carried more of the quarter than we want any single trade to carry — that is a sizing learning, not a strategy learning.',
  'TGT was the cleanest miss. We assumed margin compression would arrive later than it did; it arrived earlier. The thesis was directionally right and timing wrong, which on a one-quarter horizon is the same thing.'],

  trades: ['ADBE', 'PEP', 'F', 'TGT', 'QQQ'],
  honestMiss:
  'TGT — we held the position three weeks past when the data first turned. The exit was discipline; the entry was overconfident.'
},
{
  quarter: 'Q3-2025',
  label: 'Q3 2025',
  theme:
  'Two clean wins, two clean losses, and a portfolio that ended the quarter roughly where it started.',
  body: [
  'Four trades closed. Two wins (ORCL, HD) and two losses (XOM, BA). The losses were inside the band we sized for; the wins were modest. The quarter was about not losing the book to a single trade, and we did not.',
  'Most of the work that quarter was holding the positions we already had. The trades we did not make outnumbered the trades we did.'],

  trades: ['ORCL', 'XOM', 'HD', 'BA'],
  honestMiss:
  'BA — a supply-chain item we did not see in the data we were reading. We exited at the stop; the lesson is which data sources we now monitor.'
}];


// ============================================================================
// BRIEFING ARCHIVE — past editions for the archive view
// ============================================================================

export interface BriefingArchiveEntry {
  edition: number;
  date: string;
  isoDate: string;
  headline: string;
  summary: string;
  keyActions: string[];
  dayMovePct: number;
}

export const BRIEFING_ARCHIVE: BriefingArchiveEntry[] = [
{
  edition: 142,
  date: 'Friday, May 21',
  isoDate: '2026-05-21',
  headline: 'We trimmed AMAT and added to CME.',
  summary:
  'A quiet Friday across the book. Position sizing drove the only meaningful action.',
  keyActions: ['Trimmed AMAT', 'Added to CME'],
  dayMovePct: 0.4
},
{
  edition: 141,
  date: 'Thursday, May 20',
  isoDate: '2026-05-20',
  headline: 'A soft tape; nothing in the book triggered a rule.',
  summary:
  'Held twelve through a session that did not ask anything of us. Financials cohort still compressing.',
  keyActions: ['Held twelve'],
  dayMovePct: -0.2
},
{
  edition: 140,
  date: 'Wednesday, May 19',
  isoDate: '2026-05-19',
  headline: 'MSFT moved 1.1% on no news worth naming.',
  summary:
  'A reminder that most moves are expectations adjusting, not events happening.',
  keyActions: ['No action'],
  dayMovePct: 0.6
},
{
  edition: 139,
  date: 'Tuesday, May 18',
  isoDate: '2026-05-18',
  headline: 'Opened a half-position in CME on momentum.',
  summary:
  'Half-size on a younger signal. We will revisit in three sessions before any further sizing.',
  keyActions: ['Opened CME (half)'],
  dayMovePct: 0.3
},
{
  edition: 138,
  date: 'Monday, May 17',
  isoDate: '2026-05-17',
  headline: 'A flat open; we re-read the UNH thesis.',
  summary:
  'Three weeks held without conviction. We are watching, not exiting yet.',
  keyActions: ['No action'],
  dayMovePct: 0.1
},
{
  edition: 137,
  date: 'Friday, May 14',
  isoDate: '2026-05-14',
  headline: 'The first meaningful red day in eleven sessions.',
  summary:
  'NVDA gave back 2%. Position compounded enough that ordinary volatility looks larger than it is.',
  keyActions: ['No action'],
  dayMovePct: -0.7
},
{
  edition: 136,
  date: 'Thursday, May 13',
  isoDate: '2026-05-13',
  headline: 'Quietly across the book; momentum stayed broad.',
  summary:
  'Eleven sectors green by varying amounts. Nothing in the cohort readings asked for an action.',
  keyActions: ['No action'],
  dayMovePct: 0.5
},
{
  edition: 135,
  date: 'Wednesday, May 12',
  isoDate: '2026-05-12',
  headline: 'Added to LLY into the GLP-1 cohort strength.',
  summary:
  'A second tranche on a position that has been working since Day 1 of the trade.',
  keyActions: ['Added to LLY'],
  dayMovePct: 0.8
},
{
  edition: 134,
  date: 'Tuesday, May 11',
  isoDate: '2026-05-11',
  headline: 'We closed the XLE short against the target.',
  summary:
  'A defined-risk short that worked exactly as the thesis described, in roughly the time predicted.',
  keyActions: ['Closed XLE short'],
  dayMovePct: 0.2
},
{
  edition: 133,
  date: 'Monday, May 10',
  isoDate: '2026-05-10',
  headline: 'A new week; we sat still.',
  summary:
  'No new placements. Every position carried its weight or was deliberately being given more time.',
  keyActions: ['No action'],
  dayMovePct: 0.0
},
{
  edition: 132,
  date: 'Friday, May 7',
  isoDate: '2026-05-07',
  headline: 'Opened a starter long in MA.',
  summary:
  'Sister position to V. Half-size for now; sizing depends on the next two sessions.',
  keyActions: ['Opened MA (half)'],
  dayMovePct: 0.3
},
{
  edition: 131,
  date: 'Thursday, May 6',
  isoDate: '2026-05-06',
  headline: 'We trimmed COST after a long quiet run.',
  summary: 'Position size had drifted; the thesis is intact. Trim, not exit.',
  keyActions: ['Trimmed COST'],
  dayMovePct: -0.1
}];


// ----------------------------------------------------------------------------
// TODAY'S DESK — recommendations we're placing today
// ----------------------------------------------------------------------------

export type RecSide = 'long' | 'short' | 'long-option' | 'short-option';

export interface Recommendation {
  symbol: string;
  kind: 'stock' | 'option';
  actionLabel: string;
  paragraph: string;
  contract?: string;
  entry: string;
  target: string;
  invalidate: string;
  sizing: string;
  lessonSlug?: string;

  // Paper-trading fields
  placeable: boolean; // whether users can paper-trade this directly
  side?: RecSide; // direction (when placeable)
  entryPrice?: number; // numeric entry per share (stock) or per contract (option, in dollars)
  defaultQuantity?: number; // suggested shares or contracts
  maxLossPerContract?: number; // options only — dollars at risk per contract

  // Phase 2C — Decision Desk fields. Every rec must answer 6 questions.
  why_this_idea?: string[];                   // qualities of the idea (3 bullets max)
  why_now?: string[];                         // timing signals (3 bullets max)
  why_not_others?: { rec_id: string; reason: string }[];
  invalidate_conditions?: string[];           // 1-3 bullets — what breaks it
  hold_estimate_days_min?: number;
  hold_estimate_days_max?: number;
  confidence_level?: 'low' | 'medium' | 'high';
  confidence_supporting?: string[];           // evidence backing the confidence
  confidence_limiting?: string[];             // factors capping the confidence
  expected_return_per_day_bp?: number;        // basis points/day for Why-Not-Cash
  is_arth_pick?: boolean;                     // marks "My favorite idea today"
}

export const TODAYS_DESK: {
  stocks: Recommendation[];
  options: Recommendation[];
} = {
  stocks: [
  {
    symbol: 'TSLA',
    kind: 'stock',
    actionLabel: 'Opening a short on TSLA at $172',
    paragraph:
    "Arth's read: European port inventory has built up against a flat production schedule. Historically that combination has preceded margin pressure on a 1-3 month horizon. Short a quarter-position, exit above $182 daily close.",
    entry: 'Short $172',
    target: '$148',
    invalidate: 'Daily close above $182',
    sizing: 'Quarter position',
    lessonSlug: 'what-is-a-signal',
    placeable: true,
    side: 'short',
    entryPrice: 172.0,
    defaultQuantity: 12,

    why_this_idea: [
      'Inventory pile-up at European ports is concrete + measurable',
      'Margin compression has historically followed this signal within 60 days',
      'Short bias matches a market that is broadly extended',
    ],
    why_now: [
      'Port telemetry just refreshed — inventory at 92nd %ile of last 2y',
      'Production schedule confirmed flat through Q3 (company guidance)',
      'Implied vol modest — short risk priced fairly',
    ],
    why_not_others: [
      { rec_id: 'AAPL', reason: 'AAPL spread is bullish — opposite directional bet' },
      { rec_id: 'SPY', reason: 'SPY credit spread has 60% of decay already worked through' },
    ],
    invalidate_conditions: [
      'Daily close above $182',
      'Company announces production cut (would clear the inventory)',
      'Broad market melt-up — equity beta overrides single-name thesis',
    ],
    hold_estimate_days_min: 30,
    hold_estimate_days_max: 90,
    confidence_level: 'medium',
    confidence_supporting: [
      'Inventory data is measurable + recent',
      'Same setup printed 3 winning shorts in the last 18 months',
      'Stop is defined and tight ($10 of risk per share)',
    ],
    confidence_limiting: [
      'Multi-month horizon — many things can change before catalyst',
      'TSLA is sentiment-driven; news risk can override fundamentals',
      'Sample of similar setups is small (3 wins, 2 losses, N=5)',
    ],
    expected_return_per_day_bp: 8,         // ~+8 bp/d expected
    is_arth_pick: false,                   // AAPL gets the pick
  },
  {
    symbol: 'NVDA',
    kind: 'stock',
    actionLabel: 'Trimming NVDA back to weight',
    paragraph:
    "We're trimming a quarter of NVDA today. The position has compounded enough since Day 1 that ordinary volatility now shows up as larger numbers than the thesis was sized for. The remaining three-quarters runs without change to the original target.",
    entry: 'Existing',
    target: '$1,180 on remaining',
    invalidate: 'Weekly close below $980',
    sizing: 'Trim one-quarter',
    lessonSlug: 'why-great-investors-do-nothing-most-days',
    placeable: false
  },
  {
    symbol: 'UNH',
    kind: 'stock',
    actionLabel: 'Closing the UNH half-position',
    paragraph:
    "We're closing the UNH half-position today. We've held it for twenty-two sessions without the conviction the thesis required, and waiting longer is not a thesis. We exit at the market and free the cash for a setup we'd rather hold.",
    entry: 'Existing',
    target: 'At market',
    invalidate: '—',
    sizing: 'Full close',
    lessonSlug: 'why-great-investors-do-nothing-most-days',
    placeable: false
  }],

  options: [
  {
    symbol: 'AAPL',
    kind: 'option',
    actionLabel: 'Buy the AAPL $175 / $180 call spread',
    contract: 'AAPL $175 / $180 Call Spread · Exp May 17',
    paragraph:
    "Arth's read: Implied volatility on the targeted expiry sits in the bottom quartile of the trailing year — upside exposure is unusually inexpensive right now. The maximum loss is the $3.40 debit, known up front.",
    entry: '$3.40 debit',
    target: '$5.00 max spread',
    invalidate: 'AAPL daily close below $168',
    sizing: '1.5% of book',
    placeable: true,
    side: 'long-option',
    entryPrice: 3.4,
    defaultQuantity: 4,
    maxLossPerContract: 340,

    why_this_idea: [
      'Defined-risk structure — max loss = $340 per spread, known up front',
      'IV cheap relative to historical range (bottom quartile)',
      'Reward-to-risk is ~1.5× ($1.60 max win vs $3.40 max loss)',
    ],
    why_now: [
      'AAPL IV at 22%ile of trailing year — premium is unusually cheap',
      'Bullish gamma flip yesterday (dealer hedging now buys dips)',
      'Earnings 4 weeks out — IV expansion ahead, not behind us',
    ],
    why_not_others: [
      { rec_id: 'TSLA', reason: 'TSLA short is a longer-horizon thesis with looser stop' },
      { rec_id: 'SPY',  reason: 'SPY credit spread has 60% of decay already worked through' },
    ],
    invalidate_conditions: [
      'AAPL daily close below $168',
      'IV expansion above 30%ile (premium gets too rich)',
      'Broad SPY breakdown below the 50-DMA',
    ],
    hold_estimate_days_min: 6,
    hold_estimate_days_max: 12,
    confidence_level: 'medium',
    confidence_supporting: [
      'IV percentile is mechanical + replicable',
      'Defined-risk caps the downside',
      'Similar setups (long-call-spread, low IV) returned +0.92% expectancy in the last 7',
    ],
    confidence_limiting: [
      'Earnings catalyst is 4 weeks out — guidance risk is unknown',
      "I'm relying on IV staying cheap; macro shock could expand it",
      "The historical cohort sample is still small (4 closes, 3 wins)",
    ],
    expected_return_per_day_bp: 18,         // ~+18 bp/d expected from spread decay
    is_arth_pick: true,                     // THE ONE
  },
  {
    symbol: 'SPY',
    kind: 'option',
    actionLabel: 'Sell the SPY $540 / $548 call spread for premium',
    contract: 'SPY $540 / $548 Call Spread (sold) · Exp May 31',
    paragraph:
    "Arth's read: Realized volatility has run below implied for three weeks. Selling premium harvests the gap. Max loss is the spread width less the credit — known up front.",
    entry: '$4.30 credit',
    target: 'Decay to $2.00',
    invalidate: 'SPY daily close above $545',
    sizing: '2% of book',
    placeable: true,
    side: 'short-option',
    entryPrice: 4.3,
    defaultQuantity: 5,
    maxLossPerContract: 370,

    why_this_idea: [
      'Sells premium when realized vol < implied vol',
      'Defined-risk: spread width $8 minus $4.30 credit = $3.70 max loss per contract',
      'Theta works in your favor every day SPY stays below $540',
    ],
    why_now: [
      'Realized vol has trailed implied for 3 weeks running',
      'SPY trading sideways inside a tight 5% range',
      'No major macro catalysts in the next 2 weeks',
    ],
    why_not_others: [
      { rec_id: 'AAPL', reason: 'AAPL spread is bullish + cheap-IV — opposite vol-regime bet' },
      { rec_id: 'TSLA', reason: 'TSLA short is single-name; SPY credit is index-level' },
    ],
    invalidate_conditions: [
      'SPY daily close above $545',
      'Realized vol catches up to implied (the edge evaporates)',
      'Spike in VIX above 22 (signals regime change)',
    ],
    hold_estimate_days_min: 10,
    hold_estimate_days_max: 21,
    confidence_level: 'low',
    confidence_supporting: [
      'Vol gap is measurable + persistent so far',
      'Defined-risk structure',
    ],
    confidence_limiting: [
      '60% of time-decay is already gone — late entry',
      'Tail risk on a sharp SPY breakout above $548',
      'Cohort short_credit_spread has only 1 closed call so far (insufficient sample)',
    ],
    expected_return_per_day_bp: 5,
    is_arth_pick: false,
  }]

};

// ----------------------------------------------------------------------------
// PATHS
// ----------------------------------------------------------------------------

export const PATHS: Path[] = [
{
  slug: 'how-markets-actually-work',
  tier: 'Foundations',
  title: 'How markets actually work',
  synopsis:
  'Before risk, before sizing, before any trade — a calm read of what a market is, what a price is, and why a stock moves on a day when nothing happens.',
  lessonSlugs: [
  'what-is-a-stock',
  'why-prices-move-when-nothing-happens',
  'what-is-a-signal',
  'reading-a-thesis',
  'catalysts-and-timing']

},
{
  slug: 'risk-literacy',
  tier: 'Risk + reflection',
  title: 'Risk literacy',
  synopsis:
  'Risk is not the loss. Risk is what you cannot recover from. Five lessons on drawdown, stops, and the math of staying in the game.',
  lessonSlugs: [
  'why-great-investors-do-nothing-most-days',
  'position-sizing-rule',
  'drawdown-recovery-math',
  'exiting-when-wrong']

},
{
  slug: 'options-literacy',
  tier: 'Skill',
  title: 'Options literacy',
  synopsis:
  'Precise tools for trading direction, time, and volatility. Earned access — finish Risk first.',
  lessonSlugs: [
  'options-as-leverage',
  'implied-vs-realized',
  'defined-risk-spreads']

},
{
  slug: 'portfolio-psychology',
  tier: 'Risk + reflection',
  title: 'Portfolio psychology',
  synopsis:
  'Why holding is the hardest action. Why we trim winners. What the mind does to a portfolio that the spreadsheet does not.',
  lessonSlugs: []
},
{
  slug: 'reading-signals-like-an-analyst',
  tier: 'Skill',
  title: 'Reading signals like an analyst',
  synopsis:
  'How a real signal looks, how a fake one looks, and how to tell the difference before the position is open.',
  lessonSlugs: []
}];


// ----------------------------------------------------------------------------
// LESSONS
// ----------------------------------------------------------------------------

export const LESSONS: Lesson[] = [
{
  slug: 'why-great-investors-do-nothing-most-days',
  pathSlug: 'risk-literacy',
  order: 1,
  title: 'Why great investors do nothing most days',
  abstract:
  "Most days, we don't do anything. That's not laziness. That's the discipline that compounds.",
  readMinutes: 3,
  read: true,
  connectedSymbol: 'COST',
  body: [
  {
    type: 'p',
    text: "There's a temptation, especially in the first week, to confuse activity with progress. To check the portfolio every twenty minutes. To open the briefing twice before lunch. We've built this product to teach the opposite habit."
  },
  {
    type: 'p',
    text: "Most days, we don't do anything. On Tuesday — the day this is being written — we held twelve positions through a market move of less than half a percent. No <term:trim>trim</term>, no add, no exit. The portfolio earned its keep by not being touched."
  },
  {
    type: 'pullquote',
    text: "The hardest skill is not finding the right trade. It's recognizing the days when there is no trade to make."
  },
  {
    type: 'p',
    text: "This isn't laziness. It's the discipline that compounds. Every unnecessary action introduces a small risk — of being wrong about timing, of being right too early, of paying a spread we didn't need to pay."
  },
  {
    type: 'p',
    text: 'A position that survives the noise of one quiet Tuesday is a position that may survive the next one. <term:drawdown>Drawdowns</term> are caused less by the trades we make than by the trades we make when we should have been sitting still.'
  }]

},
{
  slug: 'what-is-a-signal',
  pathSlug: 'how-markets-actually-work',
  order: 3,
  title: 'What is a signal?',
  abstract:
  'A signal is not a prediction. It is an observation about the present that, historically, has tended to precede a certain kind of movement.',
  readMinutes: 4,
  read: true,
  connectedSymbol: 'AMAT',
  body: [
  {
    type: 'p',
    text: 'A signal is the smallest unit of an investing view. It is not a forecast. It is a present-tense observation: this thing is true today, and historically when this thing has been true, prices have behaved a certain way over a certain horizon.'
  },
  {
    type: 'p',
    text: 'The signal that led us into AMAT was simple: <term:momentum>momentum</term> in the semiconductor capital-equipment cohort had quietly outpaced the broader chip index for six consecutive weeks. That is a fact. What we did with that fact is the trade.'
  },
  {
    type: 'p',
    text: "Most signals do not become trades. We watch dozens of them every morning. The ones that do become trades are the ones where the position size, the entry price, and the invalidation level can all be defined without ambiguity. If we can't draw that map, we don't take the trade."
  }]

},
{
  slug: 'why-prices-move-when-nothing-happens',
  pathSlug: 'how-markets-actually-work',
  order: 2,
  title: 'Why prices move when nothing happens',
  abstract:
  'Most price moves are not news. They are the slow work of expectations adjusting to themselves.',
  readMinutes: 5,
  read: false,
  connectedSymbol: 'MSFT',
  body: [
  {
    type: 'p',
    text: "A common misreading of markets is that prices move because something happened. They mostly don't. They mostly move because expectations about something that might happen have shifted by a small amount."
  },
  {
    type: 'p',
    text: 'Microsoft is up 0.3% today. There is no news. There is no earnings release. There is no analyst upgrade. The reason the stock is up 0.3% is that, on the margin, a few more market participants believe the future is slightly better than they believed yesterday. That is the whole event.'
  }]

},
{
  slug: 'what-is-a-stock',
  pathSlug: 'how-markets-actually-work',
  order: 1,
  title: 'What is a stock?',
  abstract:
  'A stock is a small ownership claim on a future stream of cash. Everything else is detail.',
  readMinutes: 3,
  read: false,
  connectedSymbol: 'V',
  body: [
  {
    type: 'p',
    text: 'A stock is a small claim on the future cash a business will produce. Not the cash it produced last year. Not the cash it has in the bank. The cash it will produce — across years that have not happened yet.'
  },
  {
    type: 'p',
    text: "When the price changes, what changed is the market's collective estimate of that future stream. Sometimes the estimate gets sharper. Often it gets noisier. The investor's job is to know which is which."
  }]

},
// ────────────────────────────────────────────────────────────────────
// Lovable port (Phase 3) — academy lessons, voice retuned to ArthOS.
// Schema extended: blocks now include h2, callout, list (see LessonBlock).
// ────────────────────────────────────────────────────────────────────
{
  slug: 'reading-a-thesis',
  pathSlug: 'how-markets-actually-work',
  order: 4,
  title: 'How to read (and write) a thesis',
  abstract: 'A thesis is a falsifiable claim — not a hope. If you can\'t write what would prove you wrong, you don\'t have one.',
  readMinutes: 5,
  read: false,
  connectedSymbol: 'NVDA',
  body: [
  {
    type: 'p',
    text: "Every position in this portfolio starts with a thesis. Learning to read one is the fastest way to evaluate whether to follow a call — or to write your own."
  },
  {
    type: 'h2',
    text: 'Three parts of a clean thesis'
  },
  {
    type: 'list',
    items: [
    'A claim — what you believe will happen',
    'A reason — why it should happen',
    'A break point — what would prove you wrong']

  },
  {
    type: 'callout',
    tone: 'insight',
    title: 'The break point matters most',
    text: 'Without a written break point, every dip is room for hope. With one, the exit decision is already made — you just wait to see if you were right.'
  },
  {
    type: 'p',
    text: "When the reason you bought no longer holds, the right move is almost never to wait for price to confirm. Price confirms slowly. The thesis already told you."
  },
  {
    type: 'pullquote',
    text: "A thesis you can't break is a thesis you can't trust."
  },
  {
    type: 'callout',
    tone: 'caution',
    title: 'Common mistake',
    text: 'Keeping a position because you are up. Profit is not a thesis. Exit on logic, not on PnL.'
  }]

},
{
  slug: 'catalysts-and-timing',
  pathSlug: 'how-markets-actually-work',
  order: 5,
  title: 'Catalysts: the calendar that moves prices',
  abstract: 'Most price moves are random. The few that are not cluster around catalysts you can see coming.',
  readMinutes: 4,
  read: false,
  connectedSymbol: 'AMAT',
  body: [
  {
    type: 'p',
    text: 'Earnings, macro prints, product launches — these are the visible reasons price changes. Most days, none of them happen. On the days they do, the move is rarely random.'
  },
  {
    type: 'h2',
    text: 'Four catalyst types'
  },
  {
    type: 'list',
    items: [
    'Earnings — the quarterly truth-test',
    'Macro — inflation, jobs, central bank decisions',
    'Product — launches, approvals, design wins',
    'Guidance — analyst days and capital-markets updates']

  },
  {
    type: 'p',
    text: 'A catalyst gives a thesis a deadline. It is the moment to check whether the reasoning held — not the moment to discover what the reasoning was.'
  },
  {
    type: 'callout',
    tone: 'reflect',
    title: 'Look ahead',
    text: "What is the next catalyst for the largest position you'd consider owning? If you don't know, you are not ready to size it."
  }]

},
{
  slug: 'position-sizing-rule',
  pathSlug: 'risk-literacy',
  order: 2,
  title: 'Position sizing is the whole game',
  abstract: 'Being right small and wrong big is how careers end. Size for the loss you can survive, not the gain you can imagine.',
  readMinutes: 5,
  read: false,
  connectedSymbol: 'BRK.B',
  body: [
  {
    type: 'p',
    text: "Investors obsess over what to buy. The harder, more important question is how much. <term:position-sizing>Position sizing</term> decides whether being right matters."
  },
  {
    type: 'h2',
    text: 'The one-percent floor'
  },
  {
    type: 'p',
    text: 'Risk no more than about 1% of the portfolio per idea, measured on the distance between entry and the invalidation point. This is not a law. It is a floor — the floor that keeps you in the game long enough to learn.'
  },
  {
    type: 'callout',
    tone: 'insight',
    title: 'Concentration is not conviction',
    text: "When we <term:trim>trim</term> a winner, we are not reversing the view. We are sizing it. Conviction stays. Concentration comes down."
  },
  {
    type: 'pullquote',
    text: "Size for the loss you can survive, not the gain you can imagine."
  },
  {
    type: 'callout',
    tone: 'caution',
    title: 'When in doubt',
    text: 'When conviction and concentration get tangled, the answer is almost always smaller — not out.'
  }]

},
{
  slug: 'drawdown-recovery-math',
  pathSlug: 'risk-literacy',
  order: 3,
  title: 'Drawdowns: the math you would rather not know',
  abstract: 'Losses and recoveries are asymmetric. Down 50% means you need plus 100% to break even.',
  readMinutes: 4,
  read: false,
  connectedSymbol: 'AMAT',
  body: [
  {
    type: 'p',
    text: "A <term:drawdown>drawdown</term> is not just a number. It is the asymmetry the math of recovery imposes on every account: the deeper the dip, the steeper the climb out."
  },
  {
    type: 'h2',
    text: 'The recovery table'
  },
  {
    type: 'list',
    items: [
    '−10% loss → +11% to recover',
    '−20% loss → +25% to recover',
    '−50% loss → +100% to recover',
    '−75% loss → +300% to recover']

  },
  {
    type: 'p',
    text: 'Avoiding the worst losses matters more than catching the best winners. The portfolio that never falls 50% does not need a 100% year to feel whole.'
  },
  {
    type: 'callout',
    tone: 'reflect',
    title: 'Pause here',
    text: "What is the largest single-day drop you have actually lived through with real money on the line? That is your real risk tolerance — not what a questionnaire says."
  }]

},
{
  slug: 'exiting-when-wrong',
  pathSlug: 'risk-literacy',
  order: 4,
  title: 'Exiting cleanly when you are wrong',
  abstract: 'An honest exit is worth more than a clever entry. Every mistake-log entry is a tuition bill.',
  readMinutes: 5,
  read: false,
  connectedSymbol: 'KRE',
  body: [
  {
    type: 'p',
    text: 'Every closed position with a loss is a tuition bill paid to the next position. Read them with the same care you would read a winning trade.'
  },
  {
    type: 'h2',
    text: 'Three exit triggers'
  },
  {
    type: 'list',
    items: [
    'Thesis broken — the reason no longer holds',
    'Stop hit — price moved beyond the line we drew',
    'Better opportunity — capital has a higher use elsewhere']

  },
  {
    type: 'callout',
    tone: 'insight',
    title: 'Exit on logic, not on price',
    text: 'When the second-order assumption breaks — when the thing the thesis quietly depended on stops being true — close the position. Do not wait for price to confirm what the call already said.'
  },
  {
    type: 'pullquote',
    text: "The honest exit is the one that does not require a story."
  }]

},
{
  slug: 'options-as-leverage',
  pathSlug: 'options-literacy',
  order: 1,
  title: 'Options are leverage, not lottery tickets',
  abstract: 'Calls and puts are precise tools. Used carelessly, they are expensive ones. Options trade time, not just direction.',
  readMinutes: 6,
  read: false,
  connectedSymbol: 'NVDA',
  body: [
  {
    type: 'p',
    text: 'Before you trade your first option, understand what you are buying: a contract that gives you the right — not the obligation — to act, before a specific date.'
  },
  {
    type: 'h2',
    text: 'Two contracts, two directions'
  },
  {
    type: 'list',
    items: [
    'A call gives you the right to buy — bullish exposure',
    'A put gives you the right to sell — bearish or protective exposure']

  },
  {
    type: 'callout',
    tone: 'caution',
    title: 'Time decays. Always.',
    text: 'Every option loses value every day, all else equal. You are not just betting on direction — you are betting on it happening in time.'
  },
  {
    type: 'pullquote',
    text: "An option is a position with a deadline."
  }]

},
{
  slug: 'implied-vs-realized',
  pathSlug: 'options-literacy',
  order: 2,
  title: 'Implied vs realized — the only edge worth chasing',
  abstract: 'When the market prices a bigger move than usually happens, premium-sellers eat. The spread is the edge.',
  readMinutes: 6,
  read: false,
  connectedSymbol: 'NVDA',
  body: [
  {
    type: 'p',
    text: 'Most option edges reduce to one question: is implied volatility rich or cheap relative to what tends to actually happen?'
  },
  {
    type: 'h2',
    text: 'The percentile case'
  },
  {
    type: 'p',
    text: 'When the implied move sits in the 78th percentile of trailing implieds, that is a structural setup — not a directional view. Premium-selling expressions get cleaner the further into the upper tail you go.'
  },
  {
    type: 'callout',
    tone: 'insight',
    title: 'The spread is the edge',
    text: 'If the option market is pricing a 7% move and the stock has historically moved 5% in that window, selling the premium is selling the spread. The trade is not about direction — it is about the gap.'
  },
  {
    type: 'pullquote',
    text: "Sell when premium is rich; buy when it is cheap. The rest is execution."
  }]

},
{
  slug: 'defined-risk-spreads',
  pathSlug: 'options-literacy',
  order: 3,
  title: 'Defined-risk spreads: capping the worst case',
  abstract: 'Naked options can lose multiples of premium. Spreads define your worst case up front — at the cost of capping your best case too.',
  readMinutes: 5,
  read: false,
  connectedSymbol: 'NVDA',
  body: [
  {
    type: 'p',
    text: 'A spread structure is two options of the same type, opened together, with one offsetting the other. The result is a position whose worst case is a known dollar number — not a theoretical multiple.'
  },
  {
    type: 'h2',
    text: 'The trade-off in one line'
  },
  {
    type: 'p',
    text: 'You give up uncapped upside in exchange for a known maximum loss. For most beginners, that trade is worth making every time.'
  },
  {
    type: 'callout',
    tone: 'reflect',
    title: 'Stop and ask',
    text: 'Of the last five paper trades you have opened, could you have stated the maximum loss in one number before clicking? If not, the structure is the problem.'
  },
  {
    type: 'pullquote',
    text: "Trade structures whose worst case you can name before you click."
  }]

}];


export function getLesson(slug: string) {
  return LESSONS.find((l) => l.slug === slug);
}
export function getLessonsForPath(pathSlug: string) {
  return LESSONS.filter((l) => l.pathSlug === pathSlug).sort(
    (a, b) => a.order - b.order
  );
}

// ----------------------------------------------------------------------------
// GLOSSARY
// ----------------------------------------------------------------------------

export const GLOSSARY: GlossaryTerm[] = [
{
  slug: 'drawdown',
  term: 'drawdown',
  shortDefinition: 'The percentage decline from a peak to the next trough.',
  longDefinition:
  "A drawdown is the percentage decline from a portfolio's recent peak to its next trough. It is the single number that tells you what the worst stretch felt like in real time — not the return, but the depth of the dip before recovery.",
  body: 'A drawdown is the percentage decline from a recent peak to the next trough. It is not the return. It is the worst stretch — the deepest point of the dip, before recovery. Most investors are not undone by an average year. They are undone by the months inside that year when the drawdown felt larger than they had imagined it could.',
  examples: [
  {
    symbol: 'AMAT',
    date: '2026-04-12',
    outcome: 'A 3.8% drawdown over four sessions, recovered in eleven.'
  },
  {
    symbol: 'BRK.B',
    date: '2026-02-18',
    outcome:
    'A 5.1% drawdown that held us out of new positions for two weeks.'
  }],

  lessonRefs: ['why-great-investors-do-nothing-most-days']
},
{
  slug: 'stop-loss',
  term: 'stop-loss',
  shortDefinition:
  'A pre-decided price at which a position is exited regardless of belief.',
  longDefinition:
  'A stop-loss is a price decided before the trade is on. If the position reaches that price, we exit — regardless of belief, regardless of new information, regardless of how the day feels. The discipline is in deciding it before, not after.',
  body: 'A stop-loss is a price we agree to before the position is opened. If price reaches it, we exit — without negotiation, without revisiting the thesis, without checking how we feel. The point of a stop is not to be correct. The point is to keep the next mistake small enough to recover from.',
  examples: [
  {
    symbol: 'NVDA',
    date: '2026-03-04',
    outcome:
    'Exited at the stop after a 6.1% loss on a thesis that had broken.'
  }],

  lessonRefs: []
},
{
  slug: 'trim',
  term: 'trim',
  shortDefinition: 'Selling part of a position to reduce size, not to exit.',
  longDefinition:
  'To trim is to sell part of a position, not all of it. We trim when the position has grown beyond the size the thesis would justify — usually because price ran ahead of the original entry. The view stays on. The size comes down.',
  body: 'Trimming is selling a portion of a position to bring its size back into line. The thesis remains in place. What has changed is weight: the position has grown to occupy more of the portfolio than we would size it from scratch today. Trimming is the most underused tool a beginner has, because it requires selling something that is still working.',
  examples: [
  {
    symbol: 'AMAT',
    date: '2026-05-21',
    outcome:
    'Trimmed after a 4% run because position size had drifted above our band.'
  }],

  lessonRefs: ['why-great-investors-do-nothing-most-days']
},
{
  slug: 'momentum',
  term: 'momentum',
  shortDefinition:
  "The tendency for recent winners to keep winning, and recent losers to keep losing — until they don't.",
  longDefinition:
  "Momentum is the tendency for recent winners to keep winning and recent losers to keep losing — until they don't. It is one of the most documented patterns in markets, and one of the most difficult to use, because the moment momentum reverses, it does so quickly.",
  body: 'Momentum is a pattern: assets that have outperformed recently tend to keep outperforming for a period — and then, often suddenly, they stop. It is one of the few patterns that survives rigorous testing across decades and markets. It is also one of the hardest to act on, because the discipline of riding momentum requires sitting through reversals that, on the day, are indistinguishable from the end.',
  examples: [
  {
    symbol: 'AMAT',
    date: '2026-05-04',
    outcome:
    'A six-week momentum signal that led to a position opened on Day 1.'
  }],

  lessonRefs: ['what-is-a-signal']
},
// ────────────────────────────────────────────────────────────────────
// Lovable port (Phase 3) — academy glossary terms, voice retuned.
// ────────────────────────────────────────────────────────────────────
{
  slug: 'thesis',
  term: 'thesis',
  shortDefinition: 'The written reason a position is open — claim, reason, and break point.',
  longDefinition:
  'A thesis names what you believe, why it should happen, and what would prove you wrong. Without the break point, every dip becomes room for hope. With it, the exit is already decided.',
  body:
  'A thesis is the written reason a position is on. It names a claim, a reason that claim should hold, and the specific evidence that would falsify it. The third part is the one most beginners skip — and the one that matters most when the position moves against them.',
  examples: [
  {
    symbol: 'NVDA',
    date: '2026-05-22',
    outcome:
    'Trimmed semis exposure when hyperscaler-capex thesis remained intact but concentration drifted past 5%.'
  }],

  lessonRefs: ['reading-a-thesis', 'exiting-when-wrong']
},
{
  slug: 'catalyst',
  term: 'catalyst',
  shortDefinition: 'A specific event expected to move a price — earnings, macro print, product launch.',
  longDefinition:
  'A catalyst is a dated event that gives a thesis a deadline and a moment to be checked. Earnings, macro prints, regulatory decisions, product launches. Without a catalyst, a thesis is a slow-burn opinion; with one, it has a verification point.',
  body:
  "Catalysts cluster in time and matter unequally. Earnings cluster ahead of macro prints. Product launches cluster around design wins. The skill is not in spotting every catalyst — it is in knowing which ones the position you hold actually depends on.",
  examples: [
  {
    symbol: 'NVDA',
    date: '2026-05-28',
    outcome:
    'Nvidia FQ1 earnings was the dated catalyst behind the semis sizing call.'
  }],

  lessonRefs: ['catalysts-and-timing']
},
{
  slug: 'position-sizing',
  term: 'position sizing',
  shortDefinition: 'How much of the portfolio a single idea is allowed to risk.',
  longDefinition:
  "Position sizing is the most underrated lever in investing. A great idea sized wrong becomes a small win or a career-ending loss. The right size for a thesis is usually smaller than the size emotion wants to take.",
  body:
  'Position sizing decides whether being right matters. Sized too large, a position becomes hard to hold through ordinary volatility. Sized too small, it becomes irrelevant to the outcome. Most of the work in this portfolio happens here — not in stock selection.',
  examples: [
  {
    symbol: 'NVDA',
    date: '2026-05-22',
    outcome:
    'Trimmed from 8% to 4.5% — kept directional exposure without exceeding 5% per name into a catalyst cluster.'
  }],

  lessonRefs: ['position-sizing-rule', 'drawdown-recovery-math']
},
{
  slug: 'earnings',
  term: 'earnings',
  shortDefinition: 'Quarterly reports — the cleanest test of a thesis.',
  longDefinition:
  'Every public company reports earnings four times a year. The print plus the guidance is where most stock-specific repricing happens. Earnings clusters compress catalyst risk into a few-day window.',
  body:
  'An earnings print is a thesis verification event with a calendar date. The number itself matters less than the guidance attached and the questions answered on the call. A position sized through an earnings cluster is a position sized for the variance of three or four such events, not one.',
  examples: [
  {
    symbol: 'NVDA',
    date: '2026-05-28',
    outcome: 'Three back-to-back semis prints over five trading days created a catalyst cluster.'
  }],

  lessonRefs: ['catalysts-and-timing']
},
{
  slug: 'multiple',
  term: 'multiple',
  shortDefinition: 'What investors pay per dollar of earnings.',
  longDefinition:
  'A 20x multiple means investors are paying $20 today for $1 of annual earnings. Multiples expand and contract with mood, growth expectations, and rates — sometimes more than the underlying earnings ever do.',
  body:
  'Two companies with identical earnings can trade at very different prices because the market awards them different multiples. The multiple is the part of the price that has nothing to do with this quarter — it is the part that is about every future quarter, discounted.',
  examples: [],
  lessonRefs: []
},
{
  slug: 'call',
  term: 'call option',
  shortDefinition: 'The right to buy at a set price, before a date.',
  longDefinition:
  'A call gives you the right — not the obligation — to buy 100 shares at the strike price before expiry. Bullish exposure with the downside capped at the premium paid.',
  body:
  'Calls express directional views with leverage. The upside scales with the underlying; the downside is bounded by the premium. The trade-off is time: every day the contract loses value, all else equal. Calls are the simplest options instrument and the one beginners most often misuse.',
  examples: [],
  lessonRefs: ['options-as-leverage', 'defined-risk-spreads']
},
{
  slug: 'put',
  term: 'put option',
  shortDefinition: 'The right to sell at a set price, before a date.',
  longDefinition:
  "Puts are insurance or bearish bets. Used as insurance, they cap how much you can lose on a stock you already own; used directionally, they express a downside view with bounded loss.",
  body:
  'A put is the mirror of a call. It pays when the underlying falls below the strike before expiry. As insurance on a long position, it converts uncapped downside into a defined one — for a known cost.',
  examples: [],
  lessonRefs: ['options-as-leverage', 'defined-risk-spreads']
},
{
  slug: 'iv',
  term: 'implied volatility',
  shortDefinition: "The market's forecast of how much a stock will move.",
  longDefinition:
  'Implied volatility is the expected-move number baked into option prices. High IV means premium is rich — sellers get paid more. Low IV means premium is cheap — buyers get optionality for less. The skill is reading which side of that trade the current pricing favors.',
  body:
  'Implied volatility is a forecast — not a guarantee. The history of options trading is in the gap between what was implied and what was realized. When that gap is wide and persistent, structural edge appears for one side or the other.',
  examples: [
  {
    symbol: 'NVDA',
    date: '2026-05-22',
    outcome: "Straddle implied ~7.4% vs realized 4.9% trailing 30 days."
  }],

  lessonRefs: ['implied-vs-realized']
},
{
  slug: 'straddle',
  term: 'straddle',
  shortDefinition: 'Buying (or selling) both a call and a put at the same strike.',
  longDefinition:
  "A straddle expresses a view on volatility — not direction. Long straddles profit from a big move either way; short straddles profit from a stock that does not move much.",
  body:
  'The straddle is the cleanest volatility expression in the options book. Long, it pays when realized exceeds implied. Short, it pays when realized stays inside implied. It is a directionally neutral way to take a view on whether the market is over- or under-estimating future movement.',
  examples: [
  {
    symbol: 'NVDA',
    date: '2026-05-22',
    outcome:
    'Straddle pricing at the 78th percentile of trailing IV made premium-selling the cleaner expression.'
  }],

  lessonRefs: ['implied-vs-realized']
},
{
  slug: 'mean-reversion',
  term: 'mean reversion',
  shortDefinition: "Prices that ran a long way fast tend to retrace part of the move.",
  longDefinition:
  'Mean reversion is the empirical tendency for prices that have moved far in a short time to retrace some of that move — particularly when the move was not matched by an equivalent change in fundamentals. It is the mirror of momentum, and the two coexist on different horizons.',
  body:
  'A real mean-reversion setup requires both an extreme move and a clear reason that the move was unjustified — not just the move alone. Most trades beginners call mean reversion are momentum trades taken in the wrong direction.',
  examples: [],
  lessonRefs: []
}];


export function getTerm(slug: string) {
  return GLOSSARY.find((t) => t.slug === slug);
}

// ----------------------------------------------------------------------------
// CONCEPTS
// ----------------------------------------------------------------------------

export const CONCEPTS: Concept[] = [
{
  slug: 'momentum',
  title: 'Momentum',
  definition:
  'Momentum is the empirical tendency for assets that have outperformed recently to continue outperforming over the next several weeks to months — and the matching tendency for recent laggards to continue lagging. It is one of the few patterns that has survived testing across decades, geographies, and asset classes.',
  body: 'Momentum sits at the center of how we read short-horizon signals. We look for cohorts where momentum has been quietly accumulating — not the headline names, but the second-tier names in a sector that has been outperforming. Those tend to be the positions where momentum has more room to run, because the market has not yet noticed.',
  examples: [
  {
    symbol: 'AMAT',
    date: '2026-05-04',
    outcome: 'Entered on a six-week momentum signal in semicap.'
  },
  {
    symbol: 'CME',
    date: '2026-05-19',
    outcome:
    'Half-position opened on a momentum signal in exchange operators.'
  }]

},
{
  slug: 'mean-reversion',
  title: 'Mean reversion',
  definition:
  'Mean reversion is the empirical tendency for prices that have moved a long distance in a short time to retrace some of that move — particularly when the move has not been accompanied by an equivalent change in fundamentals. It is the mirror image of momentum, and the two coexist on different horizons.',
  body: 'We use mean reversion sparingly. The trade most beginners think is a mean reversion is usually a momentum trade in the wrong direction. A real mean reversion setup requires both an extreme move and a clear reason the move was unjustified — not just the move alone.',
  examples: []
},
{
  slug: 'position-sizing',
  title: 'Position sizing',
  definition:
  'Position sizing is the question of how much capital a single position should carry. It is the variable that, more than any other, determines whether a correct view becomes a profitable trade — and whether a wrong view becomes a recoverable loss.',
  body: 'A position sized too large becomes hard to hold through ordinary volatility. A position sized too small becomes irrelevant to the outcome. Most of the work we do happens here, not in stock selection. The right position size for a thesis is usually smaller than the size emotion wants us to take.',
  examples: [
  {
    symbol: 'AMAT',
    date: '2026-05-21',
    outcome: 'Trimmed back to target weight after price ran ahead.'
  }]

}];


export function getConcept(slug: string) {
  return CONCEPTS.find((c) => c.slug === slug);
}

// ----------------------------------------------------------------------------
// EVIDENCE LAYER — Today's "what changed" diff + as-of stamps
// ----------------------------------------------------------------------------
//
// Static for tier-1 screenshot validation. Once Today/Pick bind to
// the real APIs the same shapes are produced by the briefing-narrative
// generator + the recommendation envelope service.

export interface AsOfStamp {
  isoDate: string;        // '2026-05-21T16:00:00-04:00'
  prettyDate: string;     // 'Friday May 21, 4:00pm ET'
  windowDescription: string; // 'Snapshot after the close, post-settlement data'
}

export const BRIEFING_AS_OF: AsOfStamp = {
  isoDate: '2026-05-21T16:00:00-04:00',
  prettyDate: 'Friday, May 21 · 4:00pm ET',
  windowDescription:
    'Snapshot taken after the close. Twelve positions held; five placements on the desk; momentum readings from the post-settlement bar.',
};

export interface ChangedItem {
  symbol?: string;        // optional ticker the change is tied to
  headline: string;       // 6-10 word summary
  body: string;           // 1 sentence narrative
}

export const WHAT_CHANGED_SINCE_YESTERDAY: ChangedItem[] = [
  {
    symbol: 'AMAT',
    headline: 'AMAT crossed the position-size band.',
    body: 'Six sessions of +4.1% cumulative run pushed AMAT above the weight we sized for at entry. The trim today is the response.',
  },
  {
    symbol: 'CME',
    headline: 'CME signal held a third session.',
    body: 'The exchange-operator momentum reading we opened CME on Tuesday is still firing without giving back. We added to bring it from half to full size.',
  },
  {
    headline: 'Financials cohort compressed for the second week.',
    body: 'Momentum readings across XLF constituents are tightening into a range. Historically this resolves into a move but rarely tells us which direction in advance.',
  },
  {
    symbol: 'NVDA',
    headline: 'NVDA closed unchanged for the first time in eight sessions.',
    body: 'Multi-day quiet from a name that has compounded enough to make ordinary volatility look outsized. We did not act.',
  },
];

export interface SignalRef {
  label: string;          // 'Six-week momentum'
  source: string;         // 'Sector relative-strength · Tiingo daily bars'
  reading: string;        // '+8.4% vs cohort average'
}

export interface CatalystRef {
  date: string;           // '2026-05-30'
  prettyDate: string;     // 'May 30'
  label: string;          // 'AMAT earnings'
  note?: string;          // 'We will not add into the print.'
}

export interface ThesisEvolutionEntry {
  date: string;           // ISO
  prettyDate: string;     // 'May 4'
  note: string;           // 1-2 sentence change description
}

export interface PickEvidence {
  asOf: AsOfStamp;
  signals: SignalRef[];
  dataSources: string[];
  confidence: 'we would hold' | 'we are watching' | 'we are reducing';
  confidenceNote: string;
  horizon: string;        // 'Multi-week (3-8 sessions remaining in this regime)'
  catalysts: CatalystRef[];
  bullCase: string;       // narrative
  bearCase: string;       // narrative
  thesisEvolution: ThesisEvolutionEntry[];
  reviewDate: string;     // 'Tuesday May 27' — when we re-read the thesis
}

export const PICK_EVIDENCE: Record<string, PickEvidence> = {
  AMAT: {
    asOf: BRIEFING_AS_OF,
    signals: [
      {
        label: 'Six-week sector momentum',
        source: 'Semicap cohort relative-strength · Tiingo daily bars',
        reading: '+8.4% vs broad chip index, 32 of 42 sessions positive',
      },
      {
        label: 'Balance-sheet quality screen',
        source: 'Quarterly fundamentals · 4-quarter trailing',
        reading: 'Top quintile of cohort on net-debt / EBITDA',
      },
      {
        label: 'Position-size drift',
        source: 'Internal portfolio accounting',
        reading: 'Weight at 5.2% vs sized 4.0% at entry — out of band',
      },
    ],
    dataSources: ['Tiingo daily bars', 'Polygon delayed quotes', 'FRED macro context'],
    confidence: 'we are reducing',
    confidenceNote:
      'The thesis is intact. The size is not. Reducing is the right move when the position has run, not the wrong one when the company is still working.',
    horizon: 'Multi-week — we sized this for a six-to-twelve-week move; we are about halfway through.',
    catalysts: [
      {
        date: '2026-05-30',
        prettyDate: 'May 30',
        label: 'AMAT earnings',
        note: 'We will not add into the print.',
      },
      {
        date: '2026-06-12',
        prettyDate: 'June 12',
        label: 'Semicap industry sales data',
        note: 'Cohort-wide readout; less stock-specific.',
      },
    ],
    bullCase:
      'Semicap momentum has been broader than the headline chip cohort for six straight weeks; AMAT carries the cleanest balance sheet in the group; valuation has not expanded to match the underlying cash-flow trajectory. If the cycle holds another quarter, the cohort re-rates and AMAT leads.',
    bearCase:
      'A capex commentary reset at any of the three large customers (Intel, TSMC, Samsung) would break the cohort thesis in a single session. The position has compounded enough that a thesis break costs more in dollar terms than the original entry would have implied. We carry that risk knowingly.',
    thesisEvolution: [
      {
        date: '2026-05-04',
        prettyDate: 'May 4',
        note: 'Opened on the six-week cohort momentum read. Sized at 4% of book.',
      },
      {
        date: '2026-05-15',
        prettyDate: 'May 15',
        note: 'Cohort reading strengthened; we held without adding.',
      },
      {
        date: '2026-05-21',
        prettyDate: 'May 21',
        note: 'Trimmed a quarter because weight had drifted to 5.2%. Thesis unchanged.',
      },
    ],
    reviewDate: 'Tuesday May 27',
  },
  MSFT: {
    asOf: BRIEFING_AS_OF,
    signals: [
      {
        label: 'Cash-flow growth vs sector',
        source: 'Quarterly cash flow · 4-quarter trailing',
        reading: '+14% YoY vs software cohort +6%',
      },
      {
        label: 'Price-to-cash-flow gap',
        source: 'Internal valuation screen',
        reading: 'Trading at 18x; cohort median 22x',
      },
    ],
    dataSources: ['Tiingo fundamentals', 'Tiingo daily bars'],
    confidence: 'we would hold',
    confidenceNote:
      'Multi-quarter thesis. Daily moves are not the point. We re-read this thesis monthly.',
    horizon: 'Multi-quarter — opened Day 1 of the book, expected to run multiple quarters.',
    catalysts: [
      {
        date: '2026-07-25',
        prettyDate: 'July 25',
        label: 'MSFT earnings',
        note: 'Cloud-bookings line will either confirm or reset the thesis.',
      },
    ],
    bullCase:
      'Twelve-month operating cash flow growth has outpaced the broader software sector for six straight quarters. The multiple has not expanded to match. Historically these cash-flow / multiple gaps close.',
    bearCase:
      'A material slowdown in cloud bookings would reset both the cash-flow trajectory and the multiple in the same print. We carry concentrated AI exposure here that we are not specifically sizing against.',
    thesisEvolution: [
      {
        date: '2026-03-19',
        prettyDate: 'March 19',
        note: 'Opened on Day 1 of the portfolio. Sized 5% of book.',
      },
      {
        date: '2026-04-25',
        prettyDate: 'April 25',
        note: 'Earnings confirmed the cash-flow gap. No action.',
      },
    ],
    reviewDate: 'Monday June 2',
  },
  COST: {
    asOf: BRIEFING_AS_OF,
    signals: [
      {
        label: 'Membership renewal rate',
        source: 'Quarterly company disclosure',
        reading: '93% global · multi-year high',
      },
      {
        label: 'Same-store sales',
        source: 'Quarterly · trailing 4 quarters',
        reading: '+5.8% on flat traffic — pricing power',
      },
    ],
    dataSources: ['Tiingo fundamentals', 'Company filings'],
    confidence: 'we would hold',
    confidenceNote:
      'Compounder. The job of this position is to compound while we spend attention on positions that need it.',
    horizon: 'Multi-year — measured in quarters, not weeks.',
    catalysts: [
      {
        date: '2026-05-29',
        prettyDate: 'May 29',
        label: 'COST monthly comps',
        note: 'Routine; the data either confirms the model or it does not.',
      },
    ],
    bullCase:
      'Membership economics remain at multi-year highs. Same-store sales positive on flat traffic — the model itself, not promotional activity. Capital allocation is consistent and unsurprising.',
    bearCase:
      'A step-down in renewal rates would materially change the value of every other line. Compression in membership-fee economics is the only thing that breaks this thesis.',
    thesisEvolution: [
      {
        date: '2026-04-04',
        prettyDate: 'April 4',
        note: 'Opened on Day 1 as a long-horizon compounder.',
      },
    ],
    reviewDate: 'Friday June 6',
  },
};

export function getPickEvidence(symbol: string): PickEvidence | undefined {
  return PICK_EVIDENCE[symbol];
}

// ----------------------------------------------------------------------------
// OPPORTUNITIES — Phase 1 surface
// ----------------------------------------------------------------------------
//
// Three tiers describe the STATE of the setup, not our action or our
// confidence. Educational framing: a beginner reads them as "what does
// the data look like" rather than "is the AI sure".
//
//   Tier 1 — Strongest setups today      (most signals firing, ready to act)
//   Tier 2 — Setups still forming        (mixed signals, sized lighter)
//   Tier 3 — Names we're tracking        (criteria met but not acting)

export type OpportunityTier =
  | 'strongest-setups'
  | 'setups-forming'
  | 'tracking';

// Setup Strength — 5 objective criteria. Each criterion is a verifiable
// condition about the SIGNAL itself, not about our confidence. Beginner
// can read each one and learn what makes a setup good.
export interface SetupCriterion {
  label: string;            // 'Signal density'
  met: boolean;
  note: string;             // '3 independent reads agree' OR 'only 1 read'
  lessonSlug?: string;      // optional teaching link
}

export interface SetupStrength {
  score: number;            // 0-5
  criteria: SetupCriterion[];
}

export interface IntelligenceContent {
  whyItMatters: string;     // 1-3 sentences
  whatCouldChangeIt: string; // 1-2 sentences (invalidation)
  whatWeWatch: string[];    // forward signals
}

export interface OpportunityCard {
  symbol: string;
  kind: 'stock' | 'option';
  tier: OpportunityTier;
  actionLabel: string;      // 'Opening a short on TSLA at $172'
  contract?: string;
  entry: string;
  target: string;
  invalidate: string;
  sizing: string;
  setup: SetupStrength;
  intelligence: IntelligenceContent;
  lessonSlug: string;
  placeable: boolean;
  // For the trade sheet (existing Recommendation contract)
  side?: 'long' | 'short' | 'long-option' | 'short-option';
  entryPrice?: number;
  defaultQuantity?: number;
  maxLossPerContract?: number;
  paragraph: string;        // narrative used by TradeSheet
}

export interface TrackingName {
  symbol: string;
  oneLineSetup: string;
  setupScore: number;
  whatToWatch: string;
}

export const TRACKING_NAMES: TrackingName[] = [
  {
    symbol: 'NFLX',
    oneLineSetup: 'Momentum signal forming — 3 sessions in',
    setupScore: 2,
    whatToWatch: 'Two more sessions to confirm the cohort read',
  },
  {
    symbol: 'XLE',
    oneLineSetup: 'Sector reversal candidate — early in the read',
    setupScore: 2,
    whatToWatch: 'Crude curve flattening confirmation',
  },
  {
    symbol: 'COIN',
    oneLineSetup: 'Earnings volatility setup — 10 days to print',
    setupScore: 3,
    whatToWatch: 'IV expansion timing relative to earnings move',
  },
  {
    symbol: 'GLD',
    oneLineSetup: 'Macro hedge candidate — regime check needed',
    setupScore: 2,
    whatToWatch: 'Dollar index reaction to next CPI print',
  },
];

// ────────── WHAT WE PASSED ON ──────────
// Each rejection is a teachable moment. The user sees the criterion
// that failed and can click through to the lesson explaining why
// that criterion exists.

export interface PassedItem {
  symbol: string;
  setupScore: number;       // out of 5
  failedCriterion: string;  // 'Signal density too low'
  reason: string;           // 1-sentence explanation
  lessonSlug: string;       // teaching link
}

export const PASSED_ON_TODAY: PassedItem[] = [
  {
    symbol: 'NVDA',
    setupScore: 3,
    failedCriterion: 'Already held — sizing logic prevents add',
    reason:
      "NVDA is held at +27% from cost basis. Adding here would concentrate the book further; we sized it once already at entry.",
    lessonSlug: 'why-great-investors-do-nothing-most-days',
  },
  {
    symbol: 'TLT',
    setupScore: 4,
    failedCriterion: 'Earnings within 5 sessions',
    reason:
      "We don't enter positions inside earnings windows — the signal would be confounded by a known volatility event.",
    lessonSlug: 'what-is-a-signal',
  },
  {
    symbol: 'AMZN',
    setupScore: 2,
    failedCriterion: 'Signal density too low',
    reason:
      "Only one read firing (momentum); the fundamentals scan and the cohort scan are both neutral. We require at least two independent reads for a full-size entry.",
    lessonSlug: 'what-is-a-signal',
  },
  {
    symbol: 'KO',
    setupScore: 3,
    failedCriterion: 'Risk-reward below 2:1',
    reason:
      "Target was $5 above entry; invalidation $4 below. The math doesn't compensate for the position cost over the expected horizon.",
    lessonSlug: 'what-is-a-signal',
  },
  {
    symbol: 'WBA',
    setupScore: 1,
    failedCriterion: 'Liquidity below threshold',
    reason:
      "Average daily volume has fallen below our minimum for the position size we'd want to take. Slippage would eat the edge.",
    lessonSlug: 'what-is-a-signal',
  },
  {
    symbol: 'PLTR',
    setupScore: 2,
    failedCriterion: 'Base rate insufficient',
    reason:
      "The setup type has fewer than 5 historical precedents in our data window. We don't size into setups we can't calibrate.",
    lessonSlug: 'what-is-a-signal',
  },
];

export const PASSED_ON_TOTAL_SCREENED = 14;

// ----------------------------------------------------------------------------
// REVIEW QUEUE — derived from PICK_EVIDENCE.reviewDate
// ----------------------------------------------------------------------------

export interface ReviewQueueItem {
  symbol: string;
  company: string;
  dueDate: string;          // 'Tuesday May 27'
  daysFromToday: number;    // negative = overdue
  thesisLastTouched: string;
  reason: string;
}

// ----------------------------------------------------------------------------
// SINCE YESTERDAY — MVP Phase A continuity bridge
// ----------------------------------------------------------------------------
//
// Three short paragraphs that show "yesterday's story continued today."
// Editorial register. Always present (even quiet days carry a "we held
// the rest" line). Cold-start fallback handled in the hero component.

export interface SinceYesterdayItem {
  text: string;
  link?: { label: string; to: string };
}

export const SINCE_YESTERDAY: SinceYesterdayItem[] = [
  {
    text: "We trimmed AMAT — fill cleared at $199.50. The thesis is intact; the size is now back to the band we sized at entry.",
    link: { label: 'See the position', to: '/v2/today/pick/AMAT' },
  },
  {
    text: "CRM half-position held; the cohort read confirmed for a third session.",
    link: { label: 'See today\'s setups', to: '/v2/opportunities' },
  },
  {
    text: "One catalyst fired overnight: pre-CPI dispersion narrowed. Field note posted.",
    link: { label: 'Read the note', to: '/v2/field-notes' },
  },
];

export const REVIEW_QUEUE: ReviewQueueItem[] = [
  {
    symbol: 'UNH',
    company: 'UnitedHealth Group',
    dueDate: 'Today',
    daysFromToday: 0,
    thesisLastTouched: 'April 29',
    reason: '22 sessions held without the conviction we sized for. Time to decide: full size, half size, or close.',
  },
  {
    symbol: 'AMAT',
    company: 'Applied Materials',
    dueDate: 'Tuesday May 27',
    daysFromToday: 4,
    thesisLastTouched: 'May 21',
    reason: 'Position trimmed today; review whether the remaining 3/4 still earns its weight.',
  },
  {
    symbol: 'MSFT',
    company: 'Microsoft',
    dueDate: 'Monday June 2',
    daysFromToday: 12,
    thesisLastTouched: 'April 25',
    reason: 'Monthly re-read on a multi-quarter thesis. Confirm the cash-flow gap is still open.',
  },
  {
    symbol: 'COST',
    company: 'Costco Wholesale',
    dueDate: 'Friday June 6',
    daysFromToday: 16,
    thesisLastTouched: 'May 4',
    reason: 'Monthly compounder re-read. Verify renewal-rate slope still intact.',
  },
];

// ----------------------------------------------------------------------------
// PORTFOLIO
// ----------------------------------------------------------------------------

export const PORTFOLIO: PortfolioSnapshot = {
  edition: 142,
  dateLong: 'Friday, May 21',
  dateShort: 'May 21',
  dayMovePct: 0.4,
  lifetimeMovePct: 18.7,
  equity: 118742.51,
  positions: [
  {
    symbol: 'AMAT',
    company: 'Applied Materials',
    costBasis: 192.1,
    current: 199.85,
    dayHeld: 18,
    thesisShort: 'Momentum in semicap.'
  },
  {
    symbol: 'CME',
    company: 'CME Group',
    costBasis: 224.5,
    current: 228.1,
    dayHeld: 4,
    thesisShort: 'Exchange-operator momentum.'
  },
  {
    symbol: 'MSFT',
    company: 'Microsoft',
    costBasis: 380.1,
    current: 412.5,
    dayHeld: 64,
    thesisShort: 'Cash-flow growth ahead of multiple.'
  },
  {
    symbol: 'V',
    company: 'Visa',
    costBasis: 268.4,
    current: 281.2,
    dayHeld: 86,
    thesisShort: 'Compounder. Holding.'
  },
  {
    symbol: 'COST',
    company: 'Costco Wholesale',
    costBasis: 798.1,
    current: 862.1,
    dayHeld: 47,
    thesisShort: 'Membership economics.'
  },
  {
    symbol: 'GOOGL',
    company: 'Alphabet',
    costBasis: 158.2,
    current: 169.4,
    dayHeld: 31,
    thesisShort: 'Search margins durable.'
  },
  {
    symbol: 'NVDA',
    company: 'NVIDIA',
    costBasis: 854.3,
    current: 1086.4,
    dayHeld: 92,
    thesisShort: 'Data-center capex cycle.'
  },
  {
    symbol: 'BRK.B',
    company: 'Berkshire Hathaway',
    costBasis: 408.2,
    current: 419.1,
    dayHeld: 121,
    thesisShort: 'Cash + optionality.'
  },
  {
    symbol: 'JPM',
    company: 'JPMorgan Chase',
    costBasis: 188.4,
    current: 195.2,
    dayHeld: 56,
    thesisShort: 'Net-interest stability.'
  },
  {
    symbol: 'UNH',
    company: 'UnitedHealth Group',
    costBasis: 502.1,
    current: 488.4,
    dayHeld: 22,
    thesisShort: 'Half-size, watching.'
  },
  {
    symbol: 'LLY',
    company: 'Eli Lilly',
    costBasis: 712.4,
    current: 768.2,
    dayHeld: 38,
    thesisShort: 'GLP-1 cohort momentum.'
  },
  {
    symbol: 'MA',
    company: 'Mastercard',
    costBasis: 462.1,
    current: 478.4,
    dayHeld: 86,
    thesisShort: 'Sister position to V.'
  }]

};

export function getPosition(symbol: string) {
  return PORTFOLIO.positions.find((p) => p.symbol === symbol);
}