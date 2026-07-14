// P1.5B — shared tab strip for the Me-owned surfaces (Profile, Journal,
// Report Card). These stayed separate routes after the P1.5A nav
// collapse; this strip makes it visible that they belong together under
// Me. Pure navigation — no data, no machine vocabulary.

import { Link, useLocation } from 'react-router-dom';

const TABS: { label: string; to: string; match: (p: string) => boolean }[] = [
  { label: 'Profile', to: '/me', match: (p) => p.startsWith('/me') },
  {
    label: 'Journal',
    to: '/journal',
    match: (p) => p.startsWith('/journal') || p.startsWith('/reflections'),
  },
  { label: 'Report Card', to: '/arth', match: (p) => p.startsWith('/arth') },
];

export function MeTabs() {
  const { pathname } = useLocation();
  return (
    <nav className="flex items-baseline gap-5 mb-10" aria-label="Me sections">
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
