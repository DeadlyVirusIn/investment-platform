// V2 Pick Detail — per-symbol narrative with thesis, what changed,
// watching, and the lesson behind the pick.

import { useParams, Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import {
  getPosition,
  getPickEvidence,
  getFieldNotesForSymbol,
  LESSONS,
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
      transition={{ duration: 0.5, delay, ease: [0.32, 0.72, 0, 1] }}
    >
      {children}
    </motion.div>
  );
}

const PICK_NARRATIVE: Record<
  string,
  {
    whyWeOwn: string;
    pullquote: string;
    thesis: string[];
    changedToday: string;
    watching: string[];
    lessonSlug: string;
  }
> = {
  AMAT: {
    whyWeOwn:
      'We opened AMAT eighteen days ago on a six-week momentum signal in semiconductor capital equipment.',
    pullquote: 'Day 18 of holding. +4.0% so far. We trimmed a quarter today.',
    thesis: [
      'Semicap momentum has been broader than the headline chip cohort for six consecutive weeks.',
      'AMAT carries the cleanest balance sheet in the group, which matters when the cycle turns.',
      'The position was sized for the original entry. Price has run; weight has drifted; we trimmed.',
    ],
    changedToday:
      "AMAT closed +1.2% on the day. The trim was not a response to price action — it was a response to the position size we'd already set. We sold a quarter of the position and held the remaining three-quarters intact. The cash will be redeployed when the next signal warrants it.",
    watching: [
      'A close below $192 would invalidate the momentum signal and trigger a full exit.',
      'Earnings on May 30. We will not add into the print.',
    ],
    lessonSlug: 'why-great-investors-do-nothing-most-days',
  },
  MSFT: {
    whyWeOwn:
      'We opened MSFT on Day 1 of the portfolio on a multi-quarter cash-flow growth signal that the market multiple had not yet caught up to.',
    pullquote: 'Day 64 of holding. +8.5% so far. We are not trimming yet.',
    thesis: [
      'Twelve-month operating cash flow growth has outpaced the broader software sector for six consecutive quarters.',
      'The price-to-cash-flow multiple has not expanded to match. Historically these gaps narrow.',
      'No material change in margin trend; no change in capital allocation.',
    ],
    changedToday:
      'MSFT was unchanged on the day. The cash-flow gap that opened the position is the cash-flow gap that still holds it. We expect this to be a multi-quarter position; the daily move is not the point.',
    watching: [
      'A slowdown in cloud bookings at the next earnings would invalidate the thesis.',
      'Multiple expansion. If price catches up to cash flow, we will reassess size.',
    ],
    lessonSlug: 'what-is-a-signal',
  },
  COST: {
    whyWeOwn:
      'We opened COST on Day 1 of the portfolio as a multi-year compounder, not as a signal-driven trade.',
    pullquote: 'Day 47 of holding. +8.0% so far. We have done nothing.',
    thesis: [
      'Membership renewal rates remain at multi-year highs.',
      'Same-store sales are positive on flat traffic — the economics of the model, not promotional activity.',
      'This is a position that earns its keep by not being touched.',
    ],
    changedToday:
      'COST was up 0.3% on the day. There is nothing else to report. Positions like this are the foundation of the portfolio; their job is to compound while we spend attention on positions that require it.',
    watching: [
      'A meaningful step down in renewal rates would matter.',
      'Compression in membership-fee economics.',
    ],
    lessonSlug: 'why-great-investors-do-nothing-most-days',
  },
};

