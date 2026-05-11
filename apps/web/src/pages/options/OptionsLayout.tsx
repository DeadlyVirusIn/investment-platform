// Phase 11F + UX-1 Commit F — Options shell layout.
// Read-only. No execute / order / buy / sell controls anywhere.
//
// UX-1 Commit F: the Shadow Visibility Card was moved into the
// new OptionsOverviewPage so it appears once on the landing
// rather than persistently above every sub-page. The header was
// softened from "Options (observation)" to "Options paper
// trading", with a short reassurance caption.

import { NavLink, Outlet } from 'react-router-dom';
import OptionsPaperOnlyBanner from '@/components/options/OptionsPaperOnlyBanner';
// Phase 11L — UI-only guardrails toggle button
import GuardrailsToggleButton from '@/components/options/GuardrailsToggleButton';
// Phase 11Z — surfaces "no options data ingested" once at the top
import OptionsDataAvailabilityBanner from '@/components/options/OptionsDataAvailabilityBanner';

// "Overview" leads the tab list so a beginner who clicks into the
// section lands on a calm summary first. All other tabs preserved.
const TABS = [
  { to: '/options/overview',      label: 'Overview' },
  { to: '/options/chain',         label: 'Chain' },
  { to: '/options/features',      label: 'Features' },
  { to: '/options/trades',        label: 'Paper Trades' },
  { to: '/options/risk',          label: 'Risk Dashboard' },
  { to: '/options/observatory',   label: 'Strategy Observatory' },
  { to: '/options/performance',   label: 'Paper Performance' },
  { to: '/options/diagnostics',   label: 'Diagnostics' },
  { to: '/options/replay',        label: 'Scenario Replay' },
  { to: '/options/evaluation',    label: 'Evaluation' },
  { to: '/options/decision-support', label: 'Decision Support' },
  { to: '/options/decision-framing', label: 'Decision Framing' },
];

export default function OptionsLayout() {
  return (
    <div className="space-y-3 p-4 text-fg">
      <OptionsPaperOnlyBanner />
      <OptionsDataAvailabilityBanner />
      <header className="flex items-baseline gap-3">
        <h1 className="text-xl font-semibold">Options paper trading</h1>
        <span className="text-xs text-fg-3">
          Paper-trading guidance · simulated only · no live execution
        </span>
        <span className="ml-auto">
          <GuardrailsToggleButton />
        </span>
      </header>
      <nav className="flex gap-1 border-b border-b1 flex-wrap">
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            className={({ isActive }) =>
              `px-3 py-1 text-sm ${
                isActive
                  ? 'border-b-2 border-amber-400 text-fg'
                  : 'text-fg-3 hover:text-fg'
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
