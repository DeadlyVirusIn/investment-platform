// Truthful freshness presentation — ONE shared mapping so every surface
// (Discover cards, LiveTodayHero, PickPage header) agrees with the visible
// as-of timestamp. Elite WebUI audit C1: "updated today" was previously
// shown for anything ≤30h old, contradicting the as-of line beside it.

export type FreshnessTone = 'good' | 'warn';

export type FreshnessInfo = {
  /** Truthful relative label, e.g. "Updated today" / "Updated yesterday". */
  label: string;
  tone: FreshnessTone;
  /** Whole local-calendar days since generation (0 = today), null if unknown. */
  ageDays: number | null;
};

function calendarDaysAgo(iso: string): number | null {
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return null;
  const now = new Date();
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  return Math.max(0, Math.round((startOf(now) - startOf(t)) / 86_400_000));
}

/** Map a generated-at timestamp (+ backend stale flag) to an honest label.
 *  Tone turns to 'warn' when the backend flags staleness or the idea is
 *  more than one calendar day old. Unknown timestamps are never claimed
 *  fresh. */
export function freshnessInfo(
  generatedAt: string | null | undefined,
  stale?: boolean | null,
): FreshnessInfo {
  if (!generatedAt) {
    return { label: 'Timing unavailable', tone: 'warn', ageDays: null };
  }
  const days = calendarDaysAgo(generatedAt);
  if (days == null) {
    return { label: 'Timing unavailable', tone: 'warn', ageDays: null };
  }
  const label =
    days === 0 ? 'Updated today'
      : days === 1 ? 'Updated yesterday'
        : `Updated ${days} days ago`;
  const tone: FreshnessTone = stale || days > 1 ? 'warn' : 'good';
  return { label, tone, ageDays: days };
}