export function PickPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const navigate = useNavigate();
  const position = symbol ? getPosition(symbol) : undefined;
  const narrative = symbol
    ? PICK_NARRATIVE[symbol] || PICK_NARRATIVE.MSFT
    : undefined;
  const { inWatchlist, toggleWatchlist } = useUserPrefs();

  if (!position || !narrative) {
    return (
      <ArthosPage maxWidth="max-w-narrative">
        <div className="py-20">
          <p className="ink-muted">No position by that name.</p>
          <Link
            to="/v2/today"
            className="text-meta ink-muted mt-4 inline-block"
          >
            Back to briefing
          </Link>
        </div>
      </ArthosPage>
    );
  }

  const watching = inWatchlist(position.symbol);
  const move = ((position.current - position.costBasis) / position.costBasis) * 100;
  const lesson = LESSONS.find((l) => l.slug === narrative.lessonSlug);
  const evidence = getPickEvidence(position.symbol);
  const fieldNotes = getFieldNotesForSymbol(position.symbol);

  return (
    <ArthosPage maxWidth="max-w-copy">
      <button
        onClick={() => navigate(-1)}
        className="text-meta ink-fainter hover:ink-muted mb-12 inline-flex items-center gap-1.5 transition-colors"
      >
        <span aria-hidden>←</span> Briefing
      </button>

      <FadeIn>
        <div className="mb-12">
          <div className="flex items-center justify-between gap-4 mb-2">
            <div className="font-mono text-meta ink-fainter">
              {position.symbol}
            </div>
            <button
              onClick={() => toggleWatchlist(position.symbol)}
              className={`text-meta inline-flex items-center gap-1.5 transition-colors ${
                watching ? 'ink-primary' : 'ink-fainter hover:ink-muted'
              }`}
              aria-label={
                watching ? 'Remove from watchlist' : 'Add to watchlist'
              }
            >
              <span aria-hidden className="text-[15px] leading-none">
                {watching ? '★' : '☆'}
              </span>
              {watching ? 'Watching' : 'Watch'}
            </button>
          </div>
          <h1 className="font-serif text-headline ink-primary mb-3">
            {position.company}
          </h1>
          <div className="text-meta ink-muted tabular-nums">
            Day {position.dayHeld} · Cost ${position.costBasis.toFixed(2)} ·
            Now ${position.current.toFixed(2)} · {move >= 0 ? '+' : ''}
            {move.toFixed(1)}%
          </div>
        </div>
      </FadeIn>

      {/* As-of stamp — anchors the page to a specific snapshot window */}
      {evidence && (
        <FadeIn delay={0.04}>
          <div className="mb-12 max-w-narrative">
            <div className="flex items-baseline gap-3 mb-1.5">
              <MetaLabel>As of</MetaLabel>
              <span className="ink-primary text-[13px] tabular-nums">
                {evidence.asOf.prettyDate}
              </span>
            </div>
            <p className="ink-fainter text-[12px] italic leading-relaxed">
              {evidence.horizon}
            </p>
          </div>
        </FadeIn>
      )}

      <FadeIn delay={0.06}>
        <p className="font-serif text-subhead ink-primary leading-snug mb-16 max-w-narrative">
          {narrative.whyWeOwn}
        </p>
      </FadeIn>

      <FadeIn delay={0.12}>
        <blockquote
          className="font-serif italic text-[22px] leading-snug ink-warm max-w-narrative mb-24"
          style={{ fontVariationSettings: '"opsz" 32' }}
        >
          {narrative.pullquote}
        </blockquote>
      </FadeIn>

      {/* Evidence panel — what fired, where the data came from, our stance */}
      {evidence && (
        <FadeIn delay={0.14}>
          <section className="mb-24">
            <MetaLabel>What we're seeing</MetaLabel>
            <ul className="mt-6 space-y-7 max-w-copy">
              {evidence.signals.map((s, i) => (
                <li
                  key={i}
                  className="grid sm:grid-cols-[1fr_auto] gap-x-8 gap-y-1.5 items-baseline border-t border-hairline pt-6"
                >
                  <div className="min-w-0">
                    <div className="ink-primary text-[15px] leading-snug mb-1">
                      {s.label}
                    </div>
                    <div className="ink-fainter text-[12px] leading-relaxed">
                      {s.source}
                    </div>
                  </div>
                  <div className="ink-muted text-[13px] tabular-nums leading-snug sm:text-right">
                    {s.reading}
                  </div>
                </li>
              ))}
            </ul>

            <div className="grid sm:grid-cols-2 gap-x-10 gap-y-6 mt-12 pt-8 border-t border-hairline max-w-copy">
              <div>
                <MetaLabel>Data sources</MetaLabel>
                <ul className="mt-3 space-y-1">
                  {evidence.dataSources.map((d, i) => (
                    <li
                      key={i}
                      className="ink-muted text-[13px] leading-relaxed"
                    >
                      {d}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <MetaLabel>Our stance</MetaLabel>
                <div className="mt-3 ink-primary italic text-[15px] leading-snug mb-2">
                  {evidence.confidence}
                </div>
                <p className="ink-muted text-[13px] leading-relaxed">
                  {evidence.confidenceNote}
                </p>
              </div>
            </div>
          </section>
        </FadeIn>
      )}

      {/* Bull case + Bear case — explicit both-sides reasoning */}
      {evidence && (
        <FadeIn delay={0.18}>
          <section className="mb-24">
            <MetaLabel>Both sides</MetaLabel>
            <div className="grid md:grid-cols-2 gap-px bg-hairline mt-6 max-w-copy">
              <div className="surface-drawer p-7">
                <div className="text-meta ink-fainter mb-3">
                  Why this works
                </div>
                <p className="ink-primary leading-relaxed text-[15px]">
                  {evidence.bullCase}
                </p>
              </div>
              <div className="surface-drawer p-7">
                <div className="text-meta ink-fainter mb-3">
                  What would break it
                </div>
                <p className="ink-primary leading-relaxed text-[15px]">
                  {evidence.bearCase}
                </p>
              </div>
            </div>
          </section>
        </FadeIn>
      )}

      <FadeIn delay={0.2}>
        <section className="mb-24">
          <MetaLabel>What changed today</MetaLabel>
          <p className="mt-6 ink-muted leading-relaxed max-w-narrative">
            {narrative.changedToday}
          </p>
        </section>
      </FadeIn>

      <FadeIn delay={0.22}>
        <section className="mb-24">
          <MetaLabel>What we're watching</MetaLabel>
          <div className="mt-6 space-y-3 max-w-narrative ink-muted leading-relaxed">
            {narrative.watching.map((w, i) => (
              <p key={i}>{w}</p>
            ))}
          </div>
        </section>
      </FadeIn>

      {/* Catalyst timeline — dated, with dispositions */}
      {evidence && evidence.catalysts.length > 0 && (
        <FadeIn delay={0.24}>
          <section className="mb-24">
            <MetaLabel>Catalysts ahead</MetaLabel>
            <ul className="mt-6 space-y-5 max-w-narrative">
              {evidence.catalysts.map((c, i) => (
                <li key={i} className="flex items-baseline gap-5">
                  <span className="font-mono ink-primary text-[13px] tabular-nums w-20 shrink-0">
                    {c.prettyDate}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="ink-primary text-[14px] mb-1">
                      {c.label}
                    </div>
                    {c.note && (
                      <div className="ink-muted text-[12px] italic leading-relaxed">
                        {c.note}
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </FadeIn>
      )}

      {/* Thesis evolution — the case-study log */}
      {evidence && evidence.thesisEvolution.length > 0 && (
        <FadeIn delay={0.26}>
          <section className="mb-24">
            <MetaLabel>How our view has evolved</MetaLabel>
            <ol className="mt-6 max-w-narrative border-l border-hairline pl-6 space-y-7">
              {evidence.thesisEvolution.map((e, i) => (
                <li key={i} className="relative">
                  <span
                    aria-hidden
                    className="absolute -left-[27px] top-2 w-2 h-2 rounded-full"
                    style={{ backgroundColor: 'var(--ink-fainter)' }}
                  />
                  <div className="font-mono ink-fainter text-[12px] tabular-nums mb-1.5">
                    {e.prettyDate}
                  </div>
                  <p className="ink-muted text-[14px] leading-relaxed">
                    {e.note}
                  </p>
                </li>
              ))}
            </ol>
          </section>
        </FadeIn>
      )}

      {/* Field notes on this name — Phase 5 Pick integration */}
      {fieldNotes.length > 0 && (
        <FadeIn delay={0.27}>
          <section className="mb-24">
            <MetaLabel>Field notes on this name</MetaLabel>
            <p className="ink-muted text-[13px] italic leading-relaxed mt-3 mb-6 max-w-narrative">
              Curated notes from today's session that touch this position.
            </p>
            <ul className="space-y-px bg-hairline max-w-copy">
              {fieldNotes.map((n) => (
                <li
                  key={n.id}
                  className="surface-base py-5 flex items-baseline gap-5 flex-wrap"
                >
                  <span className="font-mono ink-fainter text-[12px] tabular-nums w-20 shrink-0">
                    {n.prettyTime}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-3 mb-1 flex-wrap">
                      <span className="text-meta ink-fainter">
                        {n.kindLabel}
                      </span>
                    </div>
                    <div className="ink-primary text-[14px] leading-snug">
                      {n.headline}
                    </div>
                  </div>
                  <Link
                    to="/v2/field-notes"
                    className="text-meta ink-muted hover:ink-primary transition-colors shrink-0 ml-auto"
                  >
                    Read →
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        </FadeIn>
      )}

      {/* Review date — gives the page a future hook */}
      {evidence && (
        <FadeIn delay={0.28}>
          <section className="mb-24 max-w-narrative">
            <p className="font-serif italic ink-muted text-[16px] leading-relaxed">
              We re-read this thesis on{' '}
              <span className="ink-primary not-italic">
                {evidence.reviewDate}
              </span>
              . Until then, the position is held.
            </p>
          </section>
        </FadeIn>
      )}

      {lesson && (
        <FadeIn delay={0.28}>
          <section className="border-t border-hairline pt-12">
            <MetaLabel>The lesson behind this pick</MetaLabel>
            <Link
              to={`/v2/learn/lesson/${lesson.slug}`}
              className="block surface-drawer p-7 mt-6 hover:opacity-90 transition-opacity max-w-copy"
            >
              <div className="font-serif text-subhead ink-primary mb-2">
                {lesson.title}
              </div>
              <div className="ink-muted leading-relaxed mb-3">
                {lesson.abstract}
              </div>
              <div className="text-meta ink-fainter">
                {lesson.readMinutes} min read
              </div>
            </Link>
          </section>
        </FadeIn>
      )}
    </ArthosPage>
  );
}
