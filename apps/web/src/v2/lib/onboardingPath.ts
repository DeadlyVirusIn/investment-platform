// useOnboardingPath — the single "what next?" for a beginner, driving the
// Continue-Your-Path card on Discover (P1 activation).
//
// Reuses the SAME Day-1 done-conditions as StartHere (localStorage: lessons
// read / decisions followed / reflections written / has a practice position).
// While Day 1 is incomplete → resume the current step. Once complete → advance
// by practice-position count (progression logic).

import { useReadLessons, useFollowedDecisions } from './lesson-progress';
import { useReflections } from './reflections';

export interface PathAction {
  title: string;
  blurb: string;
  to: string;
  /** Day-1 progress when resuming; null once the path moves to next-action. */
  progress: { done: number; total: number } | null;
}

// Resume targets per Day-1 step (mirror of StartHere's STEPS order).
const RESUME: { to: string; title: string }[] = [
  { to: '/learn/lesson/what-is-a-stock', title: 'Read: what you actually own when you buy a stock' },
  { to: '/today', title: "See today's AI decision in the wild" },
  { to: '/learn/lesson/what-is-a-stock#reflect', title: 'Reflect: what would change your mind?' },
  { to: '/portfolio', title: 'See how your practice portfolio is doing' },
];

export function useOnboardingPath(paperCount: number): PathAction {
  const lessons = useReadLessons();
  const follows = useFollowedDecisions();
  const reflections = useReflections();

  // Progression by practice activity takes priority once the user is actually
  // practising — a beginner who has added positions should be nudged forward,
  // not sent back into Day-1 reading.
  if (paperCount === 1) {
    return {
      title: 'Add a second idea',
      blurb: 'One more practice position helps you compare and learn.',
      to: '/discover',
      progress: null,
    };
  }
  if (paperCount >= 2) {
    return {
      title: 'Review your practice portfolio',
      blurb: 'See how your practice ideas are holding up.',
      to: '/portfolio',
      progress: null,
    };
  }

  // paperCount === 0 — resume the guided Day-1 path where the user left off.
  const done = [
    lessons.length > 0,
    follows.length > 0,
    reflections.length > 0,
    false, // "try" step (a practice position) — false here since paperCount===0
  ];
  const doneCount = done.filter(Boolean).length;
  const currentIdx = done.findIndex((d) => !d);

  if (currentIdx !== -1 && currentIdx < 3) {
    const step = RESUME[currentIdx];
    return {
      title: 'Continue your path',
      blurb: step.title,
      to: step.to,
      progress: { done: doneCount, total: 4 },
    };
  }

  // Day-1 reading done but no practice position yet.
  return {
    title: 'Add your first idea',
    blurb: 'Pick a stock idea and add it to your practice account.',
    to: '/today',
    progress: null,
  };
}
