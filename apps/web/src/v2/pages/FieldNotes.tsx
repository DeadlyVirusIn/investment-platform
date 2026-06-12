// V2 Field Notes — curated daily intelligence.
//
// P6E.2B truth pass: the fabricated FIELD_NOTES_TODAY notes and the
// static "curated from N candidates" counter are no longer rendered.
// The page keeps its route and shell, and states honestly that field
// notes are not wired to live trade history yet.

import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';

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

export function FieldNotes() {
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
        </header>
      </FadeIn>

      {/* Honest empty state — no live data source connected yet */}
      <FadeIn delay={0.06}>
        <div className="border-t border-hairline pt-12">
          <p className="font-serif italic ink-muted text-[18px] leading-relaxed max-w-narrative">
            Field notes are not yet connected to live trade history.
          </p>
          <p className="ink-fainter leading-relaxed max-w-narrative mt-4 text-[14px]">
            When they are, every note here will trace back to a real position,
            a real close, or a real change in the engine's reading — nothing
            illustrative, nothing hand-written.
          </p>
        </div>
      </FadeIn>

      {/* Footer doctrine */}
      <FadeIn delay={0.12}>
        <div className="border-t border-hairline pt-12 mt-16">
          <p className="font-serif italic ink-muted text-[16px] leading-relaxed max-w-narrative">
            A note is not news. It is a record of what changed our reading —
            or did not. The empty sections are as honest as the full ones.
          </p>
        </div>
      </FadeIn>
    </ArthosPage>
  );
}
