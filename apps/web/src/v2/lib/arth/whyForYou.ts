// Arth "why for you" resolver — deterministic rules over declared
// memory + user prefs + recommendation context.

import type { Recommendation } from '../../data/arthosData';
import type { MemoryNote } from './memory';

export interface WhyForYou {
  line: string;
  cited_memory_ids: string[];
  fallback: boolean;
}

interface Context {
  rec: Recommendation;
  watchlist: string[];
  topics: string[];                   // declared interest topics
  level?: 'beginner' | 'building' | 'experienced';
  memory: MemoryNote[];
}

export function resolveWhyForYou(ctx: Context): WhyForYou {
  const cited: string[] = [];
  const reasons: string[] = [];

  // Rule 1: ticker on watchlist
  if (ctx.watchlist.includes(ctx.rec.symbol)) {
    reasons.push(`${ctx.rec.symbol} is on your watchlist — you asked me to keep an eye on it`);
    const note = ctx.memory.find(
      (m) => m.category === 'told_me' && m.text.includes('watchlist'),
    );
    if (note) cited.push(note.id);
  }

  // Rule 2: kind matches declared comfort
  if (ctx.rec.kind === 'option' && ctx.level === 'beginner') {
    reasons.push(`this is an option setup — and you told me you're new to options, so the structure is defined-risk and the max loss is known up front`);
  }

  // Rule 3: kind matches experienced
  if (ctx.rec.kind === 'option' && ctx.level === 'experienced') {
    reasons.push(`you marked yourself as experienced — this is a structured options play with edge from IV mispricing`);
  }

  // Rule 4: declared horizon match
  const horizonNote = ctx.memory.find(
    (m) => m.category === 'told_me' && /horizon/i.test(m.text),
  );
  if (horizonNote) {
    cited.push(horizonNote.id);
    reasons.push(`the time-to-catalyst fits the horizon you described`);
  }

  // Rule 5: topic match
  const symbolTopicHint =
    ctx.rec.symbol === 'NVDA' || ctx.rec.symbol === 'AMD' ? 'semis' :
    ctx.rec.symbol === 'XLE' ? 'energy' :
    ctx.rec.symbol === 'AAPL' || ctx.rec.symbol === 'TSLA' ? 'mega-cap tech' :
    null;
  if (symbolTopicHint && ctx.topics.some((t) => t.toLowerCase().includes(symbolTopicHint.split(' ')[0]))) {
    reasons.push(`you marked ${symbolTopicHint} as an interest`);
  }

  if (reasons.length === 0) {
    return {
      line: "I picked this for you because the setup itself is unusually clean today — there isn't anything you told me yet that points here directly. As I learn what you like, I'll tailor more.",
      cited_memory_ids: [],
      fallback: true,
    };
  }

  // Compose the first 2 reasons into one sentence.
  const top = reasons.slice(0, 2).join('; and ');
  return {
    line: `I picked this for you because ${top}.`,
    cited_memory_ids: cited,
    fallback: false,
  };
}
