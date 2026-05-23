// V2 Field Notes — curated daily intelligence.
//
// Lens-grouped sections:
//   01. Material to what we hold
//   02. Material to what we're considering
//   03. Material to the regime
//
// Empty sections render with a calm "nothing material today" — empty
// is information. The "curated X from Y candidates" counter is the
// load-bearing trust mechanism that keeps this from being a news feed.

import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { FieldNoteCard } from '../components/FieldNoteCard';
import {
  FIELD_NOTES_TODAY,
  FIELD_NOTES_CURATED_FROM,
  BRIEFING_AS_OF,
  type FieldNote,
  type FieldNoteImpact,
} from '../data/arthosData';
import { useUserPrefs } from '../state/UserPrefsContext';

function FadeIn({
  delay = 0,
  children,
}: {
  delay?: number;
  children: React.ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay, ease: [0.32, 0.72, 0, 1] }}
    >
      {children}
    </motion.div>
  );
}

const IMPACT_LABEL: Record<FieldNoteImpact, string> = {
  portfolio: 'Material to what we hold',
  considering: "Material to what we're considering",
  regime: 'Material to the regime',
};

const IMPACT_EMPTY_STATE: Record<FieldNoteImpact, string> = {
  portfolio: 'Nothing material to what you hold today.',
  considering: "Nothing material to what you're considering today.",
  regime: 'Nothing regime-shifting today.',
};

const IMPACTS: FieldNoteImpact[] = ['portfolio', 'considering', 'regime'];

function isWatchedNote(note: FieldNote, watchlist: string[]): boolean {
  if (watchlist.length === 0) return false;
  return (
    (note.symbol !== undefined && watchlist.includes(note.symbol)) ||
    note.affectedPositions.some((s) => watchlist.includes(s)) ||
    note.affectedOpportunities.some((s) => watchlist.includes(s))
  );
}

export function FieldNotes() {
  const { watchlist } = useUserPrefs();

  const byImpact = useMemo(() => {
    const map: Record<FieldNoteImpact, FieldNote[]> = {
      portfolio: [],
      considering: [],
      regime: [],
    };
    FIELD_NOTES_TODAY.forEach((n) => map[n.impact].push(n));
    return map;
  }, []);

  return (
    <ArthosPage maxWidth="max-w-6xl">
      <FadeIn>
        <header className="mb-10">
          <MetaLabel>Field Notes</MetaLabel>
          <h1 className="font-serif text-masthead ink-primary mt-3 mb-4 max-w-[22ch]">
            What happened today, through our lens.
          </h1>
          <p className="ink-muted leading-relaxed max-w-narrative text-[15px]">
            Curated daily notes on events material to what we hold, what
            we're considering, or how we read the market. Each note answers
            what happened, what it means for us, and what could change our
            reading. No headlines. No feeds.
          </p>
          <div className="flex items-baseline gap-3 mt-5 text-[13px]">
            <span className="text-meta ink-fainter">As of</span>
            <span className="ink-primary tabular-nums">
              {BRIEFING_AS_OF.prettyDate}
            </span>
          </div>
        </header>
      </FadeIn>

      {/* Curated-from counter — the trust mechanism */}
      <FadeIn delay={0.04}>
        <div className="mb-14 max-w-narrative">
          <div className="flex items-baseline gap-3 mb-2">
            <span
              aria-hidden
              className="font-mono ink-primary text-[14px] tabular-nums"
            >
              {FIELD_NOTES_TODAY.length}
            </span>
            <span className="ink-primary text-[14px]">notes today</span>
            <span className="ink-fainter text-[13px] italic">
              curated from {FIELD_NOTES_CURATED_FROM} candidates
            </span>
          </div>
          <p className="text-[12px] ink-fainter italic leading-relaxed">
            Most days we skip more than we publish. A note appears here only
            when it changes what we'd do, what we'd watch, or how we'd read
            the regime.
          </p>
        </div>
      </FadeIn>

      {/* Three impact sections */}
      {IMPACTS.map((impact, ii) => {
        const items = byImpact[impact];
        return (
          <FadeIn key={impact} delay={0.08 + ii * 0.04}>
            <section className="mb-16">
              <div className="flex items-baseline gap-4 mb-2">
                <span className="font-mono ink-fainter text-[13px] tabular-nums">
                  {String(ii + 1).padStart(2, '0')}
                </span>
                <h2 className="font-serif text-headline ink-primary">
                  {IMPACT_LABEL[impact]}
                </h2>
                <span className="text-meta ink-fainter ml-auto">
                  {items.length} {items.length === 1 ? 'note' : 'notes'}
                </span>
              </div>

              {items.length === 0 ? (
                <p className="font-serif italic ink-muted text-[15px] leading-relaxed mt-5 max-w-narrative">
                  {IMPACT_EMPTY_STATE[impact]}
                </p>
              ) : (
                <div className="grid lg:grid-cols-2 gap-6 mt-8">
                  {items.map((n) => (
                    <FieldNoteCard
                      key={n.id}
                      note={n}
                      isWatched={isWatchedNote(n, watchlist)}
                      watchlist={watchlist}
                    />
                  ))}
                </div>
              )}
            </section>
          </FadeIn>
        );
      })}

      {/* Footer doctrine */}
      <FadeIn delay={0.24}>
        <div className="border-t border-hairline pt-12 mt-8">
          <p className="font-serif italic ink-muted text-[16px] leading-relaxed max-w-narrative">
            A note is not news. It is a record of what changed our reading —
            or did not. The empty sections are as honest as the full ones.
          </p>
        </div>
      </FadeIn>
    </ArthosPage>
  );
}
