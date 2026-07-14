// ProgressSpine — the persistent journey indicator (Sprint E).
//
// Discover → Learn → Practice → Build → Automate → Invest.
// Lightweight + quiet: a single row of stages, current one highlighted, done
// ones ticked, future/locked ones muted. Progress is driven by REAL actions
// (a lesson read, a practice position, a diversified set) — NOT points,
// streaks, badges or any gamification.

import { useReadLessons } from '../lib/lesson-progress';

type StageState = 'done' | 'current' | 'todo' | 'locked';

interface Stage {
  key: string;
  label: string;
  state: StageState;
}

// Build = a diversified set of practice positions (proxy for "followed a
// portfolio / built a book"). Automate + Invest are not in the product yet.
const BUILD_THRESHOLD = 3;

function computeStages(paperCount: number, lessonsRead: number): Stage[] {
  const discoverDone = true;            // they're in the app
  const learnDone = lessonsRead > 0;
  const practiceDone = paperCount > 0;
  const buildDone = paperCount >= BUILD_THRESHOLD;

  const raw: { key: string; label: string; done: boolean; locked?: boolean }[] = [
    { key: 'discover', label: 'Discover', done: discoverDone },
    { key: 'learn', label: 'Learn', done: learnDone },
    { key: 'practice', label: 'Practice', done: practiceDone },
    { key: 'build', label: 'Build', done: buildDone },
    { key: 'automate', label: 'Automate', done: false, locked: true },
    { key: 'invest', label: 'Invest', done: false, locked: true },
  ];

  // First not-done, not-locked stage is the current focus.
  const currentIdx = raw.findIndex((s) => !s.done && !s.locked);
  return raw.map((s, i) => ({
    key: s.key,
    label: s.label,
    state: s.locked ? 'locked' : s.done ? 'done' : i === currentIdx ? 'current' : 'todo',
  }));
}

export function ProgressSpine({ paperCount }: { paperCount: number }) {
  const lessons = useReadLessons();
  const stages = computeStages(paperCount, lessons.length);

  return (
    <div className="mb-3" aria-label="Your investing journey">
      <p className="font-semibold uppercase mb-1.5" style={{
        fontSize: 9.5, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
      }}>Your journey</p>
      {/* No connectors — keeps all six stages on one line down to ~360px wide;
          overflow-x-auto is the safety net on very narrow screens. */}
      <div className="flex items-center gap-x-3 gap-y-1.5 flex-wrap overflow-x-auto">
        {stages.map((s) => (
          <div key={s.key} className="flex items-center gap-1.5 shrink-0">
            <Dot state={s.state} />
            <span style={{
              fontSize: 11.5,
              fontWeight: s.state === 'current' ? 700 : 500,
              color: s.state === 'current' ? 'var(--brand)'
                : s.state === 'done' ? 'var(--foreground)'
                : 'var(--muted-foreground)',
              opacity: s.state === 'locked' ? 0.55 : 1,
            }}>{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Dot({ state }: { state: StageState }) {
  const filled = state === 'done' || state === 'current';
  const color = state === 'current' ? 'var(--brand)'
    : state === 'done' ? 'var(--brand)'
    : 'var(--muted-foreground)';
  return (
    <span aria-hidden className="inline-flex items-center justify-center rounded-full"
      style={{
        width: state === 'current' ? 9 : 7,
        height: state === 'current' ? 9 : 7,
        backgroundColor: filled ? color : 'transparent',
        border: filled ? 'none' : `1px solid ${color}`,
        opacity: state === 'locked' ? 0.5 : 1,
      }} />
  );
}
