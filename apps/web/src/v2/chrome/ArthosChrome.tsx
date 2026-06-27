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

import { useEffect, useState, type ReactNode, type ComponentType } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Sun,
  Moon,
  Search,
  BookOpen,
  Compass,
  Sparkles,
  User,
  LogOut,
  Shield,
  type LucideProps,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { getTerm } from '../data/arthosData';
import { useTheme } from './ThemeContext';
import { GlobalTicker } from './GlobalTicker';
import { useCommandPalette } from './CommandPalette';
import { useSession } from '../state/SessionContext';
import { apiGet } from '../../lib/api';

// Owner-only nav gate. Probes GET /api/admin/overview using the same query
// key AdminGuard uses, so this dedupes with the admin pages' own fetch. The
// SERVER is the real enforcer — require_owner returns 404 for anyone but the
// owner, so a non-owner's probe errors and the Admin link stays hidden. This
// is purely cosmetic visibility; it never grants access. retry:false avoids
// re-hammering the endpoint on the expected 404 for non-owners.
function useIsOwner(): boolean {
  const { isSuccess } = useQuery({
    queryKey: ['admin', 'overview'],
    queryFn: () => apiGet('/admin/overview'),
    retry: false,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
  return isSuccess;
}

// Phase B visual-parity — nav item shape now carries an icon ref so
// the new SideNav + restyled MobileBottomTab can render icon+label
// rows matching Lovable. Labels follow the UX-Phase-2 vocabulary
// (Trade Ideas, Practice Account, etc.).
type IconComp = ComponentType<LucideProps>;

interface NavItem {
  label: string;
  shortLabel?: string;
  to: string;
  icon: IconComp;
  match: (path: string) => boolean;
}

// ──────────────────────────────────────────────────────────────
// BrandMark — small "A" tile in brand color. Used in SideNav + mobile
// TopBar so the AI Investing Copilot identity is permanently visible.
// ──────────────────────────────────────────────────────────────
function BrandMark({ size = 'md' }: { size?: 'sm' | 'md' }) {
  const px = size === 'sm' ? 28 : 32;
  const fs = size === 'sm' ? 15 : 18;
  return (
    <span
      className="rounded-md font-serif italic flex items-center justify-center leading-none"
      style={{
        width: px,
        height: px,
        fontSize: fs,
        backgroundColor: 'var(--brand)',
        color: 'var(--brand-foreground)',
        paddingTop: '2px',
        fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
      }}
      aria-hidden
    >
      A
    </span>
  );
}

// ──────────────────────────────────────────────────────────────
// AccountTile (M2) — session-aware footer control in the SideNav.
// Logged out → "Sign in" link. Logged in → email + log-out button.
// ──────────────────────────────────────────────────────────────
function AccountTile() {
  const { user, authenticated, signOut } = useSession();
  const navigate = useNavigate();

  if (!authenticated || !user) {
    return (
      <Link
        to="/account"
        className="flex items-center gap-2.5 px-2 -ml-1 py-1 rounded-md"
        aria-label="Sign in"
      >
        <div
          className="rounded-full flex items-center justify-center"
          style={{
            width: 32, height: 32,
            backgroundColor: 'color-mix(in oklch, var(--brand) 15%, transparent)',
            color: 'var(--brand)',
          }}
        >
          <User className="w-4 h-4" strokeWidth={1.7} aria-hidden />
        </div>
        <div className="leading-tight">
          <p className="font-semibold ink-primary" style={{ fontSize: 12.5 }}>Sign in</p>
          <p style={{ fontSize: 10.5, color: 'var(--muted-foreground)' }}>Save your portfolio</p>
        </div>
      </Link>
    );
  }

  const label = user.email ?? user.display_name ?? 'You';
  const initial = (label.trim()[0] ?? 'U').toUpperCase();
  return (
    <div className="flex items-center gap-1 min-w-0">
      <Link
        to="/account"
        className="flex items-center gap-2.5 px-2 -ml-1 py-1 rounded-md min-w-0"
        aria-label="Your account"
      >
        <div
          className="rounded-full font-serif italic flex items-center justify-center"
          style={{
            width: 32, height: 32, fontSize: 14,
            backgroundColor: 'color-mix(in oklch, var(--brand) 15%, transparent)',
            color: 'var(--brand)',
            fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
          }}
        >
          {initial}
        </div>
        <div className="leading-tight min-w-0">
          <p className="font-semibold ink-primary truncate" style={{ fontSize: 12.5, maxWidth: 120 }}>
            {label}
          </p>
          <p style={{ fontSize: 10.5, color: 'var(--muted-foreground)' }}>Signed in</p>
        </div>
      </Link>
      <button
        onClick={async () => { await signOut(); navigate('/discover'); }}
        aria-label="Log out"
        className="p-1.5 rounded-md transition-colors"
        style={{ color: 'var(--muted-foreground)' }}
      >
        <LogOut className="w-3.5 h-3.5" strokeWidth={1.6} aria-hidden />
      </button>
    </div>
  );
}

// AccountTopBarButton (M2) — compact account entry in the sticky TopBar so
// mobile (no SideNav) users can reach sign in / their account.
function AccountTopBarButton() {
  const { user, authenticated } = useSession();
  const label = authenticated && user ? (user.email ?? 'Account') : 'Sign in';
  const initial = authenticated && user ? ((user.email ?? user.display_name ?? 'U').trim()[0] ?? 'U').toUpperCase() : null;
  return (
    <Link
      to="/account"
      aria-label={authenticated ? 'Your account' : 'Sign in'}
      className="inline-flex items-center gap-1.5 ink-muted hover:ink-primary transition-colors p-1.5"
    >
      {initial ? (
        <span
          className="rounded-full font-serif italic flex items-center justify-center"
          style={{
            width: 24, height: 24, fontSize: 12,
            backgroundColor: 'color-mix(in oklch, var(--brand) 15%, transparent)',
            color: 'var(--brand)',
            fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
          }}
        >
          {initial}
        </span>
      ) : (
        <User className="w-4 h-4" strokeWidth={1.5} aria-hidden />
      )}
      <span className="hidden sm:inline font-medium" style={{ fontSize: 12 }}>{label}</span>
    </Link>
  );
}

// ──────────────────────────────────────────────────────────────
// SideNav — fixed 248px desktop nav. Phase B visual-parity primitive.
// Brand mark + wordmark + "AI Investing Copilot" subtitle + 6
// icon+label rows + user-tile + theme toggle at the bottom.
// ──────────────────────────────────────────────────────────────
export function SideNav() {
  const location = useLocation();
  const { theme, toggle } = useTheme();
  const isOwner = useIsOwner();
  return (
    <aside
      className="hidden lg:flex fixed inset-y-0 left-0 z-40 w-[248px] flex-col backdrop-blur-xl"
      style={{
        backgroundColor:
          'color-mix(in oklch, var(--surface) 80%, transparent)',
        borderRight: '1px solid var(--border)',
      }}
    >
      <Link
        to="/learn"
        className="flex items-center gap-2.5 px-6 h-16 border-b"
        style={{ borderColor: 'var(--border)' }}
      >
        <BrandMark />
        <span className="flex flex-col leading-none">
          <span
            className="font-display ink-primary"
            style={{
              fontSize: 19,
              letterSpacing: '-0.01em',
              fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
            }}
          >
            ArthOS
          </span>
          <span
            className="font-semibold uppercase mt-0.5"
            style={{
              fontSize: 9,
              letterSpacing: '0.18em',
              color: 'var(--muted-foreground)',
            }}
          >
            AI Investing Copilot
          </span>
        </span>
      </Link>

      <nav className="flex-1 px-3 py-5 space-y-0.5">
        <p
          className="px-3 mb-2 font-semibold uppercase"
          style={{
            fontSize: 10,
            letterSpacing: '0.16em',
            color: 'var(--muted-foreground)',
          }}
        >
          Workspace
        </p>
        {NAV_PRIMARY.map(({ to, label, icon: Icon, match }) => {
          const active = match(location.pathname);
          return (
            <Link
              key={to}
              to={to}
              className="flex items-center gap-3 px-3 h-10 rounded-lg font-medium transition-colors"
              style={{
                fontSize: 13.5,
                backgroundColor: active ? 'var(--sage-light)' : 'transparent',
                color: active
                  ? 'var(--foreground)'
                  : 'var(--muted-foreground)',
              }}
              onMouseEnter={(e) => {
                if (!active) {
                  e.currentTarget.style.backgroundColor =
                    'color-mix(in oklch, var(--sage-light) 60%, transparent)';
                  e.currentTarget.style.color = 'var(--foreground)';
                }
              }}
              onMouseLeave={(e) => {
                if (!active) {
                  e.currentTarget.style.backgroundColor = 'transparent';
                  e.currentTarget.style.color = 'var(--muted-foreground)';
                }
              }}
            >
              <Icon
                style={{
                  width: 17,
                  height: 17,
                  color: active ? 'var(--brand)' : 'var(--muted-foreground)',
                }}
                strokeWidth={active ? 2.1 : 1.7}
                aria-hidden
              />
              <span>{label}</span>
            </Link>
          );
        })}

        {/* Owner-only — Admin console. Rendered only when the server's
            /api/admin/overview probe succeeds (owner). Server-guarded;
            non-owners never see this and cannot reach the pages. */}
        {isOwner && (() => {
          const active = location.pathname.startsWith('/admin');
          return (
            <Link
              to="/admin"
              className="flex items-center gap-3 px-3 h-10 rounded-lg font-medium transition-colors"
              style={{
                fontSize: 13.5,
                backgroundColor: active ? 'var(--sage-light)' : 'transparent',
                color: active ? 'var(--foreground)' : 'var(--muted-foreground)',
              }}
              onMouseEnter={(e) => {
                if (!active) {
                  e.currentTarget.style.backgroundColor =
                    'color-mix(in oklch, var(--sage-light) 60%, transparent)';
                  e.currentTarget.style.color = 'var(--foreground)';
                }
              }}
              onMouseLeave={(e) => {
                if (!active) {
                  e.currentTarget.style.backgroundColor = 'transparent';
                  e.currentTarget.style.color = 'var(--muted-foreground)';
                }
              }}
            >
              <Shield
                style={{
                  width: 17,
                  height: 17,
                  color: active ? 'var(--brand)' : 'var(--muted-foreground)',
                }}
                strokeWidth={active ? 2.1 : 1.7}
                aria-hidden
              />
              <span>Admin</span>
            </Link>
          );
        })()}

        {/* Secondary destinations — previously only in the mobile
            drawer, leaving them unreachable on desktop. Surfaced here
            as a quiet group so Notes/Watchlist/Methodology/System are
            clickable on the desktop SideNav too. */}
        <div className="mt-6 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
          {NAV_SECONDARY.length > 0 && (
            <p
              className="px-3 mb-2 font-semibold uppercase"
              style={{
                fontSize: 10,
                letterSpacing: '0.16em',
                color: 'var(--muted-foreground)',
              }}
            >
              More
            </p>
          )}
          {NAV_SECONDARY.map(({ to, label }) => {
            const active = location.pathname.startsWith(to);
            return (
              <Link
                key={to}
                to={to}
                className="flex items-center px-3 h-9 rounded-lg font-medium transition-colors"
                style={{
                  fontSize: 13,
                  backgroundColor: active ? 'var(--sage-light)' : 'transparent',
                  color: active ? 'var(--foreground)' : 'var(--muted-foreground)',
                }}
                onMouseEnter={(e) => {
                  if (!active) {
                    e.currentTarget.style.backgroundColor =
                      'color-mix(in oklch, var(--sage-light) 60%, transparent)';
                    e.currentTarget.style.color = 'var(--foreground)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!active) {
                    e.currentTarget.style.backgroundColor = 'transparent';
                    e.currentTarget.style.color = 'var(--muted-foreground)';
                  }
                }}
              >
                {label}
              </Link>
            );
          })}
          {NAV_ENGINE_ROOM.length > 0 && (
            <>
              <p
                className="px-3 pt-4 pb-1 font-semibold uppercase tracking-[0.14em]"
                style={{ fontSize: 10.5, color: 'var(--muted-foreground)' }}
              >
                Engine room
              </p>
              {NAV_ENGINE_ROOM.map(({ to, label }) => {
                const active = location.pathname.startsWith(to);
                return (
                  <Link
                    key={to}
                    to={to}
                    className="flex items-center px-3 h-9 rounded-lg font-medium transition-colors"
                    style={{
                      fontSize: 13,
                      backgroundColor: active ? 'var(--sage-light)' : 'transparent',
                      color: active ? 'var(--foreground)' : 'var(--muted-foreground)',
                    }}
                  >
                    {label}
                  </Link>
                );
              })}
            </>
          )}
        </div>
      </nav>

      <div
        className="px-3 py-4 flex items-center justify-between"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        <AccountTile />
        <button
          onClick={toggle}
          aria-label={theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
          className="p-2 rounded-md transition-colors"
          style={{ color: 'var(--muted-foreground)' }}
        >
          {theme === 'dark' ? (
            <Sun className="w-4 h-4" strokeWidth={1.5} />
          ) : (
            <Moon className="w-4 h-4" strokeWidth={1.5} />
          )}
        </button>
      </div>
    </aside>
  );
}

// ──────────────────────────────────────────────────────────────
// Top bar — sticky chrome (mobile shows brand tile + wordmark +
// subtitle; desktop shows category eyebrow only since SideNav
// already carries identity). Optional progress prop reserved for
// future lesson-progress integration.
// ──────────────────────────────────────────────────────────────
export function TopBar({
  progress,
  eyebrow = 'ArthOS',
}: {
  progress?: number;
  eyebrow?: string;
}) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { theme, toggle } = useTheme();
  const { open: openPalette } = useCommandPalette();

  return (
    <>
      <header
        className="sticky top-0 z-30 backdrop-blur-md"
        style={{
          backgroundColor:
            'color-mix(in oklch, var(--surface) 85%, transparent)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <div className="mx-auto w-full max-w-screen-md lg:max-w-[1080px] px-5 lg:px-10 h-14 lg:h-16 flex items-center justify-between gap-4">
          {/* Mobile-only brand block (desktop handled by SideNav). */}
          <Link to="/learn" className="flex items-center gap-2 lg:hidden">
            <BrandMark size="sm" />
            <span className="flex flex-col leading-none">
              <span
                className="font-display ink-primary"
                style={{
                  fontSize: 17,
                  letterSpacing: '-0.01em',
                  fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
                }}
              >
                ArthOS
              </span>
              <span
                className="font-semibold uppercase mt-0.5"
                style={{
                  fontSize: 9,
                  letterSpacing: '0.18em',
                  color: 'var(--muted-foreground)',
                }}
              >
                AI Investing Copilot
              </span>
            </span>
          </Link>

          {/* Desktop-only eyebrow inside TopBar */}
          <span
            className="hidden lg:block font-semibold uppercase"
            style={{
              fontSize: 11,
              letterSpacing: '0.18em',
              color: 'var(--muted-foreground)',
            }}
          >
            {eyebrow}
          </span>

          <div className="flex items-center gap-3">
            {typeof progress === 'number' && (
              <div className="flex items-center gap-2">
                <div
                  className="h-1 w-20 sm:w-28 rounded-full overflow-hidden"
                  style={{ backgroundColor: 'var(--sage-light)' }}
                >
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{
                      width: `${Math.max(0, Math.min(100, progress))}%`,
                      backgroundColor: 'var(--brand)',
                    }}
                  />
                </div>
                <span
                  className="font-mono ink-muted tabular-nums"
                  style={{ fontSize: 10 }}
                >
                  {Math.round(progress)}%
                </span>
              </div>
            )}
            <AccountTopBarButton />
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
              className="ink-muted hover:ink-primary transition-colors p-2 lg:hidden"
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
              className="ink-muted hover:ink-primary text-[18px] transition-colors px-2 py-2 lg:hidden"
            >
              ≡
            </button>
          </div>
        </div>
      </header>

      <NavDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </>
  );
}

// ──────────────────────────────────────────────────────────────
// Phase B — primary nav (SideNav + drawer + mobile bottom tab)
// ──────────────────────────────────────────────────────────────
// Six primary destinations matching Lovable's approved surfaces.
// Journal is included as a slot; ArthOS has no /v2/journal route yet,
// so the slot points at /v2/reflections (the user's local Decision
// Journal in practice). Document the redirect for future migration:
// when the Journal surface lands, swap the `to` here.
// MVP "Ideas you can follow and prove" — primary nav collapsed to the
// four approved tabs: Discover · My Portfolio · Learn · Me. Today,
// Opportunities and Catalysts now fold into the single Discover feed;
// the old routes remain reachable but carry no nav slot.
const NAV_PRIMARY: NavItem[] = [
  {
    label: 'Discover',
    to: '/discover',
    icon: Sparkles,
    match: (p) =>
      p === '/' ||
      p.startsWith('/discover') ||
      p.startsWith('/opportunities') ||
      p.startsWith('/today') ||
      p.startsWith('/catalysts'),
  },
  {
    label: 'My Portfolio',
    shortLabel: 'Portfolio',
    to: '/portfolio',
    icon: BookOpen,
    match: (p) =>
      p.startsWith('/portfolio') ||
      p.startsWith('/try') ||
      p.startsWith('/track-record'),
  },
  {
    label: 'Learn',
    to: '/learn',
    icon: Compass,
    match: (p) =>
      p.startsWith('/learn') || p.startsWith('/methodology'),
  },
  {
    label: 'Me',
    to: '/me',
    icon: User,
    match: (p) =>
      p.startsWith('/me') ||
      p.startsWith('/journal') ||
      p.startsWith('/reflections') ||
      p.startsWith('/arth'),
  },
];

// P1.2 — beginner-facing secondary nav only. Watchlist + Notes parked
// (routes/pages unchanged, just no nav slot until they serve live data).
// P1.5E2 — Methodology removed: it lives under Learn (LearnHome links it +
// Learn nav match highlights /v2/methodology). NAV_SECONDARY is now empty;
// render sites guard on length so no empty 'More' header / divider shows.
// Explicit type keeps .map/.length valid on the empty array.
const NAV_SECONDARY: { label: string; to: string }[] = [];

// Sprint C — operator/diagnostics surfaces are REMOVED from the beginner nav
// entirely (Options Diagnostics, System). The routes still exist but are
// reachable only behind the operator gate (/advanced), never linked here.
const NAV_ENGINE_ROOM: { label: string; to: string }[] = [];

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
              {NAV_PRIMARY.map((item) => {
                const isActive = item.match(location.pathname);
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    onClick={onClose}
                    className="font-display text-[24px] ink-primary inline-flex items-baseline gap-3 w-fit"
                    style={
                      isActive
                        ? {
                            borderBottom: '2px solid var(--brand)',
                            paddingBottom: '2px',
                            color: 'var(--brand)',
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
                          backgroundColor: 'var(--brand)',
                        }}
                      />
                    )}
                    {item.label}
                  </Link>
                );
              })}

              {/* Secondary nav — quieter, in same drawer */}
              {NAV_SECONDARY.length > 0 && (
                <div className="h-px bg-hairline my-4" />
              )}
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

              {/* Sprint C — engine-room group removed from beginner mobile nav. */}
              {NAV_ENGINE_ROOM.length > 0 && (
                <>
                  <div className="text-meta ink-fainter mt-6">Engine room</div>
                  {NAV_ENGINE_ROOM.map((item) => (
                    <Link
                      key={item.to}
                      to={item.to}
                      onClick={onClose}
                      className="font-serif text-[15px] ink-fainter hover:ink-primary inline-flex items-baseline gap-2 w-fit transition-colors"
                    >
                      {item.label}
                    </Link>
                  ))}
                </>
              )}
            </nav>

            {/* P1.2A — was a hardcoded fake edition/date; truthful copy only. */}
            <div className="text-meta ink-fainter mt-12">
              Built for learning, practice, and disciplined decisions.
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

