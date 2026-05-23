// V2 Academy page — surface lessons grouped by V2 PATH.
//
// One file, parameterized by pathSlug. Used for the three academy
// routes added in Phase 4:
//   /v2/learn/stocks      → pathSlug='how-markets-actually-work'
//   /v2/learn/risk        → pathSlug='risk-literacy'
//   /v2/learn/options     → pathSlug='options-literacy'
//
// Uses existing ArthosPage chrome + MetaLabel typography helpers.
// Lessons render as a vertical editorial list; each card shows
// order, title, abstract, read-minutes, and read-receipt state.

import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { PATHS, getLessonsForPath } from '../data/arthosData';
import { useLessonRead } from '../lib/lesson-progress';

// Path slug → /v2/learn/<route> mapping. Only paths listed here have a
// registered route in V2App.tsx; the "Continue exploring" footer
// filters against this map so users never land on a 404. Add a path
// here when its academy route ships.
const ACADEMY_ROUTE_BY_PATH: Record<string, string> = {
  'how-markets-actually-work': 'stocks',
  'risk-literacy': 'risk',
  'options-literacy': 'options',
};

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

function LessonRow({
  slug,
  order,
  title,
  abstract,
  readMinutes,
  delay,
}: {
  slug: string;
  order: number;
  title: string;
  abstract: string;
  readMinutes: number;
  delay: number;
}) {
  const isRead = useLessonRead(slug);
  return (
    <FadeIn delay={delay}>
      <Link
        to={`/v2/learn/lesson/${slug}`}
        className="block surface-drawer p-6 sm:p-8 hover:opacity-90 transition-opacity"
      >
        <div className="flex items-baseline justify-between gap-4 mb-2">
          <div className="text-meta ink-fainter tabular-nums">
            Lesson {String(order).padStart(2, '0')}
          </div>
          <div className="text-meta ink-fainter tabular-nums">
            {readMinutes} min{isRead ? ' · read' : ''}
          </div>
        </div>
        <div className="font-serif ink-primary text-[22px] sm:text-[24px] leading-snug mb-2">
          {title}
        </div>
        <p className="ink-muted leading-relaxed text-[15px] max-w-narrative">
          {abstract}
        </p>
      </Link>
    </FadeIn>
  );
}

export function AcademyPage({ pathSlug }: { pathSlug: string }) {
  const path = PATHS.find((p) => p.slug === pathSlug);
  const lessons = getLessonsForPath(pathSlug);

  if (!path) {
    return (
      <ArthosPage>
        <FadeIn>
          <div className="text-meta ink-fainter mb-4">Not found</div>
          <h1 className="font-serif ink-primary text-headline leading-tight mb-6">
            No academy at this path.
          </h1>
          <Link to="/v2/learn" className="ink-muted underline">
            Back to Learn
          </Link>
        </FadeIn>
      </ArthosPage>
    );
  }

  return (
    <ArthosPage maxWidth="max-w-4xl">
      <FadeIn>
        <MetaLabel>{path.tier}</MetaLabel>
        <h1 className="font-serif ink-primary text-masthead leading-[1.05] mt-2 mb-5 max-w-[22ch]">
          {path.title}
        </h1>
        <p className="ink-muted leading-relaxed text-[17px] max-w-narrative mb-12 sm:mb-16">
          {path.synopsis}
        </p>
      </FadeIn>

      {lessons.length === 0 ? (
        <FadeIn delay={0.1}>
          <p className="ink-fainter italic max-w-narrative">
            No lessons published yet in this path.
          </p>
        </FadeIn>
      ) : (
        <ul className="space-y-px bg-hairline">
          {lessons.map((lesson, i) => (
            <li key={lesson.slug}>
              <LessonRow
                slug={lesson.slug}
                order={lesson.order}
                title={lesson.title}
                abstract={lesson.abstract}
                readMinutes={lesson.readMinutes}
                delay={0.1 + i * 0.04}
              />
            </li>
          ))}
        </ul>
      )}

      <FadeIn delay={0.4}>
        <div className="mt-20 pt-10 border-t border-hairline">
          <MetaLabel>Continue exploring</MetaLabel>
          <div className="mt-4 flex flex-wrap gap-3">
            {PATHS.filter(
              (p) => p.slug !== pathSlug && ACADEMY_ROUTE_BY_PATH[p.slug],
            ).map((p) => (
              <Link
                key={p.slug}
                to={`/v2/learn/${ACADEMY_ROUTE_BY_PATH[p.slug]}`}
                className="inline-flex items-center px-4 py-2 surface-drawer rounded-full text-meta ink-muted hover:ink-primary transition-colors"
              >
                {p.title}
              </Link>
            ))}
          </div>
        </div>
      </FadeIn>
    </ArthosPage>
  );
}
