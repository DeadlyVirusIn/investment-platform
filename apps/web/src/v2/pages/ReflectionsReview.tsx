// V2 Reflections review.
//
// Route: /v2/reflections
//
// Chronological list of every saved reflection. Filterable by kind.
// Each entry shows excerpt + the target lesson/trade title + date +
// a deep-link back to the surface that produced it.
//
// Reuses ArthosPage + MetaLabel + FadeIn. No new dependencies. Pure
// read from lib/reflections.useReflections() + arthosData.getLesson().

import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { MeTabs } from './components/MeTabs';
import {
  useReflections,
  deleteReflection,
  type Reflection,
  type ReflectionKind,
} from '../lib/reflections';
import { getLesson } from '../data/arthosData';
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

type FilterKind = 'all' | 'lesson-capture' | 'paper-trade-review';

const FILTERS: { value: FilterKind; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'lesson-capture', label: 'Lessons' },
  { value: 'paper-trade-review', label: 'Paper trades' },
];

function kindLabel(kind: ReflectionKind): string {
  switch (kind) {
    case 'lesson-capture':
      return 'Lesson';
    case 'paper-trade-review':
      return 'Paper trade';
    case 'mistake':
      return 'Mistake';
    case 'thesis-review':
      return 'Thesis';
    case 'journal-note':
      return 'Note';
    case 'start-here':
      return 'Day 1';
    default:
      return 'Reflection';
  }
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

function fmtDateGroup(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: 'long',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

function dayKey(iso: string): string {
  return iso.slice(0, 10); // YYYY-MM-DD
}

function groupByDay(items: Reflection[]): {
  day: string;
  iso: string;
  items: Reflection[];
}[] {
  const map = new Map<string, { iso: string; items: Reflection[] }>();
  for (const r of items) {
    const k = dayKey(r.createdAt);
    if (!map.has(k)) map.set(k, { iso: r.createdAt, items: [] });
    map.get(k)!.items.push(r);
  }
  return Array.from(map.entries()).map(([day, v]) => ({
    day,
    iso: v.iso,
    items: v.items,
  }));
}

export function ReflectionsReview() {
  const all = useReflections();
  const paper = usePaperBook();
  const [filter, setFilter] = useState<FilterKind>('all');

  const filtered = useMemo(() => {
    if (filter === 'all') return all;
    return all.filter((r) => r.kind === filter);
  }, [all, filter]);

  const groups = useMemo(() => groupByDay(filtered), [filtered]);

  // Lookup helpers for entry targets.
  const positionById = useMemo(() => {
    const map = new Map<string, string>(); // id → "symbol · side"
    for (const p of paper.positions) {
      map.set(p.id, `${p.symbol} · ${p.side.replace('-', ' ')}`);
    }
    for (const h of paper.history) {
      map.set(h.id, `${h.symbol} · closed`);
    }
    return map;
  }, [paper.positions, paper.history]);

  function targetLabel(r: Reflection): { text: string; to?: string } {
    if (r.kind === 'lesson-capture' && r.targetId) {
      const lesson = getLesson(r.targetId);
      if (lesson) {
        return {
          text: `on lesson "${lesson.title}"`,
          to: `/v2/learn/lesson/${lesson.slug}`,
        };
      }
      return { text: `on lesson · ${r.targetId}` };
    }
    if (r.kind === 'paper-trade-review' && r.targetId) {
      const pos = positionById.get(r.targetId);
      // Find originLessonSlug for the trade — if present, link back
      // to the Try page; else portfolio.
      const linkedPos =
        paper.positions.find((p) => p.id === r.targetId) ??
        paper.history.find((h) => h.id === r.targetId);
      const lessonSlug = linkedPos?.originLessonSlug;
      if (lessonSlug) {
        return {
          text: `on paper trade · ${pos ?? r.targetId}`,
          to: `/v2/try/${lessonSlug}`,
        };
      }
      return {
        text: `on paper trade · ${pos ?? r.targetId}`,
        to: '/v2/portfolio',
      };
    }
    return { text: kindLabel(r.kind) };
  }

  return (
    <ArthosPage maxWidth="max-w-3xl">
      <MeTabs />
      <FadeIn>
        <MetaLabel>Reflect</MetaLabel>
        <h1 className="font-serif ink-primary text-masthead leading-[1.05] mt-2 mb-5 max-w-[18ch]">
          Your reflections
        </h1>
        <p className="ink-muted leading-relaxed text-[17px] max-w-narrative mb-3">
          Everything you've written, kept on this device. Never sent
          anywhere. Nothing is graded.
        </p>
        <p className="ink-fainter leading-relaxed text-[14px] mb-12">
          {all.length} {all.length === 1 ? 'reflection' : 'reflections'} total
        </p>
      </FadeIn>

      <FadeIn delay={0.1}>
        <div
          role="tablist"
          aria-label="Filter reflections by kind"
          className="flex flex-wrap gap-2 mb-10"
        >
          {FILTERS.map((f) => {
            const active = filter === f.value;
            const count =
              f.value === 'all'
                ? all.length
                : all.filter((r) => r.kind === f.value).length;
            return (
              <button
                key={f.value}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setFilter(f.value)}
                className="inline-flex items-center px-4 py-2 rounded-full text-meta transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ink-muted)]"
                style={{
                  backgroundColor: active
                    ? 'var(--ink-primary)'
                    : 'var(--surface-drawer)',
                  color: active
                    ? 'var(--surface-base)'
                    : 'var(--ink-muted)',
                }}
              >
                {f.label} · {count}
              </button>
            );
          })}
        </div>
      </FadeIn>

      {groups.length === 0 ? (
        <FadeIn delay={0.2}>
          <div className="surface-drawer p-6 sm:p-8">
            <p className="ink-muted leading-relaxed text-[15px]">
              {filter === 'all'
                ? 'No reflections yet. Open any lesson and the reflection prompt at the bottom is where this list starts.'
                : 'No reflections in this category yet.'}
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <Link
                to="/v2/learn"
                className="inline-flex items-center px-4 py-2 surface-elevated rounded-full text-meta ink-muted hover:ink-primary transition-colors"
              >
                Browse lessons
              </Link>
              <Link
                to="/v2/start"
                className="inline-flex items-center px-4 py-2 surface-elevated rounded-full text-meta ink-muted hover:ink-primary transition-colors"
              >
                Day 1 flow
              </Link>
            </div>
          </div>
        </FadeIn>
      ) : (
        <div className="space-y-10">
          {groups.map((g, gi) => (
            <FadeIn key={g.day} delay={0.1 + gi * 0.04}>
              <section>
                <div className="text-meta ink-fainter mb-4 border-b border-hairline pb-2">
                  {fmtDateGroup(g.iso)}
                </div>
                <ul className="space-y-px bg-hairline">
                  {g.items.map((r) => {
                    const target = targetLabel(r);
                    const inner = (
                      <article className="surface-drawer p-5 sm:p-6">
                        <div className="text-meta ink-fainter mb-2 flex items-center gap-2">
                          <span
                            className="inline-block px-2 py-0.5 rounded-full text-[10px] uppercase tracking-[0.12em]"
                            style={{
                              backgroundColor: 'var(--surface-elevated)',
                              color: 'var(--ink-muted)',
                            }}
                          >
                            {kindLabel(r.kind)}
                          </span>
                          <span>{target.text}</span>
                          <span className="ml-auto tabular-nums">
                            {fmtDate(r.createdAt)}
                          </span>
                        </div>
                        {r.prompt && (
                          <p className="ink-fainter italic text-[13px] leading-relaxed mb-2 max-w-narrative">
                            "{r.prompt}"
                          </p>
                        )}
                        <blockquote className="font-serif italic ink-primary text-[15px] leading-relaxed max-w-narrative">
                          "{r.body.length > 320
                            ? r.body.slice(0, 316) + '…'
                            : r.body}"
                        </blockquote>
                        <div className="mt-3 flex items-center gap-4">
                          {target.to && (
                            <Link
                              to={target.to}
                              className="text-meta ink-fainter hover:ink-muted transition-colors"
                            >
                              Open →
                            </Link>
                          )}
                          <button
                            type="button"
                            onClick={() => deleteReflection(r.id)}
                            className="text-meta ink-fainter hover:ink-muted transition-colors"
                            aria-label={`Delete reflection from ${fmtDate(r.createdAt)}`}
                          >
                            Delete
                          </button>
                        </div>
                      </article>
                    );
                    return <li key={r.id}>{inner}</li>;
                  })}
                </ul>
              </section>
            </FadeIn>
          ))}
        </div>
      )}

      <FadeIn delay={0.45}>
        <div className="mt-16 pt-10 border-t border-hairline">
          <MetaLabel>Where to go next</MetaLabel>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link
              to="/v2/me"
              className="inline-flex items-center px-4 py-2 surface-drawer rounded-full text-meta ink-muted hover:ink-primary transition-colors"
            >
              Your ArthOS
            </Link>
            <Link
              to="/v2/learn"
              className="inline-flex items-center px-4 py-2 surface-drawer rounded-full text-meta ink-muted hover:ink-primary transition-colors"
            >
              Browse lessons
            </Link>
            <Link
              to="/v2/today"
              className="inline-flex items-center px-4 py-2 surface-drawer rounded-full text-meta ink-muted hover:ink-primary transition-colors"
            >
              Today's briefing
            </Link>
          </div>
        </div>
      </FadeIn>
    </ArthosPage>
  );
}
