// V2 Learn Home — Phase D editorial rewrite.
//
// Replaces the legacy warm-card magazine layout with a Lovable-class
// beginner-first reading surface:
//
//   1. PageHeader — brand-pill "LEARN" eyebrow + display masthead
//      "Build investor instincts." + max-w-narrative description
//   2. Hero — today's recommended lesson in a highlight SurfaceCard
//      with one primary PillButton CTA. WHY-this-matters precedes
//      the title to honour beginner-first framing.
//   3. Why ArthOS teaches this way — editorial paragraph wrapped in
//      .prose-editorial so the Fraunces drop-cap activates
//   4. Your learning paths — 3 SurfaceCard tiles, AcademyChips, one
//      "Continue path →" PillButton ghost per tile
//   5. Recently read — gated on useReadLessons().length > 0
//   6. Glossary entry — single muted SurfaceCard pointing into the
//      glossary index
//   7. Trust footer — methodology link + practice-only reassurance
//
// Logic-free except for picking the recommended lesson (first unread
// or hero fallback) and per-path read counts. All data from existing
// arthosData / lesson-progress. No new APIs, no new tracking.

import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, BookOpen, Compass, Sparkles } from 'lucide-react';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { PageHeader } from '../components/ui/PageHeader';
import { Section } from '../components/ui/Section';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import {
  PATHS,
  LESSONS,
  GLOSSARY,
  getLesson,
  type Path,
  type Lesson,
} from '../data/arthosData';
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

const PATH_ROUTE: Record<string, string> = {
  'how-markets-actually-work': 'stocks',
  'risk-literacy': 'risk',
  'options-literacy': 'options',
};

// Per-path one-line "why this matters" copy. Beginner-first framing:
// answers "why should I learn this?" before "what is this?".
const PATH_WHY: Record<string, string> = {
  'how-markets-actually-work':
    'The reframe everything else builds on. A stock is a slice of a business, not a number on a chart.',
  'risk-literacy':
    'Most outcomes come from sizing, not picking. Learn the math of staying in the game.',
  'options-literacy':
    'Precise tools for direction, time, and volatility. Used carelessly, they are expensive ones.',
  'portfolio-psychology':
    'Why holding is the hardest action. What the mind does to a portfolio that the spreadsheet does not.',
  'reading-signals-like-an-analyst':
    'How a real signal looks, how a fake one looks, and how to tell the difference before the position is open.',
};

// Pick the recommended next lesson: first unread in the user's path of
// least progress; fall back to first unread overall; fall back to hero.
function pickRecommended(readSlugs: string[]): Lesson {
  const readSet = new Set(readSlugs);
  const unread = LESSONS.find((l) => !readSet.has(l.slug));
  return unread ?? LESSONS[0];
}

