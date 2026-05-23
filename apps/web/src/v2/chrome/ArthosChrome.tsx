// V2 chrome — TopBar, slide-in NavDrawer, mobile bottom tab, page
// shell, inline glossary term, paragraph-with-terms parser.
//
// Tier-1 scope: only Learn, Briefing, Pick, Paper Book, Track Record.
// Secondary nav (Watchlist, Highlights, Archive, Journal, Digest,
// Settings, Glossary) is hidden until those pages port. Links to
// dead routes are removed so the surface never produces a 404 click.
//
// All paths are namespaced under /v2/* for coexistence with the
// existing app. TermInline still surfaces the hover popover but
// the click navigation is disabled in tier-1 because /v2/learn/term
// is not yet ported.

import { useEffect, useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Sun, Moon, Search } from 'lucide-react';
import { getTerm } from '../data/arthosData';
import { useTheme } from './ThemeContext';
import { useCommandPalette } from './CommandPalette';

// ──────────────────────────────────────────────────────────────
// Top bar — sticks on scroll
// ──────────────────────────────────────────────────────────────
export function TopBar() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { theme, toggle } = useTheme();
  const { open: openPalette } = useCommandPalette();

  return (
    <>
      <header
        className="sticky top-0 z-40 backdrop-blur-md"
        style={{ backgroundColor: 'var(--surface-translucent)' }}
      >
        <div className="border-b border-hairline">
          <div className="max-w-6xl mx-auto px-5 sm:px-8 h-14 grid grid-cols-3 items-center">
            <div />
            <Link
              to="/v2/learn"
              className="font-serif ink-primary text-center"
              style={{
                fontSize: '21px',
                letterSpacing: '0.01em',
                fontWeight: 500,
              }}
            >
              ArthOS
            </Link>
            <div className="flex justify-end items-center gap-1">
              <button
                onClick={openPalette}
                aria-label="Search"
                className="ink-muted hover:ink-primary transition-colors p-2 inline-flex items-center gap-2"
              >
                <Search className="w-4 h-4" strokeWidth={1.5} />
                <kbd className="hidden sm:inline text-[10px] ink-fainter font-mono">
                  ⌘K
                </kbd>
              </button>
              <button
                onClick={toggle}
                aria-label={
                  theme === 'dark' ? 'Switch to light' : 'Switch to dark'
                }
                className="ink-muted hover:ink-primary transition-colors p-2"
              >
                {theme === 'dark' ? (
                  <Sun className="w-4 h-4" strokeWidth={1.5} />
                ) : (
                  <Moon className="w-4 h-4" strokeWidth={1.5} />
                )}
              </button>
              <button
                onClick={() => setDrawerOpen(true)}
                aria-label="Open navigation"
                className="ink-muted hover:ink-primary text-[18px] transition-colors px-2 py-2"
              >
                ≡
              </button>
            </div>
          </div>
        </div>
      </header>

      <NavDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </>
  );
}

// ──────────────────────────────────────────────────────────────
// Tier-1 nav — only routes that exist
// ──────────────────────────────────────────────────────────────
const NAV_ITEMS = [
  { label: "Today's Briefing", to: '/v2/today' },
  { label: 'Opportunities', to: '/v2/opportunities' },
  { label: 'Catalysts', to: '/v2/catalysts' },
  { label: 'Learn', to: '/v2/learn' },
  { label: 'Paper book', to: '/v2/portfolio' },
  { label: 'Track Record', to: '/v2/track-record' },
];

const NAV_SECONDARY = [
  { label: 'Field Notes', to: '/v2/field-notes' },
  { label: 'Watchlist', to: '/v2/watchlist' },
];

function NavDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const location = useLocation();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            onClick={onClose}
            className="fixed inset-0 z-50"
            style={{ backgroundColor: 'var(--backdrop)' }}
          />
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ duration: 0.35, ease: [0.32, 0.72, 0, 1] }}
            className="fixed top-0 right-0 bottom-0 z-50 w-[320px] max-w-[88vw] surface-drawer px-8 py-8 flex flex-col"
            style={{ backgroundColor: 'var(--surface-drawer)' }}
          >
            <div className="flex justify-between items-center mb-12">
              <span
                className="font-serif ink-primary"
                style={{
                  fontSize: '22px',
                  letterSpacing: '0.01em',
                  fontWeight: 500,
                }}
              >
                ArthOS
              </span>
              <button
                onClick={onClose}
                aria-label="Close"
                className="ink-muted hover:ink-primary text-[18px]"
              >
                ×
              </button>
            </div>

            <nav className="flex flex-col gap-4 flex-1">
              {NAV_ITEMS.map((item) => {
                const isActive =
                  location.pathname === item.to ||
                  (item.to !== '/v2/learn' &&
                    location.pathname.startsWith(item.to)) ||
                  (item.to === '/v2/learn' &&
                    (location.pathname === '/v2' ||
                      location.pathname.startsWith('/v2/learn')));
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    onClick={onClose}
                    className="font-serif text-[24px] ink-primary inline-flex items-baseline gap-3 w-fit"
                    style={
                      isActive
                        ? {
                            borderBottom: '2px solid var(--ink-primary)',
                            paddingBottom: '2px',
                          }
                        : undefined
                    }
                  >
                    {isActive && (
                      <span
                        aria-hidden
                        className="inline-block rounded-full"
                        style={{
                          width: '6px',
                          height: '6px',
                          backgroundColor: 'var(--ink-primary)',
                        }}
                      />
                    )}
                    {item.label}
                  </Link>
                );
              })}

              {/* Secondary nav — quieter, in same drawer */}
              <div className="h-px bg-hairline my-4" />
              {NAV_SECONDARY.map((item) => {
                const isActive = location.pathname.startsWith(item.to);
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    onClick={onClose}
                    className="font-serif text-[16px] ink-muted hover:ink-primary inline-flex items-baseline gap-2 w-fit transition-colors"
                    style={
                      isActive
                        ? {
                            color: 'var(--ink-primary)',
                            borderBottom: '2px solid var(--ink-primary)',
                            paddingBottom: '2px',
                          }
                        : undefined
                    }
                  >
                    {isActive && (
                      <span
                        aria-hidden
                        className="inline-block rounded-full"
                        style={{
                          width: '5px',
                          height: '5px',
                          backgroundColor: 'var(--ink-primary)',
                        }}
                      />
                    )}
                    {item.label}
                  </Link>
                );
              })}
            </nav>

            <div className="text-meta ink-fainter mt-12">
              Edition #142 · Friday, May 21
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

