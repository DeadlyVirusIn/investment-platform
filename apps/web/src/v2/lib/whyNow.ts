// "Why now?" deriver (investor-demo, Task 1).
//
// A single timeliness line per recommendation, built ONLY from data already
// on the idea page: the rec's own evidence (dominant current driver), its
// freshness (generated_at), and any recent news catalyst (useSymbolNews, also
// already fetched). No new data source, no earnings/analyst/breadth feeds —
// those are not populated today (see WHY_NOW_DATA_AUDIT for the backend gap).

import type { RecApi } from '@/lib/operator/hooks';
import type { SymbolNewsItem } from '@/lib/market/hooks';
import { bullBear } from './bullBear';

export interface WhyNow {
  label: string;
  line: string;
  catalyst: SymbolNewsItem | null;
}

export function whyNow(rec: RecApi, news?: SymbolNewsItem[] | null): WhyNow | null {
  const bb = bullBear(rec);
  const action = bb.action.toLowerCase();

  // Driver = the strongest CURRENT factor (bull side for buy/hold, bear side
  // when ArthOS is stepping back). Falls back to the other side, then null.
  const sell = action === 'sell' || action === 'trim';
  const driverPoint = sell ? (bb.bear[0] ?? bb.bull[0]) : (bb.bull[0] ?? bb.bear[0]);
  if (!driverPoint) return null;
  const d = driverPoint.phrase;
  const driver = d.charAt(0).toLowerCase() + d.slice(1);

  // Recency from generated_at (~last 36h counts as "today's read").
  const gen = rec.generated_at ? new Date(rec.generated_at).getTime() : NaN;
  const freshToday = Number.isFinite(gen) && Date.now() - gen < 36 * 3600 * 1000;
  const recency = freshToday ? "and it's still true on today's read" : 'on the latest read';

  // Most recent news catalyst within ~7 days (already fetched for the page).
  let catalyst: SymbolNewsItem | null = null;
  let newest = -Infinity;
  for (const n of news ?? []) {
    const t = new Date(n.published_at).getTime();
    if (Number.isFinite(t) && Date.now() - t < 7 * 86_400_000 && t > newest) {
      newest = t; catalyst = n;
    }
  }

  const label = sell ? 'Why ArthOS is stepping back now'
    : action === 'buy' ? 'Why the window looks open now'
    : 'Why it’s on the radar now';
  let line = `${driver.charAt(0).toUpperCase() + driver.slice(1)} ${recency}.`;
  if (catalyst) line += ' There’s also fresh news on the name (below).';

  return { label, line, catalyst };
}
