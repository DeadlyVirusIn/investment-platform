// optionPlain — translate a PresentedOption (trader/engine vocabulary) into
// beginner-safe language for the "Options Ideas — Advanced Practice" lane
// (Sprint M). Derives copy from STRUCTURED fields only (tone, strategy, dte,
// economics) — never passes raw engine fit-reasons through, so banned jargon
// (DTE, IV, delta, spread width, suitability) can't leak onto a beginner card.
// No fabrication: Maximum loss shows a real figure only when economics exist.

import type { PresentedOption, BiasTone } from './optionsPresent';

export interface BeginnerOption {
  timeLeft: string;     // "About 6 weeks left"
  endsOn: string | null;   // "Ends on Jul 18, 2026" — real expiry, else null
  entry: string | null;    // "You receive $35 now (a credit)." — real economics, else null
  maxGain: string | null;  // "Best case: $35" — real economics, else null
  riskLevel: string;    // honest, advanced-framed
  why: string;          // "Why this option setup exists"
  maxLoss: string;      // real economics, or honest "view full setup"
  whatFails: string;    // "What would make it fail"
}

function timeLeft(dte: number): string {
  if (!Number.isFinite(dte) || dte <= 0) return 'Expiring very soon';
  if (dte <= 10) return `About ${dte} day${dte === 1 ? '' : 's'} left`;
  const weeks = Math.round(dte / 7);
  return `About ${weeks} week${weeks === 1 ? '' : 's'} left`;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function endsOn(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return `Ends on ${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
}

// "Credit $35" / "Debit $40" from economics.premium → beginner phrasing.
// Real data only; null when no priced legs (never fabricated).
function entryLine(premium: string | null | undefined): string | null {
  if (!premium) return null;
  const m = premium.match(/(credit|debit)\s*(\$[\d.,]+)/i);
  if (!m) return null;
  const kind = m[1].toLowerCase();
  return kind === 'credit'
    ? `You receive ${m[2]} now (a credit).`
    : `You pay ${m[2]} now (a debit).`;
}

const WHY: Record<BiasTone, string> = {
  bull: 'Arth expects this stock to hold up or rise modestly before the option runs out.',
  bear: 'Arth expects this stock to stay weak or drift lower before the option runs out.',
  neutral: 'Arth expects this stock to stay in a range — this setup does best when it barely moves.',
  vol: 'Arth expects a big move in either direction — this setup does best when the stock swings hard.',
};

const FAILS: Record<BiasTone, string> = {
  bull: 'It loses if the stock drops sharply before the option runs out.',
  bear: 'It loses if the stock jumps sharply before the option runs out.',
  neutral: 'It loses if the stock makes a big move in either direction before the option runs out.',
  vol: 'It loses if the stock stays flat and the big move never arrives.',
};

export function beginnerOption(opt: PresentedOption): BeginnerOption {
  const econ = opt.economics;
  return {
    timeLeft: timeLeft(opt.dte),
    endsOn: endsOn(opt.expiry),
    entry: entryLine(econ?.premium),
    // Best case = the structure's max profit. Real economics only.
    maxGain: econ?.maxProfit ? `Best case: ${econ.maxProfit}.` : null,
    // Every v1 structure is a defined-risk setup, but options are still
    // advanced — frame the risk honestly without hiding the capped-loss fact.
    riskLevel: 'High (advanced) — but your loss is capped at the maximum below.',
    why: WHY[opt.tone] ?? WHY.neutral,
    maxLoss: econ?.maxRisk
      ? `${econ.maxRisk} — the most you can lose on this practice trade.`
      : 'Capped — exact figure is on the full setup page.',
    whatFails: FAILS[opt.tone] ?? FAILS.neutral,
  };
}
