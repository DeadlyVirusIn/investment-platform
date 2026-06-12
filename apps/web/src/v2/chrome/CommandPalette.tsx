// V2 Command Palette — ⌘K / Ctrl+K. Tier-1 index is gated to
// lessons only; secondary surfaces (terms, concepts, briefings
// archive, closed trades) are skipped because their routes are
// not ported yet and would 404 on Enter. Picks are not indexed
// until they can be sourced from the live engine.

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
import { Search, BookOpen } from 'lucide-react';
import { LESSONS } from '../data/arthosData';

interface PaletteCtx {
  open: () => void;
  close: () => void;
  isOpen: boolean;
}

const Ctx = createContext<PaletteCtx | undefined>(undefined);

interface Result {
  id: string;
  category: 'Lessons';
  title: string;
  subtitle: string;
  to: string;
  icon: ReactNode;
}

function buildIndex(): Result[] {
  const out: Result[] = [];
  LESSONS.forEach((l) =>
    out.push({
      id: `lesson-${l.slug}`,
      category: 'Lessons',
      title: l.title,
      subtitle: `${l.readMinutes} min · ${l.abstract.slice(0, 80)}`,
      to: `/v2/learn/lesson/${l.slug}`,
      icon: <BookOpen className="w-3.5 h-3.5" strokeWidth={1.5} />,
    })
  );
  return out;
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
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const index = useMemo(buildIndex, []);
  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return index.slice(0, 12);
    return index
      .filter(
        (r) =>
          r.title.toLowerCase().includes(q) ||
          r.subtitle.toLowerCase().includes(q)
      )
      .slice(0, 50);
  }, [query, index]);
  const grouped = useMemo(() => {
    const map: Record<string, Result[]> = {};
    results.forEach((r) => {
      if (!map[r.category]) map[r.category] = [];
      map[r.category].push(r);
    });
    return map;
  }, [results]);
  const flat = useMemo(() => Object.values(grouped).flat(), [grouped]);
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
      setQuery('');
      setActiveIndex(0);
    }
  }, [isOpen]);
  useEffect(() => {
    setActiveIndex(0);
  }, [query]);
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
  };
  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            className="fixed inset-0 z-[60]"
            style={{ backgroundColor: 'var(--backdrop)' }}
          />
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.25, ease: [0.32, 0.72, 0, 1] }}
            className="fixed left-1/2 -translate-x-1/2 top-[12vh] z-[70] w-full max-w-xl px-5"
          >
            <div className="card-elevated overflow-hidden shadow-2xl">
              <div className="flex items-center gap-3 px-5 py-4 border-b border-hairline">
                <Search className="w-4 h-4 ink-fainter" strokeWidth={1.5} />
                <input
                  ref={inputRef}
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={onKey}
                  placeholder="Search lessons and picks…"
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
                      Try a ticker or a concept.
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
                  <span>
                    <kbd className="font-mono">↑↓</kbd> navigate
                  </span>
                  <span>
                    <kbd className="font-mono">⏎</kbd> open
                  </span>
                </div>
                <span>Search ArthOS</span>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

function PaletteResults({
  grouped,
  flat,
  activeIndex,
  onSelect,
}: {
  grouped: Record<string, Result[]>;
  flat: Result[];
  activeIndex: number;
  onSelect: (r: Result) => void;
}) {
  return (
    <div className="py-2">
      {Object.entries(grouped).map(([category, items]) => (
        <div key={category} className="mb-2">
          <div className="text-meta ink-fainter px-5 py-2">{category}</div>
          {items.map((r) => {
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
                  <span className="block ink-primary text-[14px] truncate">
                    {r.title}
                  </span>
                  <span className="block ink-muted text-[12px] truncate">
                    {r.subtitle}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}