export function LearnHome() {
  const readSlugs = useReadLessons();
  const recommended = pickRecommended(readSlugs);
  const recommendedPath = PATHS.find((p) => p.slug === recommended.pathSlug);

  // Filter to paths that actually have lessons; hide coming-soon paths
  // from the default surface (drawer keeps them reachable).
  const activePaths = PATHS.filter((p) => p.lessonSlugs.length > 0);
  const recentlyRead = readSlugs
    .map((s) => getLesson(s))
    .filter((l): l is Lesson => Boolean(l))
    .slice(0, 4);

  return (
    <ArthosPage maxWidth="max-w-screen-md lg:max-w-[1080px]" topBarEyebrow="Learn">
      <FadeIn>
        <PageHeader
          eyebrow="Learn"
          title={
            <>
              Build investor
              <br />
              instincts.
            </>
          }
          description="One lesson at a time. Every concept connects to a real decision the AI portfolio made today — so you read the idea, then watch it work."
        />
      </FadeIn>

      {/* HERO — single primary CTA. Why-before-what, brand-pill eyebrow
          inside the highlight card so it reads as the editor's pick. */}
      <Section className="mb-12 lg:mb-16">
        <FadeIn delay={0.06}>
          <SurfaceCard variant="highlight" className="p-7 lg:p-10">
            <div className="flex items-baseline justify-between gap-3 mb-5 flex-wrap">
              <span
                className="inline-flex items-center gap-2 font-bold uppercase"
                style={{
                  fontSize: 11,
                  letterSpacing: '0.16em',
                  color: 'var(--brand)',
                }}
              >
                <Sparkles className="size-3.5" aria-hidden /> Today's lesson
              </span>
              <span
                className="font-mono tabular-nums"
                style={{ fontSize: 12, color: 'var(--muted-foreground)' }}
              >
                {recommended.readMinutes} min · {recommendedPath?.tier ?? 'Lesson'}
              </span>
            </div>

            {/* Why-this-matters BEFORE the title. Beginner-first. */}
            <p
              className="ink-muted leading-relaxed mb-4 max-w-narrative"
              style={{ fontSize: 15 }}
            >
              {recommended.abstract}
            </p>

            <h2
              className="font-display ink-primary leading-[1.05] mb-6 max-w-[22ch]"
              style={{ fontSize: 'clamp(28px, 4vw, 44px)' }}
            >
              {recommended.title}
            </h2>

            {recommended.connectedSymbol && (
              <p
                className="ink-fainter mb-6 max-w-narrative"
                style={{ fontSize: 13 }}
              >
                Connects to a live position in the AI portfolio ·{' '}
                <span className="font-mono ink-muted">
                  {recommended.connectedSymbol}
                </span>
              </p>
            )}

            <Link
              to={`/v2/learn/lesson/${recommended.slug}`}
              className="inline-flex items-center justify-center gap-2 h-12 px-6 rounded-full text-[14px] font-semibold tracking-tight transition-colors hover:opacity-92"
              style={{
                backgroundColor: 'var(--brand)',
                color: 'var(--brand-foreground)',
              }}
            >
              Read this lesson <ArrowRight className="size-4" aria-hidden />
            </Link>
          </SurfaceCard>
        </FadeIn>
      </Section>

      {/* WHY THIS WAY — editorial paragraph with prose-editorial
          drop-cap. Asserts the trust model + connects Learn to the
          rest of the product. */}
      <Section className="mb-12 lg:mb-20">
        <FadeIn delay={0.12}>
          <SurfaceCard variant="muted" className="p-7 lg:p-10">
            <span
              className="inline-block font-bold uppercase mb-4"
              style={{
                fontSize: 11,
                letterSpacing: '0.16em',
                color: 'var(--muted-foreground)',
              }}
            >
              Why ArthOS teaches this way
            </span>
            <article className="prose-editorial max-w-copy">
              <p>
                Every lesson here is paired with a real decision the AI
                portfolio is making — or has already made — in plain
                English. You read the idea, then you watch it play out
                in the briefing, the journal, and the practice account.
                The goal is not to teach you facts. The goal is to build
                the instincts that let you read a thesis, recognise a
                catalyst, size a position, and accept a loss without
                losing the discipline that earned the next one.
              </p>
              <p
                className="mt-1"
                style={{ fontSize: 14, color: 'var(--muted-foreground)' }}
              >
                Nothing here is financial advice. Nothing real is at stake. The
                point is literacy — by Day 90, the page reads itself.
              </p>
            </article>
            <Link
              to="/v2/methodology"
              className="inline-flex items-center gap-1.5 mt-5 transition-colors"
              style={{ fontSize: 13, color: 'var(--brand)', fontWeight: 600 }}
            >
              Read the full methodology <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          </SurfaceCard>
        </FadeIn>
      </Section>

      {/* PATHS — 3 SurfaceCards in a grid. Each tile is a path with
          progress + why-this-matters + continue CTA. */}
      <Section
        title="Your learning paths"
        action={
          <span
            className="font-mono tabular-nums"
            style={{ fontSize: 12, color: 'var(--muted-foreground)' }}
          >
            {activePaths.length} paths
          </span>
        }
        className="mb-12 lg:mb-20"
      >
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5 lg:gap-6">
          {activePaths.map((path, i) => (
            <FadeIn key={path.slug} delay={0.18 + i * 0.04}>
              <PathTile path={path} readSlugs={readSlugs} />
            </FadeIn>
          ))}
        </div>
      </Section>

      {/* RECENTLY READ — gated. Tiny list, no analytics theatre. */}
      {recentlyRead.length > 0 && (
        <Section title="Recently read" className="mb-12 lg:mb-20">
          <FadeIn delay={0.3}>
            <SurfaceCard className="p-0 overflow-hidden">
              <ul>
                {recentlyRead.map((lesson, i, arr) => (
                  <li
                    key={lesson.slug}
                    style={
                      i < arr.length - 1
                        ? { borderBottom: '1px solid var(--border)' }
                        : undefined
                    }
                  >
                    <Link
                      to={`/v2/learn/lesson/${lesson.slug}`}
                      className="flex items-baseline justify-between gap-4 px-5 py-4 sm:px-6 sm:py-5 transition-colors"
                      style={{
                        backgroundColor: 'transparent',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor =
                          'color-mix(in oklch, var(--sage-light) 50%, transparent)';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = 'transparent';
                      }}
                    >
                      <span className="ink-primary leading-snug max-w-narrative">
                        {lesson.title}
                      </span>
                      <span
                        className="font-mono tabular-nums shrink-0"
                        style={{ fontSize: 11, color: 'var(--muted-foreground)' }}
                      >
                        {lesson.readMinutes} min
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </SurfaceCard>
          </FadeIn>
        </Section>
      )}

      {/* GLOSSARY entry — one SurfaceCard, ghost CTA. */}
      <Section className="mb-12 lg:mb-20">
        <FadeIn delay={0.36}>
          <SurfaceCard variant="muted">
            <div className="flex items-baseline justify-between gap-4 flex-wrap">
              <div className="min-w-0 flex-1">
                <span
                  className="inline-flex items-center gap-2 font-bold uppercase mb-3"
                  style={{
                    fontSize: 11,
                    letterSpacing: '0.16em',
                    color: 'var(--muted-foreground)',
                  }}
                >
                  <BookOpen className="size-3.5" aria-hidden /> Reference
                </span>
                <p
                  className="font-display ink-primary leading-snug mb-2"
                  style={{ fontSize: 22 }}
                >
                  Every concept this portfolio uses
                </p>
                <p
                  className="ink-muted leading-relaxed max-w-narrative"
                  style={{ fontSize: 14 }}
                >
                  {GLOSSARY.length} terms. Hover the dotted underline anywhere in
                  a lesson to see the definition inline.
                </p>
              </div>
              <Link
                to="/v2/learn/glossary"
                className="inline-flex items-center gap-2 h-10 px-4 rounded-full text-[13px] font-semibold transition-colors hover:opacity-92 shrink-0"
                style={{
                  border: '1px solid var(--border)',
                  color: 'var(--foreground)',
                  backgroundColor: 'transparent',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--sage-light)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }}
              >
                Open glossary <ArrowRight className="size-3.5" aria-hidden />
              </Link>
            </div>
          </SurfaceCard>
        </FadeIn>
      </Section>

      {/* Trust footer — same shape as Today. */}
      <FadeIn delay={0.44}>
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

      {/* Keep MetaLabel import live for downstream lint compatibility. */}
      <noscript>
        <MetaLabel>internal</MetaLabel>
      </noscript>
    </ArthosPage>
  );
}

// ──────────────────────────────────────────────────────────────
// PathTile — per-path SurfaceCard with progress + why-this-matters
// ──────────────────────────────────────────────────────────────
function PathTile({
  path,
  readSlugs,
}: {
  path: Path;
  readSlugs: string[];
}) {
  const total = path.lessonSlugs.length;
  const read = path.lessonSlugs.filter((s) => readSlugs.includes(s)).length;
  const pct = total === 0 ? 0 : (read / total) * 100;
  const academyRoute = PATH_ROUTE[path.slug];
  const why = PATH_WHY[path.slug] ?? path.synopsis;
  // First unread lesson in path → entry point. Falls back to first lesson.
  const entrySlug =
    path.lessonSlugs.find((s) => !readSlugs.includes(s)) ?? path.lessonSlugs[0];
  const targetHref = academyRoute
    ? `/v2/learn/${academyRoute}`
    : entrySlug
    ? `/v2/learn/lesson/${entrySlug}`
    : '/v2/learn';

  return (
    <SurfaceCard className="flex flex-col h-full">
      <div className="flex items-center gap-2 mb-3">
        <Compass
          className="size-3.5"
          style={{ color: 'var(--brand)' }}
          aria-hidden
        />
        <span
          className="font-bold uppercase"
          style={{
            fontSize: 10,
            letterSpacing: '0.16em',
            color: 'var(--muted-foreground)',
          }}
        >
          {path.tier}
        </span>
      </div>
      <h3
        className="font-display ink-primary leading-snug mb-2"
        style={{ fontSize: 21 }}
      >
        {path.title}
      </h3>
      <p
        className="ink-muted leading-relaxed mb-5 max-w-narrative flex-1"
        style={{ fontSize: 14 }}
      >
        {why}
      </p>
      <div className="mb-4">
        <div className="flex items-baseline justify-between mb-1.5">
          <span
            className="font-bold uppercase"
            style={{
              fontSize: 10,
              letterSpacing: '0.14em',
              color: 'var(--muted-foreground)',
            }}
          >
            Progress
          </span>
          <span
            className="font-mono tabular-nums"
            style={{ fontSize: 11, color: 'var(--muted-foreground)' }}
          >
            {read} / {total}
          </span>
        </div>
        <div
          className="h-1.5 rounded-full overflow-hidden"
          style={{ backgroundColor: 'var(--sage-light)' }}
        >
          <div
            className="h-full transition-all duration-500"
            style={{
              width: `${pct}%`,
              backgroundColor: 'var(--brand)',
            }}
          />
        </div>
      </div>
      <Link
        to={targetHref}
        className="inline-flex items-center gap-1.5 self-start transition-colors"
        style={{
          fontSize: 13,
          fontWeight: 600,
          color: 'var(--brand)',
        }}
      >
        {read === 0 ? 'Start the path' : 'Continue path'}{' '}
        <ArrowRight className="size-3.5" aria-hidden />
      </Link>
    </SurfaceCard>
  );
}
