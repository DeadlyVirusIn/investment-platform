// Click-trigger glossary popover + auto-linker.
//
// Source: wise-start-bloom-31433ca8/src/components/GlossaryPopover.tsx
// Adaptations from upstream:
//   - <Link> swapped from @tanstack/react-router → react-router-dom.
//   - Term route swapped to '/v2/learn/lesson/:slug' (absolute path).
//   - Journal route ('/v2/journal/:id') links rendered conditionally;
//     V2 GlossaryTerm currently has no related-journal field, so the
//     section is omitted until Phase 6 (Decision Journal surface).
//   - Type imports point at V2's GlossaryTerm (arthosData) — fields are
//     `shortDefinition`, `examples[]`, `lessonRefs` (V2) rather than
//     `short`, `example` (string), `relatedLessonSlugs` (Lovable).
//   - Tailwind tokens replaced with V2-token equivalents or arbitrary
//     hex values where utility classes are unavailable outside v2-root
//     (Radix portals content to document.body).
//
// Coexists with ArthosChrome.TermInline (hover, lightweight, used by
// ParagraphWithTerms). GlossaryPopover is the richer click-trigger
// surface intended for academy + glossary-index pages.

import { Link } from 'react-router-dom';
import { BookOpen, ArrowRight } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import { GLOSSARY, getTerm, type GlossaryTerm } from '../data/arthosData';

// Match-aliases for each glossary slug — every form we should auto-link
// in body copy. Keep these conservative; over-linking is worse than
// under-linking. Slugs must exist in V2 GLOSSARY (arthosData.ts).
const ALIASES: Record<string, string[]> = {
  'drawdown': ['drawdown', 'drawdowns'],
  'stop-loss': ['stop loss', 'stop-loss'],
  'trim': ['trim', 'trimming'],
  'momentum': ['momentum'],
  'mean-reversion': ['mean reversion', 'mean-reversion'],
  'position-sizing': ['position sizing', 'sizing'],
  // P1.3 — additions (entries live in arthosData GLOSSARY).
  'net-asset-value': ['NAV', 'net asset value'],
  'expectancy': ['expectancy'],
  'days-to-expiration': ['DTE', 'days to expiration'],
  'breakeven': ['breakeven', 'break-even'],
};

// Build one regex with capture groups, longest aliases first so longer
// matches win over shorter overlapping ones.
const aliasPairs = Object.entries(ALIASES).flatMap(([slug, words]) =>
  words.map((w) => ({ slug, word: w })),
);
aliasPairs.sort((a, b) => b.word.length - a.word.length);
const pattern = new RegExp(
  `\\b(${aliasPairs
    .map((p) => p.word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .join('|')})\\b`,
  'gi',
);

function lookupSlug(matched: string): string | null {
  const lower = matched.toLowerCase();
  for (const p of aliasPairs) {
    if (p.word.toLowerCase() === lower) return p.slug;
  }
  return null;
}

export function GlossaryPopover({
  term,
  children,
}: {
  term: GlossaryTerm;
  children: React.ReactNode;
}) {
  const lessons = term.lessonRefs ?? [];
  const example = term.examples?.[0]?.outcome;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="font-medium underline decoration-dotted underline-offset-[3px] rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ink-muted,#B5AC9B)]"
          style={{
            color: 'var(--ink-primary, #ECE6D8)',
            textDecorationColor: 'var(--ink-fainter, #7C7568)',
          }}
          aria-label={`Definition of ${term.term}`}
        >
          {children}
        </button>
      </PopoverTrigger>
      <PopoverContent side="top" align="start" className="w-80">
        <div className="p-4">
          <p
            className="text-[10.5px] font-bold uppercase tracking-[0.18em] mb-1.5 flex items-center gap-1.5"
            style={{ color: 'var(--ink-muted, #B5AC9B)' }}
          >
            <BookOpen className="size-3" aria-hidden /> Glossary
          </p>
          <p
            className="text-[20px] leading-tight mb-1.5 font-serif"
            style={{
              fontFamily: '"Newsreader", Georgia, serif',
              color: 'var(--ink-primary, #ECE6D8)',
            }}
          >
            {term.term}
          </p>
          <p
            className="text-[13.5px] leading-relaxed mb-2"
            style={{ color: 'var(--ink-muted, #B5AC9B)' }}
          >
            {term.shortDefinition}
          </p>
          {example && (
            <p
              className="text-[12.5px] leading-relaxed italic"
              style={{ color: 'var(--ink-fainter, #7C7568)' }}
            >
              {example}
            </p>
          )}
        </div>
        {lessons.length > 0 && (
          <div
            className="border-t p-4"
            style={{
              borderColor: 'var(--hairline, rgba(236,230,216,0.08))',
              backgroundColor: 'var(--surface-elevated, #1F1B14)',
            }}
          >
            <p
              className="text-[10.5px] font-bold uppercase tracking-[0.18em] mb-1.5"
              style={{ color: 'var(--ink-muted, #B5AC9B)' }}
            >
              Related lessons
            </p>
            <ul className="space-y-1">
              {lessons.map((slug) => (
                <li key={slug}>
                  <Link
                    to={`/v2/learn/lesson/${slug}`}
                    className="group inline-flex items-center gap-1 text-[12.5px] font-semibold"
                    style={{ color: 'var(--ink-primary, #ECE6D8)' }}
                  >
                    {slug.replace(/-/g, ' ')}
                    <ArrowRight className="size-3 opacity-50 group-hover:opacity-100" />
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}

/**
 * Auto-link known glossary words inside a string. Use sparingly — only
 * on lesson body paragraphs and journal thesis text, not on UI labels.
 * Returns React nodes interleaving plain text with <GlossaryPopover>.
 */
export function GlossaryText({ text }: { text: string }) {
  const out: React.ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  pattern.lastIndex = 0;
  while ((m = pattern.exec(text)) !== null) {
    const slug = lookupSlug(m[0]);
    if (!slug) continue;
    const term = getTerm(slug);
    if (!term) continue;
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(
      <GlossaryPopover key={`${slug}-${m.index}`} term={term}>
        {m[0]}
      </GlossaryPopover>,
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return <>{out}</>;
}

export const allGlossary = GLOSSARY;
