// V2 Academy page — Phase D editorial rewrite.
//
// One academy. Lists the lessons in order with editorial structure
// matching LearnHome's new patterns: PageHeader brand-pill eyebrow,
// SurfaceCard rows, brand-aligned typography, beginner-first framing
// ("Why this academy" before "What's in it"), and a clear single
// next-step CTA derived from progress.
//
// Route: /v2/learn/{stocks|risk|options}

import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, Compass } from 'lucide-react';
import { ArthosPage } from '../chrome/ArthosChrome';
import { PageHeader } from '../components/ui/PageHeader';
import { Section } from '../components/ui/Section';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import { PATHS, getLessonsForPath } from '../data/arthosData';
import { useReadLessons } from '../lib/lesson-progress';

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

// Per-path "why this academy matters" copy. Beginner-first framing —
// the same micro-essay LearnHome surfaces, restated as the academy
// page header description. Authored once; both surfaces stay in sync.
const PATH_WHY: Record<string, string> = {
  'how-markets-actually-work':
    'The reframe everything else builds on. A stock is a slice of a business, not a number on a chart. By the end of this academy you can read a price the way an investor does.',
  'risk-literacy':
    'Most investing outcomes are decided by how much you size — not what you pick. Five lessons on drawdown, stops, and the math of staying in the game long enough to learn.',
  'options-literacy':
    'A precise set of tools for expressing views on direction, time, and volatility. Earned access — finish Risk literacy first.',
  'portfolio-psychology':
    'Why holding is the hardest action. Why we trim winners. What the mind does to a portfolio that the spreadsheet does not.',
  'reading-signals-like-an-analyst':
    'How a real signal looks, how a fake one looks, and how to tell the difference before the position is open.',
};

const PATH_ROUTE: Record<string, string> = {
  'how-markets-actually-work': 'stocks',
  'risk-literacy': 'risk',
  'options-literacy': 'options',
};

