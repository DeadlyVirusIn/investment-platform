// MVP Phase A — Salutation.
//
// Two-line block at the top of Today.
//   Line 1 (eyebrow): "DAY N OF READING · GOOD MORNING."   OR   "WELCOME."
//   Line 2 (headline): "Good morning." / "Good afternoon." / etc.
//   Line 3 (optional, long-gap only): "It's been N days."
//
// Three rules. No streak language. No anxiety mechanics.

import { useUserPrefs } from '../state/UserPrefsContext';

function dateOnly(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function daysBetween(aIso: string, bIso: string): number {
  const a = new Date(aIso + 'T00:00:00Z').getTime();
  const b = new Date(bIso + 'T00:00:00Z').getTime();
  return Math.round((b - a) / (1000 * 60 * 60 * 24));
}

function timeOfDayGreeting(): string {
  const h = new Date().getHours();
  if (h < 5) return 'Late evening';
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  if (h < 21) return 'Good evening';
  return 'Late evening';
}

export function Salutation() {
  const { firstVisitedDate, previousVisitDate } = useUserPrefs();
  const today = dateOnly(new Date());
  const greeting = timeOfDayGreeting();

  // Rule 1 — first visit (no firstVisitedDate yet, or it equals today
  // before the provider's mount-effect persists). Treat as "Welcome."
  const isFirstVisit = !firstVisitedDate || firstVisitedDate === today;

  // Rule 2 — long gap (>= 7 days since previous visit).
  const gapDays =
    previousVisitDate && previousVisitDate !== today
      ? daysBetween(previousVisitDate, today)
      : 0;
  const isLongGap = gapDays >= 7;

  // Rule 3 — standard (default): "Day N of reading. Good morning."
  const dayN =
    firstVisitedDate && firstVisitedDate !== today
      ? daysBetween(firstVisitedDate, today) + 1
      : 1;

  let eyebrow: string;
  let context: string | null = null;

  if (isFirstVisit) {
    eyebrow = 'Welcome';
  } else if (isLongGap) {
    eyebrow = `Day ${dayN} of reading · ${greeting}`;
    context = `It's been ${gapDays} days.`;
  } else {
    eyebrow = `Day ${dayN} of reading · ${greeting}`;
  }

  return (
    <section className="mb-10 max-w-narrative" aria-label="Salutation">
      <div
        className="ink-muted mb-3"
        style={{
          fontSize: '12px',
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          fontWeight: 500,
        }}
      >
        {eyebrow}
      </div>
      <h2 className="font-serif text-headline ink-primary leading-[1.05] mb-2">
        {isFirstVisit ? 'Welcome.' : `${greeting}.`}
      </h2>
      {context && (
        <p className="ink-muted text-[15px] leading-relaxed">{context}</p>
      )}
    </section>
  );
}
