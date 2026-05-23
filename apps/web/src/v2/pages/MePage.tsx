// V2 Me — personal progress hub.
//
// Surfaces the localStorage signals that already exist but aren't shown
// back to the user anywhere: lessons read, reflections written, follows
// toggled, paper-book positions + history. Per-academy progress bars
// derived from arthosData.PATHS lessonSlugs vs useReadLessons().
//
// Route: /v2/me
//
// No new tracking, no new data sources.

import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import { PATHS, LESSONS, getLesson } from '../data/arthosData';
import { useReadLessons, useFollowedDecisions } from '../lib/lesson-progress';
import { useReflections } from '../lib/reflections';
import { usePaperBook } from '../state/PaperBook';

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

// Path slug → /v2/learn/<route> mapping. Only paths with a registered
// route are linked; others read as static rows. Mirrors AcademyPage.
const ACADEMY_ROUTE_BY_PATH: Record<string, string> = {
  'how-markets-actually-work': 'stocks',
  'risk-literacy': 'risk',
  'options-literacy': 'options',
};

function dayN(firstActivityIso: string | null): number {
  if (!firstActivityIso) return 1;
  const ms = Date.now() - new Date(firstActivityIso).getTime();
  if (!Number.isFinite(ms) || ms < 0) return 1;
  return Math.max(1, Math.floor(ms / 86_400_000) + 1);
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
}

