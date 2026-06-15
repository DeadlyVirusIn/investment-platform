// V2 Start Here — guided first-session flow.
//
// 4 steps. Each step has a destination route + a done-condition derived
// from existing localStorage state (no new tracking introduced). The
// novice has exactly one CTA per visit until all four are complete.
//
// Route: /v2/start
//
// Step done-conditions (drawn from already-stored data):
//   1 Read    — lib/lesson-progress.useReadLessons().length > 0
//   2 See     — lib/lesson-progress.useFollowedDecisions().length > 0
//   3 Reflect — lib/reflections.useReflections().length > 0
//   4 Try     — state/PaperBook.usePaperBook positions+history > 0

import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { useReadLessons, useFollowedDecisions } from '../lib/lesson-progress';
import { useReflections } from '../lib/reflections';
import { usePaperBook } from '../state/PaperBook';

interface StartStep {
  n: 1 | 2 | 3 | 4;
  kind: 'read' | 'see' | 'reflect' | 'try';
  title: string;
  blurb: string;
  estMinutes: number;
  to: string;
}

const STEPS: StartStep[] = [
  {
    n: 1,
    kind: 'read',
    title: 'What you actually own when you buy a stock',
    blurb:
      "The reframe everything else builds on. Six minutes; nothing is graded.",
    estMinutes: 6,
    to: '/v2/learn/lesson/what-is-a-stock',
  },
  {
    n: 2,
    kind: 'see',
    title: "See it in the wild — today's AI decision",
    blurb:
      "Read how the engine sized a real position. Open the working; the reasoning is in plain English.",
    estMinutes: 8,
    // P1.7B — link to today's Briefing (leads with the live top pick) rather
    // than a hardcoded symbol that dead-ends when the picks list drifts.
    to: '/v2/today',
  },
  {
    n: 3,
    kind: 'reflect',
    title: "What would have changed your mind?",
    blurb:
      "One honest answer at the bottom of the lesson. Stored on your device only, never sent.",
    estMinutes: 3,
    to: '/v2/learn/lesson/what-is-a-stock#reflect',
  },
  {
    n: 4,
    kind: 'try',
    title: "See how the AI portfolio is doing",
    blurb:
      "Your paper portfolio, marked daily. Watch a real decision play out — nothing real is at stake.",
    estMinutes: 10,
    to: '/v2/portfolio',
  },
];

function FadeIn({
  delay = 0,
  children,
  className,
}: {
  delay?: number;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay, ease: [0.32, 0.72, 0, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

function StepCard({
  step,
  state,
  delay,
}: {
  step: StartStep;
  state: 'done' | 'current' | 'upcoming';
  delay: number;
}) {
  const isUpcoming = state === 'upcoming';
  const isDone = state === 'done';
  return (
    <FadeIn delay={delay}>
      <Link
        to={step.to}
        className={
          'block surface-drawer p-5 sm:p-7 transition-opacity ' +
          (isUpcoming ? 'opacity-50 hover:opacity-70' : 'hover:opacity-90')
        }
      >
        <div className="flex items-center justify-between mb-3 gap-3">
          <div className="text-meta ink-fainter tabular-nums flex items-center gap-2">
            <span
              className="inline-flex items-center justify-center rounded-full"
              style={{
                width: 22,
                height: 22,
                fontSize: 11,
                backgroundColor: isDone
                  ? 'var(--ink-primary)'
                  : 'var(--surface-elevated)',
                color: isDone
                  ? 'var(--surface-base)'
                  : 'var(--ink-muted)',
                border: '1px solid var(--hairline)',
              }}
              aria-hidden
            >
              {isDone ? '✓' : step.n}
            </span>
            {step.kind === 'read'
              ? 'Read'
              : step.kind === 'see'
              ? 'See'
              : step.kind === 'reflect'
              ? 'Reflect'
              : 'Try'}
          </div>
          <div className="text-meta ink-fainter tabular-nums">
            {step.estMinutes} min
          </div>
        </div>
        <div className="font-serif ink-primary text-[20px] sm:text-[22px] leading-snug mb-2">
          {step.title}
        </div>
        <p className="ink-muted leading-relaxed text-[14px] sm:text-[15px] max-w-narrative">
          {step.blurb}
        </p>
      </Link>
    </FadeIn>
  );
}

export function StartHere() {
  const lessonsRead = useReadLessons();
  const reflections = useReflections();
  const follows = useFollowedDecisions();
  const paper = usePaperBook();

  const done = [
    lessonsRead.length > 0,
    follows.length > 0,
    reflections.length > 0,
    paper.positions.length + paper.history.length > 0,
  ];
  const doneCount = done.filter(Boolean).length;
  const allDone = doneCount === 4;
  const currentIdx = done.findIndex((d) => !d);

  return (
    <ArthosPage maxWidth="max-w-3xl">
      <FadeIn>
        <MetaLabel>Day 1</MetaLabel>
        <h1 className="font-serif ink-primary text-masthead leading-[1.05] mt-2 mb-5 max-w-[22ch]">
          {allDone ? "You've finished Day 1." : 'Start here.'}
        </h1>
        <p className="ink-muted leading-relaxed text-[17px] max-w-narrative mb-3">
          {allDone
            ? "Four steps complete. From tomorrow, Today's Briefing is your home; new lessons land daily."
            : "Today, you'll learn one idea, see one real decision, write one honest note, and watch one trade play out."}
        </p>
        {!allDone && (
          <p className="ink-fainter leading-relaxed text-[14px] mb-12 sm:mb-16">
            About 27 minutes total. Nothing is graded. You can stop at any
            step and come back later — your progress is saved on this device.
          </p>
        )}
      </FadeIn>

      <ul className="space-y-px bg-hairline">
        {STEPS.map((step, i) => (
          <li key={step.n}>
            <StepCard
              step={step}
              state={
                done[i]
                  ? 'done'
                  : i === currentIdx
                  ? 'current'
                  : 'upcoming'
              }
              delay={0.1 + i * 0.04}
            />
          </li>
        ))}
      </ul>

      <FadeIn delay={0.35}>
        <div className="mt-12 pt-8 border-t border-hairline">
          <div className="flex items-center justify-between gap-3 mb-3">
            <MetaLabel>Progress</MetaLabel>
            <div className="text-meta ink-fainter tabular-nums">
              {doneCount} of 4
            </div>
          </div>
          <div
            className="h-1.5 rounded-full overflow-hidden"
            style={{ backgroundColor: 'var(--sage-light)' }}
          >
            <div
              className="h-full transition-all duration-500"
              style={{
                width: `${(doneCount / 4) * 100}%`,
                backgroundColor: 'var(--brand)',
              }}
            />
          </div>
        </div>
      </FadeIn>

      <FadeIn delay={0.45}>
        <div className="mt-16 pt-10 border-t border-hairline flex flex-wrap gap-3">
          <Link
            to="/v2/learn"
            className="inline-flex items-center px-4 py-2 surface-drawer rounded-full text-meta ink-muted hover:ink-primary transition-colors"
          >
            I'd rather just browse
          </Link>
          <Link
            to="/v2/methodology"
            className="inline-flex items-center px-4 py-2 surface-drawer rounded-full text-meta ink-muted hover:ink-primary transition-colors"
          >
            How does ArthOS work?
          </Link>
        </div>
      </FadeIn>
    </ArthosPage>
  );
}