// ──────────────────────────────────────────────────────────────
// Mobile bottom tab — Phase B visual-parity rebuild.
// 5 tabs: Today · Journal · Practice · Learn · Me. Icon + label,
// top-pill active indicator, brand color on active state.
// (Opportunities accessible via drawer on mobile.)
// ──────────────────────────────────────────────────────────────
// P1.5A — all 5 primary destinations on the mobile bottom bar (the old
// Opportunities filter existed only to thin a 7-item bar).
const MOBILE_TABS: NavItem[] = NAV_PRIMARY;

export function MobileBottomTab() {
  const location = useLocation();
  return (
    <nav
      className="lg:hidden fixed bottom-0 left-0 right-0 z-30 pb-safe backdrop-blur-xl"
      style={{
        backgroundColor:
          'color-mix(in oklch, var(--surface) 92%, transparent)',
        borderTop: '1px solid var(--border)',
      }}
    >
      <div className="max-w-screen-md mx-auto px-1 grid grid-cols-4">
        {MOBILE_TABS.map(({ to, label, shortLabel, icon: Icon, match }) => {
          const active = match(location.pathname);
          const display = shortLabel ?? label;
          return (
            <Link
              key={to}
              to={to}
              aria-label={display}
              className="relative flex flex-col items-center justify-center gap-1 py-2.5 min-h-11 group"
            >
              {active && (
                <span
                  aria-hidden
                  className="absolute top-0 left-1/2 -translate-x-1/2 h-0.5 w-8 rounded-full"
                  style={{ backgroundColor: 'var(--brand)' }}
                />
              )}
              <Icon
                style={{
                  width: 18,
                  height: 18,
                  color: active ? 'var(--brand)' : 'var(--muted-foreground)',
                  transition: 'color 200ms',
                }}
                strokeWidth={active ? 2 : 1.6}
                aria-hidden
              />
              <span
                className="font-semibold"
                style={{
                  fontSize: 10,
                  letterSpacing: '0.04em',
                  color: active ? 'var(--brand)' : 'var(--muted-foreground)',
                  transition: 'color 200ms',
                }}
              >
                {display}
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

// ──────────────────────────────────────────────────────────────
// Page shell — Phase B visual-parity rebuild.
// Layout: fixed SideNav (desktop) + lg:pl-[248px] body offset +
// TopBar (sticky) + main content + MobileBottomTab (mobile only).
// maxWidth prop kept for backward-compat but ignored — the canonical
// Lovable layout caps at max-w-screen-md (mobile) / max-w-[1080px]
// (desktop).
// ──────────────────────────────────────────────────────────────
export function ArthosPage({
  children,
  maxWidth,
  topBarProgress,
  topBarEyebrow,
}: {
  children: ReactNode;
  maxWidth?: string;
  topBarProgress?: number;
  topBarEyebrow?: string;
}) {
  // maxWidth retained as opt-in override per page; default falls back
  // to Lovable canonical widths.
  const widthClass = maxWidth ?? 'max-w-screen-md lg:max-w-[1080px]';
  return (
    <div className="v2-has-rail min-h-screen surface-base ink-primary">
      <SideNav />
      <div className="lg:pl-[248px]">
        {/* Sprint D — the operator market-cockpit rail (P&L / Regime / Engine /
            health ticker) is removed from beginner mode. "What's moving today"
            now lives as a plain-English section inside Discover instead. */}
        <TopBar progress={topBarProgress} eyebrow={topBarEyebrow} />
        {/* Global running market tape — visible near the top on every main page. */}
        <GlobalTicker />
        <main
          className={`mx-auto w-full ${widthClass} px-5 lg:px-10 pt-6 lg:pt-10 pb-32 lg:pb-16`}
        >
          {children}
        </main>
      </div>
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