// ──────────────────────────────────────────────────────────────
// Mobile bottom tab
// ──────────────────────────────────────────────────────────────
const MOBILE_TABS = [
  { label: 'Today', to: '/v2/today' },
  { label: 'Opps', to: '/v2/opportunities' },
  { label: 'Catalysts', to: '/v2/catalysts' },
  { label: 'Learn', to: '/v2/learn' },
];

export function MobileBottomTab() {
  const location = useLocation();
  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-30 border-t border-hairline pb-safe"
      style={{
        backgroundColor: 'var(--surface-translucent)',
        backdropFilter: 'blur(20px)',
      }}
    >
      <div className="grid grid-cols-4 px-2 py-3">
        {MOBILE_TABS.map((tab) => {
          const isActive =
            location.pathname === tab.to ||
            (tab.to !== '/v2/learn' && location.pathname.startsWith(tab.to)) ||
            (tab.to === '/v2/learn' &&
              (location.pathname === '/v2' ||
                location.pathname.startsWith('/v2/learn')));
          return (
            <Link
              key={tab.to}
              to={tab.to}
              className="flex flex-col items-center justify-center text-meta ink-muted py-1 gap-1"
            >
              {isActive && (
                <span
                  aria-hidden
                  className="block rounded-full"
                  style={{
                    width: '5px',
                    height: '5px',
                    backgroundColor: 'var(--ink-primary)',
                  }}
                />
              )}
              <span
                className={isActive ? 'ink-primary' : ''}
                style={
                  isActive
                    ? {
                        borderBottom: '2px solid var(--ink-primary)',
                        paddingBottom: '2px',
                      }
                    : undefined
                }
              >
                {tab.label}
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

// ──────────────────────────────────────────────────────────────
// Page shell — TopBar + content + MobileBottomTab
// ──────────────────────────────────────────────────────────────
export function ArthosPage({
  children,
  maxWidth = 'max-w-6xl',
}: {
  children: ReactNode;
  maxWidth?: string;
}) {
  return (
    <div className="min-h-screen surface-base ink-primary">
      <TopBar />
      <main
        className={`${maxWidth} mx-auto px-5 sm:px-8 pt-10 sm:pt-16 pb-32 md:pb-24`}
      >
        {children}
      </main>
      <MobileBottomTab />
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// Inline glossary term — hover popover only in tier-1.
// Click navigation disabled because /v2/learn/term is not ported.
// ──────────────────────────────────────────────────────────────
export function TermInline({
  slug,
  children,
}: {
  slug: string;
  children: ReactNode;
}) {
  const term = getTerm(slug);
  const [open, setOpen] = useState(false);
  if (!term) return <>{children}</>;
  return (
    <span className="relative inline">
      <span
        className="glossary-term ink-primary"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        role="note"
        aria-label={`Definition: ${term.term}`}
      >
        {children}
      </span>
      <AnimatePresence>
        {open && (
          <motion.span
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.18 }}
            className="absolute left-0 top-[1.6em] z-30 w-[280px] surface-drawer p-4 text-[13px] leading-relaxed ink-muted block"
            style={{
              backgroundColor: 'var(--surface-drawer)',
              boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
            }}
          >
            <span className="font-serif text-[15px] ink-primary italic block mb-1.5">
              {term.term}
            </span>
            <span className="block">{term.longDefinition}</span>
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  );
}

// ──────────────────────────────────────────────────────────────
// Renders a paragraph string with <term:slug>…</term> markup
// ──────────────────────────────────────────────────────────────
export function ParagraphWithTerms({ text }: { text: string }) {
  const parts: ReactNode[] = [];
  const regex = /<term:([a-z-]+)>(.*?)<\/term>/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    parts.push(
      <TermInline key={key++} slug={match[1]}>
        {match[2]}
      </TermInline>
    );
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return <>{parts}</>;
}

// ──────────────────────────────────────────────────────────────
// Small typographic helpers
// ──────────────────────────────────────────────────────────────
export function MetaLabel({ children }: { children: ReactNode }) {
  return <div className="text-meta ink-fainter">{children}</div>;
}
