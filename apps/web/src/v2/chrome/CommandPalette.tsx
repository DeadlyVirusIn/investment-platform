// V2 Command Palette — ⌘K / Ctrl+K. Sprint E.1: the front door to ArthOS.
// Searches Ideas, Model Portfolios, Themes, and Lessons (ranked in that
// order). Locks body scroll + opaque blurred backdrop so nothing behind it
// is visible or interactive.

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  useRef,
  createContext,
  useContext,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, BookOpen, Sparkles, Layers, Hash } from 'lucide-react';
import { LESSONS } from '../data/arthosData';
import { useTheme } from './ThemeContext';
import { plainThesis } from '../lib/plainText';
import {
  useTodaysRecommendations,
  effectiveAction,
} from '@/lib/operator/hooks';
import { useModelPortfolios } from '@/lib/operator/modelPortfolios';

interface PaletteCtx {
  open: () => void;
  close: () => void;
  isOpen: boolean;
}

const Ctx = createContext<PaletteCtx | undefined>(undefined);

type Category = 'Ideas' | 'Model Portfolios' | 'Themes' | 'Lessons';
// Ranking order — Ideas first, Lessons last.
const CATEGORY_ORDER: Category[] = ['Ideas', 'Model Portfolios', 'Themes', 'Lessons'];

interface Result {
  id: string;
  category: Category;
  title: string;
  subtitle: string;
  to: string;
  icon: ReactNode;
}

// Themes mirror the Discover "Trending Themes" chips (plain-English entry
// points into curated portfolios).
const THEMES: { label: string; slug: string }[] = [
  { label: 'Dividend growth', slug: 'dividend-growers' },
  { label: 'Big American companies', slug: 'american-megacaps' },
  { label: 'Brands you use daily', slug: 'everyday-brands' },
  { label: 'Steady compounders', slug: 'steady-compounders' },
];

// Live + static index, built in ranking order.
function useSearchIndex(): Result[] {
  const { data: recData } = useTodaysRecommendations();
  const { data: pfData } = useModelPortfolios();
  return useMemo(() => {
    const out: Result[] = [];
    (recData?.recommendations ?? []).forEach((r) => {
      const sym = (r.symbol ?? '').toUpperCase();
      if (!sym) return;
      out.push({
        id: `idea-${sym}`,
        category: 'Ideas',
        title: `${sym} — ${effectiveAction(r) ?? 'Hold'}`,
        subtitle: plainThesis(r.thesis) ?? 'Tap to see the reasoning',
        to: `/today/pick/${sym}`,
        icon: <Sparkles className="w-3.5 h-3.5" strokeWidth={1.5} />,
      });
    });
    (pfData?.portfolios ?? []).forEach((p) => {
      out.push({
        id: `pf-${p.slug}`,
        category: 'Model Portfolios',
        title: p.name,
        subtitle: p.thesis ?? 'Follow this portfolio',
        to: `/portfolios/${p.slug}`,
        icon: <Layers className="w-3.5 h-3.5" strokeWidth={1.5} />,
      });
    });
    THEMES.forEach((t) => {
      out.push({
        id: `theme-${t.slug}`,
        category: 'Themes',
        title: t.label,
        subtitle: 'Explore this theme',
        to: `/portfolios/${t.slug}`,
        icon: <Hash className="w-3.5 h-3.5" strokeWidth={1.5} />,
      });
    });
    LESSONS.forEach((l) => {
      out.push({
        id: `lesson-${l.slug}`,
        category: 'Lessons',
        title: l.title,
        subtitle: `${l.readMinutes} min · ${l.abstract.slice(0, 70)}`,
        to: `/learn/lesson/${l.slug}`,
        icon: <BookOpen className="w-3.5 h-3.5" strokeWidth={1.5} />,
      });
    });
    return out;
  }, [recData, pfData]);
}

export function CommandPaletteProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setIsOpen((o) => !o);
      }
      if (e.key === 'Escape') setIsOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  return (
    <Ctx.Provider value={{ open, close, isOpen }}>
      {children}
      <PaletteModal isOpen={isOpen} onClose={close} />
    </Ctx.Provider>
  );
}

export function useCommandPalette() {
  const v = useContext(Ctx);
  if (!v)
    throw new Error(
      'useCommandPalette must be used within CommandPaletteProvider'
    );
  return v;
}

