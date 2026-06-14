// P1.5D1 — shared tab strip for the Practice-owned "my book" surfaces
// (Holdings, Performance). Separate routes that both highlight Practice
// in nav; this strip makes them visibly cohere. Pure navigation — no
// data, no machine vocabulary. Options is added in a later slice.

import { Link, useLocation } from 'react-router-dom';

const TABS: { label: string; to: string; match: (p: string) => boolean }[] = [
  { label: 'Holdings', to: '/v2/portfolio', match: (p) => p.startsWith('/v2/portfolio') },
  {
    label: 'Performance',
    to: '/v2/track-record',
    match: (p) => p.startsWith('/v2/track-record'),
  },
  {
    // P1.5D2a — Options book joins the Practice spine. Specific prefix
    // so it never collides with /v2/options (engine-room diagnostics).
    label: 'Options',
    to: '/v2/options/portfolio',
    match: (p) => p.startsWith('/v2/options/portfolio'),
  },
];

export function PracticeTabs() {
  const { pathname } = useLocation();
  return (
    <nav className="flex items-baseline gap-5 mb-10" aria-label="Practice sections">
      {TABS.map(({ label, to, match }) => {
        const active = match(pathname);
        return (
          <Link
            key={to}
            to={to}
            className="text-meta transition-colors"
            style={
              active
                ? {
                    color: 'var(--ink-primary)',
                    borderBottom: '2px solid var(--ink-primary)',
                    paddingBottom: '3px',
                  }
                : { color: 'var(--ink-muted)' }
            }
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