export function MePage() {
  const lessonsRead = useReadLessons();
  const reflections = useReflections();
  const follows = useFollowedDecisions();
  const paper = usePaperBook();

  // Earliest timestamp across all signals = Day 1 anchor.
  const earliestIso = (() => {
    const candidates: string[] = [];
    // Reflections carry ISO timestamps.
    for (const r of reflections) candidates.push(r.createdAt);
    if (candidates.length === 0) return null;
    return candidates.sort()[0];
  })();
  const day = dayN(earliestIso);

  const totalLessons = LESSONS.length;
  const lessonsReadCount = lessonsRead.length;
  const reflectionCount = reflections.length;
  const followCount = follows.length;
  const openPositions = paper.positions.length;
  const closedTrades = paper.history.length;
  const realizedPnl = paper.realizedPnL;
  const unrealizedPnl = paper.unrealizedPnL;

  const latestReflection = reflections[0]; // already sorted desc

  // Per-path read counts.
  const pathProgress = PATHS.filter((p) => p.lessonSlugs.length > 0).map(
    (p) => {
      const total = p.lessonSlugs.length;
      const readHere = p.lessonSlugs.filter((s) =>
        lessonsRead.includes(s),
      ).length;
      return {
        slug: p.slug,
        title: p.title,
        total,
        read: readHere,
        route: ACADEMY_ROUTE_BY_PATH[p.slug],
      };
    },
  );

  return (
    <ArthosPage maxWidth="max-w-3xl">
      <FadeIn>
        <div className="flex items-start gap-5 mb-6">
          <div
            className="rounded-full flex items-center justify-center shrink-0"
            style={{
              width: 64,
              height: 64,
              backgroundColor:
                'color-mix(in oklch, var(--brand) 15%, transparent)',
              color: 'var(--brand)',
              fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
              fontStyle: 'italic',
              fontSize: 30,
              lineHeight: 1,
              paddingTop: 4,
            }}
            aria-hidden
          >
            U
          </div>
          <div className="min-w-0 flex-1">
            <span
              className="inline-block px-3.5 py-1.5 rounded-full text-[11px] font-bold uppercase tracking-[0.16em] mb-3"
              style={{
                backgroundColor:
                  'color-mix(in oklch, var(--brand) 14%, transparent)',
                color: 'var(--brand)',
              }}
            >
              Your ArthOS
            </span>
            <h1 className="font-display text-4xl sm:text-5xl ink-primary leading-[1.05] mb-2">
              Day {day}
            </h1>
            {earliestIso ? (
              <p className="ink-muted leading-relaxed text-[16px]">
                You started {fmtDate(earliestIso)}.
              </p>
            ) : (
              <p className="ink-muted leading-relaxed text-[16px] max-w-narrative">
                Nothing recorded yet. Open a lesson, write a reflection,
                or follow a decision and your activity will land here.
              </p>
            )}
          </div>
        </div>
        <div className="mb-12 sm:mb-16" />
      </FadeIn>

      <FadeIn delay={0.1}>
        <section className="mb-12 sm:mb-16">
          <MetaLabel>What you've done</MetaLabel>
          <SurfaceCard className="mt-4 p-0 overflow-hidden">
            <ul>
              {[
                { label: 'Lessons read', value: `${lessonsReadCount} of ${totalLessons}` },
                { label: 'Reflections written', value: `${reflectionCount}` },
                { label: 'Decisions followed', value: `${followCount}` },
                { label: 'Paper trades', value: `${openPositions} open · ${closedTrades} closed` },
              ].map((row, i, arr) => (
                <li
                  key={row.label}
                  className="px-5 py-4 sm:px-6 sm:py-5 flex items-baseline justify-between gap-4"
                  style={
                    i < arr.length - 1
                      ? { borderBottom: '1px solid var(--border)' }
                      : undefined
                  }
                >
                  <span className="ink-primary">{row.label}</span>
                  <span className="font-mono ink-muted tabular-nums">
                    {row.value}
                  </span>
                </li>
              ))}
            </ul>
          </SurfaceCard>
        </section>
      </FadeIn>

      {pathProgress.length > 0 && (
        <FadeIn delay={0.2}>
          <section className="mb-12 sm:mb-16">
            <MetaLabel>What you've learned</MetaLabel>
            <ul className="mt-4 space-y-4">
              {pathProgress.map((p) => {
                const pct = p.total === 0 ? 0 : (p.read / p.total) * 100;
                const linkable = !!p.route;
                const inner = (
                  <>
                    <div className="flex items-baseline justify-between mb-1.5">
                      <span className="ink-primary text-[15px]">
                        {p.title}
                      </span>
                      <span className="font-mono ink-fainter tabular-nums text-meta">
                        {p.read}/{p.total}
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
                  </>
                );
                return (
                  <li key={p.slug}>
                    {linkable ? (
                      <Link
                        to={`/v2/learn/${p.route}`}
                        className="block hover:opacity-90 transition-opacity"
                      >
                        {inner}
                      </Link>
                    ) : (
                      <div>{inner}</div>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        </FadeIn>
      )}

      {latestReflection && (
        <FadeIn delay={0.3}>
          <section className="mb-12 sm:mb-16">
            <MetaLabel>What you wrote</MetaLabel>
            <div className="mt-4 surface-drawer p-5 sm:p-6">
              <div className="text-meta ink-fainter mb-2">
                {fmtDate(latestReflection.createdAt)}
                {latestReflection.kind === 'lesson-capture' && latestReflection.targetId
                  ? ` · on ${getLesson(latestReflection.targetId)?.title ?? 'lesson'}`
                  : ''}
              </div>
              <blockquote className="font-serif italic ink-primary text-[15px] leading-relaxed max-w-narrative">
                "{latestReflection.body.length > 220
                  ? latestReflection.body.slice(0, 218) + '…'
                  : latestReflection.body}"
              </blockquote>
              {reflections.length > 1 && (
                <div className="mt-3 text-meta ink-fainter">
                  · {reflections.length - 1} more reflection
                  {reflections.length - 1 === 1 ? '' : 's'}
                </div>
              )}
            </div>
            <Link
              to="/v2/reflections"
              className="inline-flex items-center mt-4 text-meta ink-fainter hover:ink-muted transition-colors"
            >
              See all reflections →
            </Link>
          </section>
        </FadeIn>
      )}

      {/* UX Phase 3A — Learning loops. For each lesson the user has
          read, surface any paper trade opened from it (via
          originLessonSlug). Closes the read→reflect→try→track loop
          visibly on the personal hub. */}
      {(() => {
        const loopsByLesson = new Map<
          string,
          { positions: typeof paper.positions; history: typeof paper.history }
        >();
        const allLessonSlugs = new Set<string>(lessonsRead);
        for (const p of paper.positions) {
          if (p.originLessonSlug) allLessonSlugs.add(p.originLessonSlug);
        }
        for (const h of paper.history) {
          if (h.originLessonSlug) allLessonSlugs.add(h.originLessonSlug);
        }
        for (const slug of allLessonSlugs) {
          loopsByLesson.set(slug, {
            positions: paper.positions.filter(
              (p) => p.originLessonSlug === slug,
            ),
            history: paper.history.filter(
              (h) => h.originLessonSlug === slug,
            ),
          });
        }
        const loops = Array.from(loopsByLesson.entries())
          .map(([slug, data]) => ({ slug, lesson: getLesson(slug), ...data }))
          .filter((x) => x.lesson)
          .sort((a, b) =>
            (a.lesson?.title ?? '').localeCompare(b.lesson?.title ?? ''),
          );
        if (loops.length === 0) return null;
        return (
          <FadeIn delay={0.32}>
            <section className="mb-12 sm:mb-16">
              <MetaLabel>Your learning loops</MetaLabel>
              <ul className="mt-4 space-y-px bg-hairline">
                {loops.map((loop) => {
                  const reflected = reflections.some(
                    (r) =>
                      r.kind === 'lesson-capture' &&
                      r.targetId === loop.slug,
                  );
                  const tried =
                    loop.positions.length + loop.history.length > 0;
                  const reviewed = loop.history.length > 0;
                  return (
                    <li key={loop.slug}>
                      <Link
                        to={`/v2/try/${loop.slug}`}
                        className="block surface-drawer p-5 sm:p-6 hover:opacity-90 transition-opacity"
                      >
                        <div className="font-serif ink-primary text-[17px] leading-snug mb-2 max-w-narrative">
                          {loop.lesson!.title}
                        </div>
                        <div className="text-meta ink-fainter flex flex-wrap items-center gap-x-3 gap-y-1">
                          <span
                            style={{
                              color: 'var(--ink-muted)',
                            }}
                          >
                            ✓ Read
                          </span>
                          <span
                            style={{
                              color: reflected
                                ? 'var(--ink-muted)'
                                : 'var(--ink-fainter)',
                            }}
                          >
                            {reflected ? '✓' : '·'} Reflected
                          </span>
                          <span
                            style={{
                              color: tried
                                ? 'var(--ink-muted)'
                                : 'var(--ink-fainter)',
                            }}
                          >
                            {tried ? '✓' : '·'} Tried
                            {tried
                              ? ` (${loop.positions.length} open, ${loop.history.length} closed)`
                              : ''}
                          </span>
                          <span
                            style={{
                              color: reviewed
                                ? 'var(--ink-muted)'
                                : 'var(--ink-fainter)',
                            }}
                          >
                            {reviewed ? '✓' : '·'} Reviewed
                          </span>
                        </div>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </section>
          </FadeIn>
        );
      })()}

      {(openPositions > 0 || closedTrades > 0) && (
        <FadeIn delay={0.35}>
          <section className="mb-12 sm:mb-16">
            <MetaLabel>Your paper trades</MetaLabel>
            <div className="mt-4 surface-drawer p-5 sm:p-6 grid grid-cols-2 gap-4">
              <div>
                <div className="text-meta ink-fainter mb-1">Unrealized</div>
                <div className="font-mono ink-primary tabular-nums">
                  {unrealizedPnl >= 0 ? '+' : ''}
                  {unrealizedPnl.toFixed(2)}
                </div>
              </div>
              <div>
                <div className="text-meta ink-fainter mb-1">Realized</div>
                <div className="font-mono ink-primary tabular-nums">
                  {realizedPnl >= 0 ? '+' : ''}
                  {realizedPnl.toFixed(2)}
                </div>
              </div>
            </div>
            <Link
              to="/v2/portfolio"
              className="inline-flex items-center mt-4 px-4 py-2 surface-drawer rounded-full text-meta ink-muted hover:ink-primary transition-colors"
            >
              Open practice account →
            </Link>
          </section>
        </FadeIn>
      )}

      <FadeIn delay={0.45}>
        <div className="mt-16 pt-10 border-t border-hairline">
          <MetaLabel>Where to go next</MetaLabel>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link
              to="/v2/today"
              className="inline-flex items-center px-4 py-2 surface-drawer rounded-full text-meta ink-muted hover:ink-primary transition-colors"
            >
              Today's briefing
            </Link>
            <Link
              to="/v2/learn"
              className="inline-flex items-center px-4 py-2 surface-drawer rounded-full text-meta ink-muted hover:ink-primary transition-colors"
            >
              Browse lessons
            </Link>
            <Link
              to="/v2/methodology"
              className="inline-flex items-center px-4 py-2 surface-drawer rounded-full text-meta ink-muted hover:ink-primary transition-colors"
            >
              How ArthOS works
            </Link>
          </div>
        </div>
      </FadeIn>
    </ArthosPage>
  );
}