function PaletteModal({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const { theme } = useTheme();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const index = useSearchIndex();

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return index.slice(0, 12);
    return index
      .filter(
        (r) =>
          r.title.toLowerCase().includes(q) ||
          r.subtitle.toLowerCase().includes(q)
      )
      .slice(0, 60);
  }, [query, index]);

  // Group + flatten in ranking order (Ideas → Portfolios → Themes → Lessons).
  const grouped = useMemo(() => {
    const map = {} as Record<Category, Result[]>;
    results.forEach((r) => {
      (map[r.category] ??= []).push(r);
    });
    return map;
  }, [results]);
  const flat = useMemo(
    () => CATEGORY_ORDER.flatMap((c) => grouped[c] ?? []),
    [grouped]
  );

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
      setQuery('');
      setActiveIndex(0);
    }
  }, [isOpen]);
  useEffect(() => setActiveIndex(0), [query]);

  // Sprint E.1 — lock body scroll while open so the page behind cannot move
  // or bleed through.
  useEffect(() => {
    if (!isOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [isOpen]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((i) => Math.min(flat.length - 1, i + 1));
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((i) => Math.max(0, i - 1));
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      const r = flat[activeIndex];
      if (r) {
        navigate(r.to);
        onClose();
      }
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  };

  return (
    // Render inside a themed v2-root scope so light/dark CSS tokens resolve
    // (the palette mounts above the routed pages, outside their .v2-root).
    // display:contents → no box painted (won't overlay the app when closed),
    // but the data-theme custom properties still cascade to the fixed children.
    <div className="v2-root" data-theme={theme} style={{ display: 'contents' }}>
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Opaque, blurred backdrop — nothing behind is visible/clickable. */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            onClick={onClose}
            className="fixed inset-0 z-[100] backdrop-blur-sm"
            style={{ backgroundColor: 'rgba(8, 10, 12, 0.72)' }}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.22, ease: [0.32, 0.72, 0, 1] }}
            className="fixed left-1/2 -translate-x-1/2 top-[12vh] z-[110] w-full max-w-xl px-5"
          >
            <div className="card-elevated overflow-hidden shadow-2xl"
              style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}>
              <div className="flex items-center gap-3 px-5 py-4 border-b border-hairline">
                <Search className="w-4 h-4 ink-fainter" strokeWidth={1.5} />
                <input
                  ref={inputRef}
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={onKey}
                  placeholder="Search ideas, portfolios, themes, and lessons"
                  className="flex-1 bg-transparent ink-primary placeholder:ink-fainter outline-none text-[15px]"
                />
                <kbd className="text-[11px] ink-fainter font-mono">esc</kbd>
              </div>

              <div className="max-h-[60vh] overflow-y-auto">
                {flat.length === 0 ? (
                  <div className="p-10 text-center">
                    <p className="ink-muted italic font-serif text-[16px]">
                      No matches.
                    </p>
                    <p className="text-meta ink-fainter mt-3">
                      Search ideas, portfolios, themes, and lessons.
                    </p>
                  </div>
                ) : (
                  <PaletteResults
                    grouped={grouped}
                    flat={flat}
                    activeIndex={activeIndex}
                    onSelect={(r) => {
                      navigate(r.to);
                      onClose();
                    }}
                  />
                )}
              </div>

              <div className="flex items-center justify-between px-5 py-3 border-t border-hairline text-[11px] ink-fainter">
                <div className="flex items-center gap-4">
                  <span><kbd className="font-mono">↑↓</kbd> navigate</span>
                  <span><kbd className="font-mono">⏎</kbd> open</span>
                  <span><kbd className="font-mono">esc</kbd> close</span>
                </div>
                <span>Search ArthOS</span>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
    </div>
  );
}

function PaletteResults({
  grouped,
  flat,
  activeIndex,
  onSelect,
}: {
  grouped: Record<Category, Result[]>;
  flat: Result[];
  activeIndex: number;
  onSelect: (r: Result) => void;
}) {
  return (
    <div className="py-2">
      {CATEGORY_ORDER.filter((c) => (grouped[c] ?? []).length > 0).map((category) => (
        <div key={category} className="mb-2">
          <div className="text-meta ink-fainter px-5 py-2">{category}</div>
          {grouped[category].map((r) => {
            const isActive = flat[activeIndex]?.id === r.id;
            return (
              <button
                key={r.id}
                onClick={() => onSelect(r)}
                className={`w-full text-left px-5 py-3 flex items-start gap-3 transition-colors ${
                  isActive ? 'surface-drawer' : ''
                }`}
              >
                <span className="mt-1 ink-fainter">{r.icon}</span>
                <span className="flex-1 min-w-0">
                  <span className="block ink-primary text-[14px] truncate">{r.title}</span>
                  <span className="block ink-muted text-[12px] truncate">{r.subtitle}</span>
                </span>
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}
