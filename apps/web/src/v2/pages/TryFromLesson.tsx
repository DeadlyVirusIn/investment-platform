// V2 Try — paper-trade the idea from a lesson.
//
// Route: /v2/try/:lessonSlug
//
// Flow:
//   1. Look up lesson by slug; derive a Recommendation either from
//      TODAYS_DESK (when the lesson is in scope of an active desk pick)
//      or by constructing a fallback from the lesson's connectedSymbol
//      + PORTFOLIO data.
//   2. Show pre-filled setup card (symbol, side, suggested size, thesis,
//      invalidation).
//   3. Render adjustable knobs (size %, hold-for, stop).
//   4. On submit, call openFromRec(rec, quantity, lessonSlug).
//   5. Post-open: show position state + ReflectionCapture
//      (kind="paper-trade-review", targetId=position.id).
//
// Reuses ArthOS chrome (ArthosPage, MetaLabel, FadeIn), existing
// PaperBook state, ReflectionCapture, and the GlossaryPopover-aware
// ParagraphWithTerms. No new dependencies.

import { useMemo, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, Check } from 'lucide-react';
import {
  ArthosPage,
  MetaLabel,
  ParagraphWithTerms,
} from '../chrome/ArthosChrome';
import { PageHeader } from '../components/ui/PageHeader';
import {
  getLesson,
  getPosition,
  TODAYS_DESK,
  type Recommendation,
} from '../data/arthosData';
import { usePaperBook } from '../state/PaperBook';
import { ReflectionCapture } from '../components/ReflectionCapture';
import { PillButton } from '../components/ui/PillButton';
import { markLessonRead, useLessonRead } from '../lib/lesson-progress';

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

