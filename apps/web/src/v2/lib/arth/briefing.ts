// Arth daily briefing — composes today's hero + opening line.
// Deterministic per local-date.

import { TODAYS_DESK, type Recommendation } from '../../data/arthosData';

export interface DailyBriefing {
  date: string;
  arth_opening: string;
  hero?: Recommendation;
  also_watch: Recommendation[];
  generated_at: string;
}

export function generateBriefing(opts: {
  todayKey: string;
  streakDay: number;
  yesterdayDecision?: { action: string; symbol: string };
}): DailyBriefing {
  const all = [...TODAYS_DESK.stocks, ...TODAYS_DESK.options].filter(
    (r) => r.placeable,
  );
  // Stable order: by symbol so the same hero appears all day.
  const sorted = [...all].sort((a, b) => a.symbol.localeCompare(b.symbol));
  const hero = sorted[0];
  const also_watch = sorted.slice(1, 4);

  const opening = composeOpening(opts.streakDay, opts.yesterdayDecision, hero);

  return {
    date: opts.todayKey,
    arth_opening: opening,
    hero,
    also_watch,
    generated_at: new Date().toISOString(),
  };
}

function composeOpening(
  day: number,
  yesterday: { action: string; symbol: string } | undefined,
  hero: Recommendation | undefined,
): string {
  if (day <= 1) {
    return "I'm new to you. I picked something on the conservative side today on purpose — let me see how you react before I push harder.";
  }
  if (yesterday?.action === 'skipped') {
    return `Yesterday I flagged ${yesterday.symbol}. You skipped. Fair. Here's what I think looks cleanest today.`;
  }
  if (yesterday?.action === 'followed' || yesterday?.action === 'paper_traded') {
    return `Yesterday you took the ${yesterday.symbol} call. I'm watching that for you. Here's what I see today.`;
  }
  if (!hero) {
    return "Nothing clean on the desk today. I'd rather show you nothing than make something up. Read a lesson instead.";
  }
  return `Day ${day}. One setup looks meaningfully cleaner than the others — that's where I'd start.`;
}
