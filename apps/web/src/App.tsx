// Phase UI-RESET — clean routing over new Shell.
// Legacy pages remain reachable but not linked from nav.

import { Routes, Route, Navigate } from 'react-router-dom';
import Shell from '@/components/shell/Shell';

// NEW product pages.
// UX-5B Phase B-3 — /overview now flips through OverviewRouteSwitch:
// default → Layer-1 editorial CopilotOverview;
// ?view=working → existing Overview (Elite Terminal preserved).
import OverviewRouteSwitch from '@/pages/copilot/OverviewRouteSwitch';
// UX-2 Phase B — /portfolio brief↔working route switch wraps
// PortfolioTerminal; no longer imported directly here.
import PortfolioRouteSwitch from '@/pages/copilot/PortfolioRouteSwitch';
import Decisions from '@/pages/Decisions';
import ResearchLab from '@/pages/ResearchLab';
import AlphaLab from '@/pages/AlphaLab';
import MLLab from '@/pages/MLLab';
import Ops from '@/pages/Ops';
import RiskDashboard from '@/pages/RiskDashboard';
import AgentWorkflows from '@/pages/AgentWorkflows';

// Legacy pages (kept reachable for continuity)
import Dashboard from '@/pages/Dashboard';
import PaperPortfolio from '@/pages/PaperPortfolio';
import PaperOperator from '@/pages/PaperOperator';
import Watchlist from '@/pages/Watchlist';
import Asset from '@/pages/Asset';
import Recommendations from '@/pages/Recommendations';
import Briefing from '@/pages/Briefing';
import Alerts from '@/pages/Alerts';
import Intelligence from '@/pages/Intelligence';
import Performance from '@/pages/Performance';
import JobsHealth from '@/pages/JobsHealth';
import Settings from '@/pages/Settings';
import NotFound from '@/pages/NotFound';

// Phase 11F — Options (read-only, paper-trading only)
import OptionsLayout from '@/pages/options/OptionsLayout';
import OptionsChainPage from '@/pages/options/OptionsChainPage';
import OptionsFeaturesPage from '@/pages/options/OptionsFeaturesPage';
import OptionsPaperTradesPage from '@/pages/options/OptionsPaperTradesPage';
import OptionsRiskDashboardPage from '@/pages/options/OptionsRiskDashboardPage';
// UX-1 Commit F — Options summary-first landing page.
import OptionsOverviewPage from '@/pages/options/OptionsOverviewPage';

// Phase 11G — Options Strategy Observatory (read-only)
import OptionsStrategyObservatoryPage from '@/pages/options/OptionsStrategyObservatoryPage';
import OptionsPaperPerformancePage    from '@/pages/options/OptionsPaperPerformancePage';
import OptionsStrategyDiagnosticsPage from '@/pages/options/OptionsStrategyDiagnosticsPage';
import OptionsScenarioReplayPage      from '@/pages/options/OptionsScenarioReplayPage';

// Phase 11H — Strategy Evaluation (read-only, paper-only, deterministic)
import OptionsStrategyEvaluationPage  from '@/pages/options/OptionsStrategyEvaluationPage';

// Phase 11I — Decision Support (read-only, paper-only)
import OptionsDecisionSupportPage     from '@/pages/options/OptionsDecisionSupportPage';

// Phase 11J — Decision Framing (read-only, paper-only)
import OptionsDecisionFramingPage     from '@/pages/options/OptionsDecisionFramingPage';
// Phase 6b-3-b — new 7-surface workspace placeholders
// Phase 6b-3-d — Research shell replaced by full Research page
import OptionsResearchPage   from '@/pages/options/OptionsResearchPage';
// Phase 6b-3-e — Journal shell replaced by full Journal page
import OptionsJournalPage    from '@/pages/options/OptionsJournalPage';
// Phase 6b-3-f — Learning shell replaced by full Learning page
import OptionsLearningPage   from '@/pages/options/OptionsLearningPage';
// Phase 6b-3-g — Ops shell replaced by full Ops page
import OptionsOpsPage        from '@/pages/options/OptionsOpsPage';
// Phase 6b-3-h — Lab shell replaced by full Lab page
import OptionsLabPage        from '@/pages/options/OptionsLabPage';
import OptionsSettingsShell  from '@/pages/options/OptionsSettingsShell';

// Phase 11Q — Pending T+1 Decisions diagnostic (read-only)
import PendingT1Page                  from '@/pages/diagnostics/PendingT1';