export function AcademyPage({ pathSlug }: { pathSlug: string }) {
  const path = PATHS.find((p) => p.slug === pathSlug);
  const lessons = getLessonsForPath(pathSlug);
  const readSlugs = useReadLessons();
  const readSet = new Set(readSlugs);
  const readInPath = lessons.filter((l) => readSet.has(l.slug)).length;
  const totalInPath = lessons.length;
  const pct = totalInPath === 0 ? 0 : (readInPath / totalInPath) * 100;
  const nextLesson = lessons.find((l) => !readSet.has(l.slug)) ?? lessons[0];
  const why = path ? PATH_WHY[path.slug] ?? path.synopsis : '';

  if (!path) {
    return (
      <ArthosPage
        maxWidth="max-w-screen-md lg:max-w-[1080px]"
        topBarEyebrow="Learn"
      >
        <FadeIn>
          <PageHeader eyebrow="Not found" title="No academy at this path." />
          <Link
            to="/v2/learn"
            className="inline-flex items-center gap-1.5"
            style={{ fontSize: 13, color: 'var(--brand)', fontWeight: 600 }}
          >
            Back to Learn <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        </FadeIn>
      </ArthosPage>
    );
  }

  return (
    <ArthosPage
      maxWidth="max-w-screen-md lg:max-w-[1080px]"
      topBarEyebrow="Learn"
    >
      <FadeIn>
        <Link
          to="/v2/learn"
          className="text-meta ink-fainter hover:ink-muted mb-6 inline-flex items-center gap-1.5 transition-colors"
        >
          <span aria-hidden>←</span> Learn
        </Link>
        <PageHeader
          eyebrow={path.tier}
          title={path.title}
          description={why}
          progress={Math.round(pct)}
        />
      </FadeIn>

      {nextLesson && (
        <Section className="mb-12 lg:mb-16">
          <FadeIn delay={0.08}>
            <SurfaceCard variant="highlight" className="p-7 lg:p-10">
              <span
                className="inline-flex items-center gap-2 font-bold uppercase mb-4"
                style={{
                  fontSize: 11,
                  letterSpacing: '0.16em',
                  color: 'var(--brand)',
                }}
              >
                <Compass className="size-3.5" aria-hidden />{' '}
                {readInPath === 0
                  ? 'Start here'
                  : 'Pick up where you left off'}
              </span>
              <p
                className="ink-muted leading-relaxed mb-3 max-w-narrative"
                style={{ fontSize: 14.5 }}
              >
                {nextLesson.abstract}
              </p>
              <h2
                className="font-display ink-primary leading-[1.1] mb-5 max-w-[22ch]"
                style={{ fontSize: 'clamp(26px, 3.5vw, 36px)' }}
              >
                {nextLesson.title}
              </h2>
              <div className="flex items-center gap-4 flex-wrap">
                <Link
                  to={`/v2/learn/lesson/${nextLesson.slug}`}
                  className="inline-flex items-center justify-center gap-2 h-11 px-5 rounded-full text-[13.5px] font-semibold tracking-tight transition-colors hover:opacity-92"
                  style={{
                    backgroundColor: 'var(--brand)',
                    color: 'var(--brand-foreground)',
                  }}
                >
                  {readInPath === 0
                    ? 'Read the first lesson'
                    : 'Continue reading'}{' '}
                  <ArrowRight className="size-3.5" aria-hidden />
                </Link>
                <span
                  className="font-mono tabular-nums"
                  style={{ fontSize: 12, color: 'var(--muted-foreground)' }}
                >
                  {nextLesson.readMinutes} min · Lesson {nextLesson.order} of{' '}
                  {totalInPath}
                </span>
              </div>
            </SurfaceCard>
          </FadeIn>
        </Section>
      )}

      <Section
        title="The path, in order"
        action={
          <span
            className="font-mono tabular-nums"
            style={{ fontSize: 12, color: 'var(--muted-foreground)' }}
          >
            {readInPath} of {totalInPath} read
          </span>
        }
        className="mb-12 lg:mb-20"
      >
        <SurfaceCard className="p-0 overflow-hidden">
          <ul>
            {lessons.map((lesson, i, arr) => {
              const isRead = readSet.has(lesson.slug);
              const isLast = i === arr.length - 1;
              return (
                <li
                  key={lesson.slug}
                  style={
                    !isLast
                      ? { borderBottom: '1px solid var(--border)' }
                      : undefined
                  }
                >
                  <Link
                    to={`/v2/learn/lesson/${lesson.slug}`}
                    className="block px-5 py-5 sm:px-7 sm:py-6 transition-colors"
                    style={{ backgroundColor: 'transparent' }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.backgroundColor =
                        'color-mix(in oklch, var(--sage-light) 50%, transparent)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.backgroundColor = 'transparent';
                    }}
                  >
                    <div className="flex items-start gap-4 sm:gap-6">
                      <span
                        className="font-mono tabular-nums shrink-0 mt-1"
                        style={{
                          fontSize: 13,
                          color: isRead
                            ? 'var(--brand)'
                            : 'var(--muted-foreground)',
                          width: 28,
                          textAlign: 'right',
                        }}
                        aria-hidden
                      >
                        {isRead ? '✓' : String(lesson.order).padStart(2, '0')}
                      </span>
                      <div className="min-w-0 flex-1">
                        <h3
                          className="font-display ink-primary leading-snug mb-1.5"
                          style={{ fontSize: 19 }}
                        >
                          {lesson.title}
                        </h3>
                        <p
                          className="ink-muted leading-relaxed max-w-narrative mb-2"
                          style={{ fontSize: 14 }}
                        >
                          {lesson.abstract}
                        </p>
                        <div
                          className="flex items-baseline gap-3 flex-wrap"
                          style={{
                            fontSize: 11,
                            color: 'var(--muted-foreground)',
                          }}
                        >
                          <span className="font-mono tabular-nums">
                            {lesson.readMinutes} min
                          </span>
                          {lesson.connectedSymbol && (
                            <>
                              <span aria-hidden>·</span>
                              <span>
                                Connects to{' '}
                                <span className="font-mono ink-muted">
                                  {lesson.connectedSymbol}
                                </span>
                              </span>
                            </>
                          )}
                          {isRead && (
                            <>
                              <span aria-hidden>·</span>
                              <span
                                className="font-bold uppercase"
                                style={{
                                  letterSpacing: '0.12em',
                                  color: 'var(--brand)',
                                }}
                              >
                                Read
                              </span>
                            </>
                          )}
                        </div>
                      </div>
                      <ArrowRight
                        className="size-4 shrink-0 mt-1.5"
                        style={{ color: 'var(--muted-foreground)' }}
                        aria-hidden
                      />
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        </SurfaceCard>
      </Section>

      <Section className="mb-12 lg:mb-20">
        <FadeIn delay={0.24}>
          <SurfaceCard variant="muted" className="p-7 lg:p-10">
            <span
              className="inline-block font-bold uppercase mb-4"
              style={{
                fontSize: 11,
                letterSpacing: '0.16em',
                color: 'var(--muted-foreground)',
              }}
            >
              Why this academy matters
            </span>
            <article className="prose-editorial max-w-copy">
              <p>{why}</p>
            </article>
            <Link
              to="/v2/methodology"
              className="inline-flex items-center gap-1.5 mt-5 transition-colors"
              style={{ fontSize: 13, color: 'var(--brand)', fontWeight: 600 }}
            >
              How ArthOS teaches{' '}
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          </SurfaceCard>
        </FadeIn>
      </Section>

      <Section title="Other academies" className="mb-12 lg:mb-16">
        <div className="grid sm:grid-cols-2 gap-5 lg:gap-6">
          {PATHS.filter(
            (p) => p.slug !== pathSlug && PATH_ROUTE[p.slug],
          ).map((p, i) => (
            <FadeIn key={p.slug} delay={0.3 + i * 0.04}>
              <Link
                to={`/v2/learn/${PATH_ROUTE[p.slug]}`}
                className="block h-full"
              >
                <SurfaceCard className="h-full transition-colors">
                  <span
                    className="font-bold uppercase mb-3 inline-block"
                    style={{
                      fontSize: 10,
                      letterSpacing: '0.16em',
                      color: 'var(--muted-foreground)',
                    }}
                  >
                    {p.tier}
                  </span>
                  <h3
                    className="font-display ink-primary leading-snug mb-2"
                    style={{ fontSize: 20 }}
                  >
                    {p.title}
                  </h3>
                  <p
                    className="ink-muted leading-relaxed max-w-narrative"
                    style={{ fontSize: 14 }}
                  >
                    {PATH_WHY[p.slug] ?? p.synopsis}
                  </p>
                  <div
                    className="inline-flex items-center gap-1.5 mt-4 transition-colors"
                    style={{
                      fontSize: 13,
                      color: 'var(--brand)',
                      fontWeight: 600,
                    }}
                  >
                    Open path <ArrowRight className="size-3.5" aria-hidden />
                  </div>
                </SurfaceCard>
              </Link>
            </FadeIn>
          ))}
        </div>
      </Section>

      <FadeIn delay={0.4}>
        <div
          className="mt-4 pt-8 flex flex-wrap items-center justify-between gap-3"
          style={{ borderTop: '1px solid var(--border)' }}
        >
          <Link
            to="/v2/methodology"
            className="inline-flex items-center gap-1.5 transition-colors"
            style={{ fontSize: 12, color: 'var(--muted-foreground)' }}
          >
            How ArthOS works →
          </Link>
          <p
            className="italic"
            style={{ fontSize: 11.5, color: 'var(--muted-foreground)' }}
          >
            Practice only · nothing real is at stake · not financial advice
          </p>
        </div>
      </FadeIn>
    </ArthosPage>
  );
}