// LoopRibbon — 5-step coach progress strip. Visualises the
// learning loop without taking on the SixStepRibbon Decision-Journal
// vocabulary (which references a surface not yet shipped).
function LoopRibbon({
  state,
}: {
  state: { lesson: boolean; reflect: boolean; try_: boolean; track: boolean; review: boolean };
}) {
  const steps: { key: keyof typeof state; label: string }[] = [
    { key: 'lesson', label: 'Lesson' },
    { key: 'reflect', label: 'Reflect' },
    { key: 'try_', label: 'Try' },
    { key: 'track', label: 'Track' },
    { key: 'review', label: 'Review' },
  ];
  return (
    <ol
      className="flex items-center gap-1.5 w-full text-[10.5px]"
      aria-label="Coach loop progress"
    >
      {steps.map((s) => {
        const done = state[s.key];
        return (
          <li key={s.key} className="flex-1 flex flex-col gap-1.5 items-stretch">
            <span
              className="h-1 rounded-full transition-colors"
              style={{
                backgroundColor: done ? 'var(--brand)' : 'var(--sage-light)',
              }}
              aria-hidden
            />
            <span
              className="font-semibold uppercase tracking-[0.14em] truncate"
              style={{
                fontSize: 10.5,
                color: done ? 'var(--brand)' : 'var(--muted-foreground)',
              }}
            >
              {s.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

// Resolve a Recommendation for a lesson. Prefer a placeable
// TODAYS_DESK entry whose lessonSlug matches; otherwise synthesise
// a long-stock recommendation from the lesson's connectedSymbol +
// PORTFOLIO current price.
function resolveRecForLesson(lessonSlug: string): Recommendation | null {
  const lesson = getLesson(lessonSlug);
  if (!lesson) return null;
  const deskMatch =
    TODAYS_DESK.stocks.find(
      (r) => r.lessonSlug === lessonSlug && r.placeable,
    ) ??
    TODAYS_DESK.options.find(
      (r) => r.lessonSlug === lessonSlug && r.placeable,
    );
  if (deskMatch) return deskMatch;

  const sym = lesson.connectedSymbol;
  const pos = getPosition(sym);
  const entryPrice = pos?.current ?? 100;
  return {
    symbol: sym,
    kind: 'stock',
    actionLabel: `Practice a long on ${sym}`,
    paragraph:
      pos?.thesisShort ??
      `Use this trade to act on the idea from "${lesson.title}." Nothing real is at stake.`,
    entry: `Long at $${entryPrice.toFixed(2)}`,
    target: '—',
    invalidate: '—',
    sizing: 'Quarter position',
    lessonSlug,
    placeable: true,
    side: 'long',
    entryPrice,
    defaultQuantity: 10,
  };
}

const SIZE_PRESETS = [
  { label: '1%', pct: 0.01 },
  { label: '2%', pct: 0.02 },
  { label: '5%', pct: 0.05 },
];

const HOLD_PRESETS = [
  { label: '1 week' },
  { label: '1 month' },
  { label: 'Open-ended' },
];

const STOP_PRESETS = [
  { label: '−3%' },
  { label: '−5%' },
  { label: 'None' },
];

export function TryFromLesson() {
  const { lessonSlug = '' } = useParams<{ lessonSlug: string }>();
  const lesson = getLesson(lessonSlug);
  const rec = useMemo(() => resolveRecForLesson(lessonSlug), [lessonSlug]);
  const paper = usePaperBook();
  const isRead = useLessonRead(lessonSlug);

  // Existing open position from this lesson — drives the post-open
  // state and prevents duplicate opens.
  const existing = paper.positions.find(
    (p) => p.originLessonSlug === lessonSlug,
  );
  const closedFromLesson = paper.history.filter(
    (h) => h.originLessonSlug === lessonSlug,
  );

  const [sizeIdx, setSizeIdx] = useState(1); // default 2%
  const [holdIdx, setHoldIdx] = useState(1); // default 1 month
  const [stopIdx, setStopIdx] = useState(1); // default −5%
  const [error, setError] = useState<string | null>(null);

  if (!lesson) {
    return (
      <ArthosPage>
        <FadeIn>
          <MetaLabel>Not found</MetaLabel>
          <h1 className="font-serif ink-primary text-headline leading-tight mt-2 mb-6">
            No lesson at this path.
          </h1>
          <Link to="/learn" className="ink-muted underline">
            Back to Learn
          </Link>
        </FadeIn>
      </ArthosPage>
    );
  }

  if (!rec) {
    return (
      <ArthosPage>
        <FadeIn>
          <MetaLabel>Try</MetaLabel>
          <h1 className="font-serif ink-primary text-headline leading-tight mt-2 mb-6 max-w-[24ch]">
            This lesson doesn't have a paper-trade idea yet.
          </h1>
          <Link
            to={`/learn/lesson/${lessonSlug}`}
            className="ink-muted underline"
          >
            Back to the lesson
          </Link>
        </FadeIn>
      </ArthosPage>
    );
  }

  const sizePct = SIZE_PRESETS[sizeIdx].pct;
  const bookValue = paper.bookValue;
  const cashTarget = bookValue * sizePct;
  const entryPrice = rec.entryPrice ?? 0;
  const multiplier = rec.kind === 'option' ? 100 : 1;
  const suggestedQty = entryPrice > 0
    ? Math.max(1, Math.floor(cashTarget / (entryPrice * multiplier)))
    : rec.defaultQuantity ?? 1;

  const handleOpen = () => {
    setError(null);
    if (!isRead) markLessonRead(lessonSlug, true);
    const result = paper.openFromRec(rec, suggestedQty, lessonSlug);
    if (!result.ok) setError(result.reason ?? 'Could not open trade.');
  };

  const loopState = {
    lesson: isRead || !!existing || closedFromLesson.length > 0,
    reflect: false, // resolved by ReflectionCapture; treated as "in progress" below
    try_: !!existing || closedFromLesson.length > 0,
    track: !!existing,
    review: closedFromLesson.length > 0,
  };

  return (
    <ArthosPage maxWidth="max-w-3xl">
      <Link
        to={`/learn/lesson/${lessonSlug}`}
        className="text-meta ink-fainter hover:ink-muted mb-10 inline-flex items-center gap-1.5 transition-colors"
      >
        <ArrowLeft className="size-3.5" aria-hidden /> Back to the lesson
      </Link>

      <FadeIn>
        <PageHeader
          eyebrow="Try"
          title={
            existing
              ? `You've opened a paper trade from "${lesson.title}."`
              : `Try the idea from "${lesson.title}."`
          }
          description={
            existing
              ? 'We mark this position daily. When the thesis resolves, come back to review.'
              : 'An illustrative practice scenario pre-filled from the lesson — not live market guidance. Adjust the knobs if you want; open the position when you are ready.'
          }
        />
      </FadeIn>

      <FadeIn delay={0.1}>
        <section className="mb-12">
          <MetaLabel>Coach loop</MetaLabel>
          <div className="mt-3">
            <LoopRibbon state={loopState} />
          </div>
        </section>
      </FadeIn>

      <FadeIn delay={0.15}>
        <section className="mb-12 surface-drawer p-5 sm:p-7">
          <MetaLabel>The setup</MetaLabel>
          <p className="ink-fainter text-[12px] leading-relaxed mt-2 italic">
            Illustrative practice scenario · uses educational sample data ·
            not live market guidance.
          </p>
          <dl className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3 text-[15px]">
            <div>
              <dt className="ink-fainter text-meta mb-1">Symbol</dt>
              <dd className="font-mono ink-primary">{rec.symbol}</dd>
            </div>
            <div>
              <dt className="ink-fainter text-meta mb-1">Direction</dt>
              <dd className="ink-primary capitalize">
                {(rec.side ?? '—').replace('-', ' ')}
              </dd>
            </div>
            <div>
              <dt className="ink-fainter text-meta mb-1">Entry</dt>
              <dd className="ink-primary">{rec.entry}</dd>
            </div>
            <div>
              <dt className="ink-fainter text-meta mb-1">Suggested sizing</dt>
              <dd className="ink-primary">{rec.sizing}</dd>
            </div>
          </dl>
          <div className="mt-5 pt-4 border-t border-hairline">
            <dt className="ink-fainter text-meta mb-2">Thesis</dt>
            <p className="ink-muted leading-relaxed text-[15px] max-w-narrative">
              <ParagraphWithTerms text={rec.paragraph} />
            </p>
          </div>
          {rec.invalidate && rec.invalidate !== '—' && (
            <div className="mt-4 pt-4 border-t border-hairline">
              <dt className="ink-fainter text-meta mb-1">Invalid if</dt>
              <p className="ink-muted leading-relaxed text-[14px] max-w-narrative">
                {rec.invalidate}
              </p>
            </div>
          )}
        </section>
      </FadeIn>

      {!existing && (
        <>
          <FadeIn delay={0.2}>
            <section className="mb-12">
              <MetaLabel>You can adjust</MetaLabel>
              <div className="mt-4 space-y-5">
                <KnobRow
                  label="Size"
                  presets={SIZE_PRESETS.map((p) => p.label)}
                  activeIdx={sizeIdx}
                  onChange={setSizeIdx}
                />
                <KnobRow
                  label="Hold for"
                  presets={HOLD_PRESETS.map((p) => p.label)}
                  activeIdx={holdIdx}
                  onChange={setHoldIdx}
                />
                <KnobRow
                  label="Stop at"
                  presets={STOP_PRESETS.map((p) => p.label)}
                  activeIdx={stopIdx}
                  onChange={setStopIdx}
                />
              </div>
              <p className="ink-fainter text-[12px] leading-relaxed mt-4 max-w-narrative">
                Suggested quantity: {suggestedQty} ·{' '}
                ~${(suggestedQty * entryPrice * multiplier).toFixed(0)}{' '}
                of your practice account.
              </p>
            </section>
          </FadeIn>

          <FadeIn delay={0.25}>
            <section className="mb-12">
              <MetaLabel>What happens next</MetaLabel>
              <p className="ink-muted leading-relaxed text-[15px] max-w-narrative mt-3">
                We mark this position daily. When the thesis resolves —
                stop hit, target reached, or you close it manually — the
                outcome lands in your practice account history alongside
                this lesson. Nothing real is at stake.
              </p>
            </section>
          </FadeIn>

          <FadeIn delay={0.3}>
            <div className="flex flex-wrap items-center gap-4">
              <PillButton
                type="button"
                onClick={handleOpen}
                className="h-12 px-6 text-[14px]"
              >
                Open the paper trade →
              </PillButton>
              <Link
                to={`/learn/lesson/${lessonSlug}`}
                className="text-meta ink-fainter hover:ink-muted transition-colors"
              >
                I'm not ready — back to the lesson
              </Link>
            </div>
            {error && (
              <p
                role="alert"
                className="mt-4 ink-warm text-[13px] leading-relaxed"
              >
                {error}
              </p>
            )}
          </FadeIn>
        </>
      )}

      {existing && (
        <>
          <FadeIn delay={0.2}>
            <section className="mb-12 surface-drawer p-5 sm:p-7">
              <MetaLabel>Your position</MetaLabel>
              <dl className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-3 text-[15px]">
                <div>
                  <dt className="ink-fainter text-meta mb-1">Entry</dt>
                  <dd className="font-mono ink-primary tabular-nums">
                    ${existing.entryPrice.toFixed(2)}
                  </dd>
                </div>
                <div>
                  <dt className="ink-fainter text-meta mb-1">Current</dt>
                  <dd className="font-mono ink-primary tabular-nums">
                    ${existing.currentPrice.toFixed(2)}
                  </dd>
                </div>
                <div>
                  <dt className="ink-fainter text-meta mb-1">Quantity</dt>
                  <dd className="font-mono ink-primary tabular-nums">
                    {existing.quantity}
                  </dd>
                </div>
                <div>
                  <dt className="ink-fainter text-meta mb-1">Direction</dt>
                  <dd className="ink-primary capitalize">
                    {existing.side.replace('-', ' ')}
                  </dd>
                </div>
              </dl>
              <div className="mt-5 pt-4 border-t border-hairline flex items-center justify-between gap-3">
                <span className="text-meta ink-fainter">Unrealized</span>
                <span className="font-mono ink-primary tabular-nums">
                  {(() => {
                    const delta =
                      (existing.currentPrice - existing.entryPrice) *
                      existing.quantity *
                      existing.multiplier *
                      (existing.side === 'long' ||
                      existing.side === 'long-option'
                        ? 1
                        : -1);
                    return `${delta >= 0 ? '+' : ''}${delta.toFixed(2)}`;
                  })()}
                </span>
              </div>
            </section>
          </FadeIn>

          <FadeIn delay={0.25}>
            <section className="mb-12">
              <MetaLabel>Reflect on opening this trade</MetaLabel>
              <div className="mt-3">
                <ReflectionCapture
                  kind="paper-trade-review"
                  targetId={existing.id}
                  prompt={`Why did you size ${existing.symbol} at ${existing.quantity}? What would change your mind?`}
                />
              </div>
            </section>
          </FadeIn>

          <FadeIn delay={0.3}>
            <div className="mt-4 flex flex-wrap items-center gap-4">
              <Link
                to="/portfolio"
                className="inline-flex items-center px-5 py-3 surface-drawer rounded-full text-meta ink-muted hover:ink-primary transition-colors"
              >
                See practice account →
              </Link>
              <button
                type="button"
                onClick={() => paper.closePosition(existing.id)}
                className="text-meta ink-fainter hover:ink-muted transition-colors"
              >
                Close this position now
              </button>
            </div>
          </FadeIn>
        </>
      )}

      {closedFromLesson.length > 0 && (
        <FadeIn delay={0.4}>
          <section className="mt-16 pt-10 border-t border-hairline">
            <MetaLabel>Past trades from this lesson</MetaLabel>
            <ul className="mt-4 space-y-px bg-hairline">
              {closedFromLesson.map((h) => (
                <li
                  key={h.id}
                  className="surface-drawer p-4 flex items-center justify-between gap-4"
                >
                  <div className="flex items-baseline gap-2">
                    <Check className="size-3.5 ink-muted" aria-hidden />
                    <span className="font-mono ink-primary tabular-nums">
                      {h.symbol}
                    </span>
                    <span className="text-meta ink-fainter">
                      · {h.daysHeld}d held
                    </span>
                  </div>
                  <span className="font-mono ink-primary tabular-nums text-[14px]">
                    {h.pnl >= 0 ? '+' : ''}
                    {h.pnl.toFixed(2)} ({h.pnlPct >= 0 ? '+' : ''}
                    {h.pnlPct.toFixed(1)}%)
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </FadeIn>
      )}
    </ArthosPage>
  );
}

function KnobRow({
  label,
  presets,
  activeIdx,
  onChange,
}: {
  label: string;
  presets: string[];
  activeIdx: number;
  onChange: (i: number) => void;
}) {
  return (
    <div>
      <div className="text-meta ink-fainter mb-2">{label}</div>
      <div className="flex flex-wrap gap-2">
        {presets.map((p, i) => {
          const active = i === activeIdx;
          return (
            <button
              key={p}
              type="button"
              onClick={() => onChange(i)}
              aria-pressed={active}
              className="inline-flex items-center px-4 py-2 rounded-full text-meta font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2"
              style={{
                backgroundColor: active
                  ? 'var(--brand)'
                  : 'var(--sage-light)',
                color: active
                  ? 'var(--brand-foreground)'
                  : 'var(--muted-foreground)',
                ['--tw-ring-color' as string]: 'var(--ring)',
              }}
            >
              {p}
            </button>
          );
        })}
      </div>
    </div>
  );
}
