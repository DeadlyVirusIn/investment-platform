import { NavLink, Outlet } from 'react-router-dom';
import { cn } from '@/lib/cn';

interface NavItem {
  to: string;
  label: string;
  icon: string;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/dashboard', label: 'Dashboard', icon: '◈' },
  { to: '/portfolio', label: 'Portfolio', icon: '◎' },
  { to: '/portfolio/setup', label: 'Setup Portfolio', icon: '⊕' },
  { to: '/watchlist', label: 'Watchlist', icon: '◉' },
  { to: '/recommendations', label: 'Recommendations', icon: '◆' },
  { to: '/briefing', label: 'Briefing', icon: '◫' },
  { to: '/alerts', label: 'Alerts', icon: '◬' },
  { to: '/performance', label: 'Performance', icon: '◑' },
  { to: '/jobs-health', label: 'Jobs Health', icon: '◧' },
  { to: '/settings', label: 'Settings', icon: '◩' },
];

export default function Layout() {
  return (
    <div className="flex min-h-screen bg-surface">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 flex flex-col bg-surface-card border-r border-surface-border">
        {/* Logo / brand */}
        <div className="px-5 py-5 border-b border-surface-border">
          <span className="text-accent font-semibold tracking-tight text-base">
            InvestIQ
          </span>
          <span className="ml-1 text-text-muted text-xs">alpha</span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-3 px-2">
          {NAV_ITEMS.map(({ to, label, icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/portfolio'}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2.5 px-3 py-2 rounded-md text-sm mb-0.5 transition-colors',
                  isActive
                    ? 'bg-accent-muted text-accent font-medium'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover'
                )
              }
            >
              <span className="text-xs w-4 text-center" aria-hidden>
                {icon}
              </span>
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Footer hint */}
        <div className="px-4 py-3 border-t border-surface-border">
          <p className="text-text-muted text-xs">Personal use only</p>
        </div>
      </aside>

      {/* Main content area */}
      <main className="flex-1 overflow-y-auto p-6">
        <Outlet />
      </main>
    </div>
  );
}