// Phase 11A — split Investing OS pages
import ActionQueuePage                from '@/pages/ActionQueuePage';
import EventsResearchPage             from '@/pages/EventsResearchPage';
import StrategiesPage                 from '@/pages/StrategiesPage';
import SignalLabPage                  from '@/pages/SignalLabPage';
import PortfolioIntelligencePage      from '@/pages/PortfolioIntelligencePage';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/overview" replace />} />

      <Route element={<Shell />}>
        {/* --- NEW 5-area product --- */}
        <Route path="/overview"      element={<OverviewRouteSwitch />} />
        <Route path="/action-queue"  element={<ActionQueuePage />} />
        <Route path="/portfolio"     element={<PortfolioRouteSwitch />} />
        <Route path="/portfolio/intel" element={<PortfolioIntelligencePage />} />
        <Route path="/events"        element={<EventsResearchPage />} />
        <Route path="/strategies"    element={<StrategiesPage />} />
        <Route path="/signal-lab"    element={<SignalLabPage />} />
        <Route path="/decisions"  element={<Decisions />} />
        <Route path="/research"   element={<ResearchLab />} />
        <Route path="/alpha-lab"  element={<AlphaLab />} />
        <Route path="/ml-lab"     element={<MLLab />} />
        <Route path="/ops"        element={<Ops />} />
        <Route path="/risk"       element={<RiskDashboard />} />
        <Route path="/agents"     element={<AgentWorkflows />} />

        {/* --- Options (Phase 11F) — read-only, paper-trading only --- */}
        <Route path="/options" element={<OptionsLayout />}>
          {/* UX-1 Commit F — index lands on the new beginner-     */}
          {/* friendly Overview, not the dense chain table.         */}
          <Route index             element={<Navigate to="overview" replace />} />
          <Route path="overview"   element={<OptionsOverviewPage />} />
          <Route path="chain"      element={<OptionsChainPage />} />
          <Route path="features"   element={<OptionsFeaturesPage />} />
          <Route path="trades"     element={<OptionsPaperTradesPage />} />
          <Route path="risk"       element={<OptionsRiskDashboardPage />} />
          {/* Phase 11G — Strategy Observatory (read-only) */}
          <Route path="observatory"  element={<OptionsStrategyObservatoryPage />} />
          <Route path="performance"  element={<OptionsPaperPerformancePage />} />
          <Route path="diagnostics"  element={<OptionsStrategyDiagnosticsPage />} />
          <Route path="replay"       element={<OptionsScenarioReplayPage />} />
          {/* Phase 11H — Strategy Evaluation (read-only) */}
          <Route path="evaluation"   element={<OptionsStrategyEvaluationPage />} />
          {/* Phase 11I — Decision Support (read-only) */}
          <Route path="decision-support" element={<OptionsDecisionSupportPage />} />
          {/* Phase 11J — Decision Framing (read-only) */}
          <Route path="decision-framing" element={<OptionsDecisionFramingPage />} />
          {/* Phase 6b-3-b — new 7-surface workspace shells.
              All 12 legacy routes above remain reachable; these are
              ADDITIVE. Bodies land in 6b-3-{d..i}. */}
          <Route path="research" element={<OptionsResearchPage />} />
          <Route path="journal"  element={<OptionsJournalPage />} />
          <Route path="learning" element={<OptionsLearningPage />} />
          <Route path="lab"      element={<OptionsLabPage />} />
          <Route path="ops"      element={<OptionsOpsPage />} />
          <Route path="settings" element={<OptionsSettingsShell />} />
        </Route>

        {/* Phase 11Q — Pending T+1 Decisions diagnostic (read-only) */}
        <Route
          path="/diagnostics/pending-t1"
          element={<PendingT1Page />}
        />

        {/* --- Legacy deep links (not in nav) --- */}
        <Route path="/legacy/dashboard" element={<Dashboard />} />
        <Route path="/legacy/paper-portfolio" element={<PaperPortfolio />} />
        <Route path="/legacy/paper-operator" element={<PaperOperator />} />
        <Route path="/legacy/watchlist" element={<Watchlist />} />
        <Route path="/legacy/recommendations" element={<Recommendations />} />
        <Route path="/legacy/briefing" element={<Briefing />} />
        <Route path="/legacy/alerts" element={<Alerts />} />
        <Route path="/legacy/performance" element={<Performance />} />
        <Route path="/legacy/intelligence" element={<Intelligence />} />
        <Route path="/legacy/jobs-health" element={<JobsHealth />} />
        <Route path="/legacy/settings" element={<Settings />} />
        <Route path="/legacy/asset/:symbol" element={<Asset />} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
