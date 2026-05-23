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
    <ArthosPage maxWidth="max-w-reading">
      <Link
        to="/v2/learn"
        className="text-meta ink-fainter hover:ink-muted mb-12 inline-flex items-center gap-1.5 transition-colors"
      >
        <span aria-hidden>←</span> {path ? path.title : 'Learn'}
      </Link>

      <motion.header
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="mb-16"
      >
        <MetaLabel>
          {path?.tier} {path && '·'} {path?.title} {path && '·'} Lesson{' '}
          {lesson.order}
        </MetaLabel>
        <h1 className="font-serif text-headline ink-primary mt-4 leading-[1.1] text-balance max-w-[22ch]">
          {lesson.title}
        </h1>
        <div className="text-meta ink-fainter mt-5 flex items-center gap-4">
          <span>{lesson.readMinutes} min read</span>
          <span className="ink-fainter italic">
            · select text to save a highlight
          </span>
        </div>
      </motion.header>

      <article ref={articleRef} className="space-y-7">
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
            className="fixed z-30 px-4 py-2 rounded-full font-serif text-[14px] shadow-2xl"
            style={{
              top: Math.max(8, selection.rect.top + window.scrollY - 48),
              left: Math.max(
                8,
                Math.min(
                  window.innerWidth - 180,
                  selection.rect.left + selection.rect.width / 2 - 90
                )
              ),
              backgroundColor: 'var(--ink-primary)',
              color: 'var(--surface-base)',
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
