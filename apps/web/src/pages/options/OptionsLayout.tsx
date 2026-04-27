// Phase 11F — Options shell layout. Sub-tabs + paper-only banner.
// Read-only. No execute / order / buy / sell controls anywhere.

import { NavLink, Outlet } from 'react-router-dom';
import OptionsPaperOnlyBanner from '@/components/options/OptionsPaperOnlyBanner';

const TABS = [
  { to: '/options/chain',         label: 'Chain' },
  { to: '/options/features',      label: 'Features' },
  { to: '/options/trades',        label: 'Paper Trades' },
  { to: '/options/risk',          label: 'Risk Dashboard' },
  { to: '/options/observatory',   label: 'Strategy Observatory' },
  { to: '/options/performance',   label: 'Paper Performance' },
  { to: '/options/diagnostics',   label: 'Diagnostics' },
  { to: '/options/replay',        label: 'Scenario Replay' },
];

export default function OptionsLayout() {
  return (
    <div className="space-y-3 p-4 text-zinc-100">
      <OptionsPaperOnlyBanner />
      <header className="flex items-baseline gap-3">
        <h1 className="text-xl font-semibold">Options (observation)</h1>
        <span className="text-xs text-zinc-500">
          Paper-trading only · simulated lifecycle
        </span>
      </header>
      <nav className="flex gap-1 border-b border-zinc-800">
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            className={({ isActive }) =>
              `px-3 py-1 text-sm ${
                isActive
                  ? 'border-b-2 border-amber-400 text-zinc-100'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`
            }
          >
            {t.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
