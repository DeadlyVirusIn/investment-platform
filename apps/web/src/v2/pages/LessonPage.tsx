// V2 Lesson Page — long-form reading + inline terms + select-to-save
// highlight + connected real trade footer.

import { useEffect, useState, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArthosPage,
  MetaLabel,
  ParagraphWithTerms,
} from '../chrome/ArthosChrome';
import { getLesson, PATHS, getPosition } from '../data/arthosData';
import { useUserPrefs } from '../state/UserPrefsContext';
// Lovable port (Phase 5) — local-first reflection footer.
import { ReflectionCapture } from '../components/ReflectionCapture';
import { markLessonRead, useLessonRead } from '../lib/lesson-progress';

export function LessonPage() {
  const { slug } = useParams<{ slug: string }>();
  const lesson = slug ? getLesson(slug) : undefined;
  const { highlights, addHighlight, removeHighlight } = useUserPrefs();
  const articleRef = useRef<HTMLElement | null>(null);
  const [selection, setSelection] = useState<{
    text: string;
    rect: DOMRect | null;
  }>({ text: '', rect: null });

  useEffect(() => {
    if (!lesson) return;
    const onSelect = () => {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed) {
        setSelection({ text: '', rect: null });
        return;
      }
      const text = sel.toString().trim();
      if (text.length < 3) {
        setSelection({ text: '', rect: null });
        return;
      }
      const range = sel.getRangeAt(0);
      const article = articleRef.current;
      if (!article || !article.contains(range.commonAncestorContainer)) {
        setSelection({ text: '', rect: null });
        return;
      }
      setSelection({ text, rect: range.getBoundingClientRect() });
    };
    document.addEventListener('selectionchange', onSelect);
    return () => document.removeEventListener('selectionchange', onSelect);
  }, [lesson]);

  if (!lesson) {
    return (
      <ArthosPage maxWidth="max-w-narrative">
        <div className="py-20">
          <p className="ink-muted">No lesson by that name.</p>
          <Link to="/v2/learn" className="text-meta ink-muted mt-4 inline-block">
            Back to Learn
          </Link>
        </div>
      </ArthosPage>
    );
  }

  const path = PATHS.find((p) => p.slug === lesson.pathSlug);
  const connectedPosition = getPosition(lesson.connectedSymbol);
  const lessonHighlights = highlights.filter(
    (h) => h.lessonSlug === lesson.slug
  );

  const handleSave = () => {
    if (!selection.text) return;
    addHighlight(lesson.slug, lesson.title, selection.text);
    window.getSelection()?.removeAllRanges();
    setSelection({ text: '', rect: null });
  };

  return (
    <ArthosPage maxWidth="max-w-reading" topBarEyebrow="Learn">
      <Link
        to="/v2/learn"
        className="text-meta ink-fainter hover:ink-muted mb-8 inline-flex items-center gap-1.5 transition-colors"
      >
        <span aria-hidden>←</span> {path ? path.title : 'Learn'}
      </Link>

      <motion.header
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="mb-12"
      >
        <span
          className="inline-block px-3.5 py-1.5 rounded-full text-[11px] font-bold uppercase tracking-[0.16em] mb-5"
          style={{
            backgroundColor:
              'color-mix(in oklch, var(--brand) 14%, transparent)',
            color: 'var(--brand)',
          }}
        >
          {path ? `${path.title} · Lesson ${lesson.order}` : `Lesson ${lesson.order}`}
        </span>
        <h1 className="font-display text-4xl sm:text-5xl ink-primary leading-[1.05] mb-4 text-balance max-w-[22ch]">
          {lesson.title}
        </h1>
        <div className="text-meta ink-fainter mt-4 flex items-center gap-4">
          <span>{lesson.readMinutes} min read</span>
          <span className="ink-fainter italic">
            · select text to save a highlight
          </span>
        </div>
      </motion.header>

      <article ref={articleRef} className="prose-editorial space-y-7">
        {lesson.body.map((block, i) => {
          if (block.type === 'p') {
            return (
              <motion.p
                key={i}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.5, delay: 0.04 + i * 0.03 }}
                className="ink-primary leading-[1.7] text-[17px]"
              >
                <ParagraphWithTerms text={block.text} />
              </motion.p>
            );
          }
          if (block.type === 'pullquote') {
            return (
              <motion.blockquote
                key={i}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.5, delay: 0.04 + i * 0.03 }}
                className="font-serif italic text-[22px] leading-snug ink-warm my-12 max-w-[30ch]"
                style={{ fontVariationSettings: '"opsz" 32' }}
              >
                {block.text}
              </motion.blockquote>
            );
          }
          // Lovable port (Phase 3) — extended block types.
          if (block.type === 'h2') {
            return (
              <motion.h2
                key={i}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.5, delay: 0.04 + i * 0.03 }}
                className="font-serif ink-primary text-[24px] leading-tight mt-10 mb-1"
              >
                {block.text}
              </motion.h2>
            );
          }
          if (block.type === 'list') {
            return (
              <motion.ul
                key={i}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.5, delay: 0.04 + i * 0.03 }}
                className="ink-primary leading-[1.7] text-[17px] space-y-2 list-disc pl-5 marker:ink-fainter"
              >
                {block.items.map((item, j) => (
                  <li key={j}>
                    <ParagraphWithTerms text={item} />
                  </li>
                ))}
              </motion.ul>
            );
          }
          if (block.type === 'callout') {
            const toneRing =
              block.tone === 'caution'
                ? 'border-l-2 border-l-[var(--ink-muted)]'
                : block.tone === 'reflect'
                ? 'border-l-2 border-l-[var(--ink-fainter)]'
                : 'border-l-2 border-l-[var(--ink-primary)]';
            return (
              <motion.aside
                key={i}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.5, delay: 0.04 + i * 0.03 }}
                className={`surface-drawer pl-5 pr-5 py-4 my-4 ${toneRing}`}
              >
                <div className="text-meta ink-fainter mb-1.5">
                  {block.tone === 'caution'
                    ? 'Caution'
                    : block.tone === 'reflect'
                    ? 'Pause'
                    : 'Insight'}
                </div>
                <div className="font-serif ink-primary text-[18px] leading-snug mb-1.5">
                  {block.title}
                </div>
                <div className="ink-muted leading-relaxed text-[15px]">
                  <ParagraphWithTerms text={block.text} />
                </div>
              </motion.aside>
            );
          }
          return null;
        })}
      </article>

      <AnimatePresence>
        {selection.text && selection.rect && (
          <motion.button
            initial={{ opacity: 0, y: -4, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.95 }}
            transition={{ duration: 0.18 }}
            onClick={handleSave}
            className="fixed z-30 px-4 py-2 rounded-full text-[13.5px] font-semibold tracking-tight shadow-2xl"
            style={{
              top: Math.max(8, selection.rect.top + window.scrollY - 48),
              left: Math.max(
                8,
                Math.min(
                  window.innerWidth - 180,
                  selection.rect.left + selection.rect.width / 2 - 90
                )
              ),
              backgroundColor: 'var(--brand)',
              color: 'var(--brand-foreground)',
            }}
          >
            Save highlight
          </motion.button>
        )}
      </AnimatePresence>

      {lessonHighlights.length > 0 && (
        <motion.section
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.4 }}
          className="mt-20 pt-12 border-t border-hairline"
        >
          <MetaLabel>Your highlights from this lesson</MetaLabel>
          <ul className="mt-6 space-y-px bg-hairline">
            {lessonHighlights.map((h) => (
              <li key={h.id} className="surface-drawer p-5 group">
                <blockquote className="font-serif italic ink-primary text-[15px] leading-relaxed mb-2 max-w-narrative">
                  "{h.text}"
                </blockquote>
                <button
                  onClick={() => removeHighlight(h.id)}
                  className="text-meta ink-fainter hover:ink-muted transition-colors opacity-0 group-hover:opacity-100"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </motion.section>
      )}

      {/* Lovable port (Phase 5) — reflection block. Sits between
          highlights and the connected-trade footer; local-only. */}
      {slug && (
        <ReflectionSection slug={slug} title={lesson.title} />
      )}

      {/* UX Phase 3A — Try-this-idea CTA. Bridges Read→Reflect into
          Try→Track→Review via /v2/try/:lessonSlug. */}
      {slug && lesson.connectedSymbol && (
        <motion.section
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.47 }}
          className="mt-16 pt-10 border-t border-hairline"
        >
          <MetaLabel>Try this idea</MetaLabel>
          <p className="mt-3 ink-muted leading-relaxed text-[15px] max-w-narrative">
            This lesson connects to {lesson.connectedSymbol}. Open a
            paper trade with the thesis already filled in — nothing real
            is at stake.
          </p>
          <Link
            to={`/v2/try/${slug}`}
            className="inline-flex items-center justify-center gap-2 mt-5 h-11 px-5 rounded-full text-[13.5px] font-semibold tracking-tight transition-colors min-h-11 hover:opacity-92"
            style={{
              backgroundColor: 'var(--brand)',
              color: 'var(--brand-foreground)',
            }}
          >
            Try this idea as a paper trade →
          </Link>
        </motion.section>
      )}

      {connectedPosition && (
        <motion.section
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.5 }}
          className="mt-24 pt-12 border-t border-hairline"
        >
          <Link
            to={`/v2/today/pick/${connectedPosition.symbol}`}
            className="block surface-drawer p-8 hover:opacity-90 transition-opacity"
          >
            <div className="text-meta ink-fainter mb-3">
              This connects to a real trade
            </div>
            <div className="flex items-baseline gap-3 mb-2">
              <span className="font-mono ink-primary">
                {connectedPosition.symbol}
              </span>
              <span className="ink-muted">·</span>
              <span className="font-serif text-subhead ink-primary">
                {connectedPosition.company}
              </span>
            </div>
            <p className="ink-muted leading-relaxed">
              {connectedPosition.thesisShort} Day {connectedPosition.dayHeld}{' '}
              of holding.
            </p>
            <div className="text-meta ink-muted mt-3 inline-flex items-center gap-1.5">
              Open the position <span aria-hidden>→</span>
            </div>
          </Link>
        </motion.section>
      )}
    </ArthosPage>
  );
}

// Lovable port (Phase 5) — reflection footer with read-receipt toggle.
// Split into its own function so the read-state hook stays scoped here.
function ReflectionSection({ slug, title }: { slug: string; title: string }) {
  const isRead = useLessonRead(slug);
  return (
    <motion.section
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.45 }}
      className="mt-20 pt-12 border-t border-hairline"
    >
      <div className="flex items-baseline justify-between mb-4 gap-3">
        <MetaLabel>Reflect</MetaLabel>
        <button
          type="button"
          onClick={() => markLessonRead(slug, !isRead)}
          className="text-meta ink-fainter hover:ink-muted transition-colors"
          aria-pressed={isRead}
        >
          {isRead ? '✓ Marked read' : 'Mark lesson read'}
        </button>
      </div>
      <ReflectionCapture
        kind="lesson-capture"
        targetId={slug}
        prompt={`What in "${title}" do you want to remember in a month?`}
      />
    </motion.section>
  );
}
