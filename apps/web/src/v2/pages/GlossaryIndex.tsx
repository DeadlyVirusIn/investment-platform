// V2 Glossary index — A–Z list of terms with click-trigger popovers.
//
// Route: /v2/learn/glossary
//
// Uses GlossaryPopover (Phase 2 port) for rich popover content +
// related-lesson links. Bullet list groups terms by first letter.

import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { GLOSSARY } from '../data/arthosData';
import { GlossaryPopover } from '../components/GlossaryPopover';

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

export function GlossaryIndex() {
  const groups = useMemo(() => {
    const buckets = new Map<string, typeof GLOSSARY>();
    const sorted = [...GLOSSARY].sort((a, b) =>
      a.term.localeCompare(b.term),
    );
    for (const t of sorted) {
      const letter = t.term[0]?.toUpperCase() ?? '#';
      if (!buckets.has(letter)) buckets.set(letter, []);
      buckets.get(letter)!.push(t);
    }
    return Array.from(buckets.entries());
  }, []);

  return (
    <ArthosPage maxWidth="max-w-3xl">
      <FadeIn>
        <MetaLabel>Reference</MetaLabel>
        <h1 className="font-serif ink-primary text-masthead leading-[1.05] mt-2 mb-5 max-w-[18ch]">
          Glossary
        </h1>
        <p className="ink-muted leading-relaxed text-[17px] max-w-narrative mb-12 sm:mb-16">
          Every working concept this portfolio uses. Click a term for
          the short definition; the popover links to the lessons that
          teach it.
        </p>
      </FadeIn>

      {groups.length === 0 ? (
        <FadeIn delay={0.1}>
          <p className="ink-fainter italic">No terms yet.</p>
        </FadeIn>
      ) : (
        <div className="space-y-12">
          {groups.map(([letter, terms], gi) => (
            <FadeIn key={letter} delay={0.1 + gi * 0.04}>
              <section>
                <div className="text-meta ink-fainter mb-4 border-b border-hairline pb-2">
                  {letter}
                </div>
                <ul className="space-y-5">
                  {terms.map((t) => (
                    <li key={t.slug}>
                      <div className="flex items-baseline gap-3 mb-1">
                        <GlossaryPopover term={t}>
                          <span className="font-serif text-[20px] leading-tight">
                            {t.term}
                          </span>
                        </GlossaryPopover>
                        {t.lessonRefs && t.lessonRefs.length > 0 && (
                          <span className="text-meta ink-fainter">
                            · {t.lessonRefs.length} lesson
                            {t.lessonRefs.length === 1 ? '' : 's'}
                          </span>
                        )}
                      </div>
                      <p className="ink-muted leading-relaxed text-[15px] max-w-narrative">
                        {t.shortDefinition}
                      </p>
                    </li>
                  ))}
                </ul>
              </section>
            </FadeIn>
          ))}
        </div>
      )}

      <FadeIn delay={0.5}>
        <div className="mt-20 pt-10 border-t border-hairline">
          <MetaLabel>Where to go next</MetaLabel>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link
              to="/learn"
              className="inline-flex items-center px-4 py-2 surface-drawer rounded-full text-meta ink-muted hover:ink-primary transition-colors"
            >
              All paths
            </Link>
            <Link
              to="/today"
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
