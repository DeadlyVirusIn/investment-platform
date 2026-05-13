// Phase 11F + UX-1 Commit F — Options shell layout.
// Read-only. No execute / order / buy / sell controls anywhere.
//
// UX-1 Commit F: the Shadow Visibility Card was moved into the
// new OptionsOverviewPage so it appears once on the landing
// rather than persistently above every sub-page. The header was
// softened from "Options (observation)" to "Options paper
// trading", with a short reassurance caption.

import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import OptionsPaperOnlyBanner from '@/components/options/OptionsPaperOnlyBanner';
// Phase 11L — UI-only guardrails toggle button
import GuardrailsToggleButton from '@/components/options/GuardrailsToggleButton';
// Phase 11Z — surfaces "no options data ingested" once at the top
import OptionsDataAvailabilityBanner from '@/components/options/OptionsDataAvailabilityBanner';

// Phase Opt-C1 Step 15 — Advanced Research Workspace nav grouping.
// 12 routes preserved verbatim. Grouped into 5 semantic sections so
// the Working view stops feeling like tab-chaos.
//
// "Overview" leads the legacy tab list so URL deep-links stay valid.
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

// Step 15 — semantic grouping. Each tab appears in exactly ONE group.
// "Overview" intentionally NOT grouped (it's the default landing).
const NAV_GROUPS: Array<{
  id: string;
  label: string;
  description: string;
  tab_paths: string[];
}> = [
  {
    id: 'strategy-lab',
    label: 'Strategy Lab',
    description: 'Inspect strategy templates, evaluation logic, and per-strategy performance.',
    tab_paths: ['/options/observatory', '/options/diagnostics', '/options/evaluation'],
  },
  {
    id: 'decision-support',
    label: 'Decision Support',
    description: 'Review individual decision contexts and engine framing per candidate.',
    tab_paths: ['/options/decision-support', '/options/decision-framing'],
  },
  {
    id: 'chain-features',
    label: 'Chain & Features',
    description: 'Raw chain data, computed features, and scenario replay for any (symbol, expiry).',
    tab_paths: ['/options/chain', '/options/features', '/options/replay'],
  },
  {
    id: 'performance',
    label: 'Performance',
    description: 'Paper trade ledger and aggregate performance across strategies.',
    tab_paths: ['/options/trades', '/options/performance'],
  },
  {
    id: 'engineering',
    label: 'Engineering',
    description: 'Pipeline diagnostics, risk dashboards, and full system truth surface.',
    tab_paths: ['/options/risk'],
  },
];

const TAB_BY_PATH: Record<string, { to: string; label: string }> =
  Object.fromEntries(TABS.map(t => [t.to, t]));

export default function OptionsLayout() {
  // Phase Opt-A — Brief / Working toggle. Default at /options/overview
  // (no ?view=working) hides the 12-tab nav so the Outlet's
  // OptionsOverviewPage (truth-first cards) is the only thing visible.
  // ?view=working OR any sub-route (chain/features/etc.) shows the
  // existing 12-tab dense nav. NO route changes; no component removal.
  const { pathname, search } = useLocation();
  const params = new URLSearchParams(search);
  const isWorking = params.get('view') === 'working';
  const isOverviewRoute =
    pathname === '/options' ||
    pathname === '/options/' ||
    pathname === '/options/overview';
  const showWorkingNav = isWorking || !isOverviewRoute;

  return (
    <div className="space-y-3 p-4 text-fg">
      <OptionsPaperOnlyBanner />
      <OptionsDataAvailabilityBanner />
      <header className="flex items-baseline gap-3">
        <h1 className="text-xl font-semibold">Options paper trading</h1>
        <span className="text-xs text-fg-3">
          Paper trading — nothing here places real orders
        </span>
        <span className="ml-auto flex items-center gap-2">
          <OptionsViewToggle isWorking={isWorking} />
          <GuardrailsToggleButton />
        </span>
      </header>

      {showWorkingNav && (
        <>
          {/* Overview link always available as a quick "back to brief" pill */}
          <nav
            className="flex gap-1 border-b border-b1 overflow-x-auto
                       flex-nowrap options-tabnav-scroll"
            aria-label="Options primary navigation"
          >
            <NavLink
              to="/options/overview"
              className={({ isActive }) =>
                `flex-shrink-0 whitespace-nowrap px-3 py-2 text-sm ${
                  isActive
                    ? 'border-b-2 border-accent text-fg'
                    : 'text-fg-3 hover:text-fg'
                }`
              }
            >
              Overview
            </NavLink>
          </nav>

          {/* Step 15 — five semantic groups, each a small labeled cluster */}
          <div
            className="opt-working-nav-groups"
            data-test="options-working-nav-groups"
          >
            {NAV_GROUPS.map((g) => (
              <section key={g.id} className="opt-working-nav-group">
                <header className="opt-working-nav-group-head">
                  <span className="opt-working-nav-group-label">{g.label}</span>
                  <span className="opt-working-nav-group-desc">
                    {g.description}
                  </span>
                </header>
                <nav
                  className="opt-working-nav-group-tabs"
                  aria-label={`${g.label} sections`}
                >
                  {g.tab_paths.map((p) => {
                    const tab = TAB_BY_PATH[p];
                    if (!tab) return null;
                    return (
                      <NavLink
                        key={tab.to}
                        to={tab.to}
                        className={({ isActive }) =>
                          `opt-working-nav-pill${isActive ? ' is-active' : ''}`
                        }
                      >
                        {tab.label}
                      </NavLink>
                    );
                  })}
                </nav>
              </section>
            ))}
          </div>
        </>
      )}

      <Outlet />
    </div>
  );
}


// Two-segment Brief / Working pill — same primitive shape as the
// /portfolio toggle so the affordance reads consistently.
function OptionsViewToggle({ isWorking }: { isWorking: boolean }) {
  return (
    <span className="opt-view-toggle" role="group"
          aria-label="Options view">
      <Link
        to="/options"
        className="opt-view-toggle-btn"
        data-active={!isWorking ? 'true' : 'false'}
        aria-current={!isWorking ? 'page' : undefined}
      >
        Brief
      </Link>
      <Link
        to="/options?view=working"
        className="opt-view-toggle-btn"
        data-active={isWorking ? 'true' : 'false'}
        aria-current={isWorking ? 'page' : undefined}
      >
        Working
      </Link>
    </span>
  );
}
