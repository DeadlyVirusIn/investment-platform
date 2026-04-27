import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from '@/components/Layout';
import Dashboard from '@/pages/Dashboard';
import Portfolio from '@/pages/Portfolio';
import PortfolioSetup from '@/pages/PortfolioSetup';
import Watchlist from '@/pages/Watchlist';
import Asset from '@/pages/Asset';
import Recommendations from '@/pages/Recommendations';
import Briefing from '@/pages/Briefing';
import Alerts from '@/pages/Alerts';
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

// Phase 11G — Options Strategy Observatory (read-only)
import OptionsStrategyObservatoryPage from '@/pages/options/OptionsStrategyObservatoryPage';
import OptionsPaperPerformancePage    from '@/pages/options/OptionsPaperPerformancePage';
import OptionsStrategyDiagnosticsPage from '@/pages/options/OptionsStrategyDiagnosticsPage';
import OptionsScenarioReplayPage      from '@/pages/options/OptionsScenarioReplayPage';

// Phase 11H — Strategy Evaluation (read-only, paper-only, deterministic)
import OptionsStrategyEvaluationPage  from '@/pages/options/OptionsStrategyEvaluationPage';

// Phase 11I — Decision Support (read-only, paper-only)
import OptionsDecisionSupportPage     from '@/pages/options/OptionsDecisionSupportPage';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route element={<Layout />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/portfolio" element={<Portfolio />} />
        <Route path="/portfolio/setup" element={<PortfolioSetup />} />
        <Route path="/watchlist" element={<Watchlist />} />
        <Route path="/asset/:symbol" element={<Asset />} />
        <Route path="/recommendations" element={<Recommendations />} />
        <Route path="/briefing" element={<Briefing />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/performance" element={<Performance />} />
        <Route path="/jobs-health" element={<JobsHealth />} />
        <Route path="/settings" element={<Settings />} />
      </Route>

      {/* Options (Phase 11F + 11G) — read-only, paper-trading only */}
      <Route path="/options" element={<OptionsLayout />}>
        <Route index            element={<Navigate to="chain" replace />} />
        <Route path="chain"     element={<OptionsChainPage />} />
        <Route path="features"  element={<OptionsFeaturesPage />} />
        <Route path="trades"    element={<OptionsPaperTradesPage />} />
        <Route path="risk"      element={<OptionsRiskDashboardPage />} />
        {/* Phase 11G — Strategy Observatory (read-only) */}
        <Route path="observatory"  element={<OptionsStrategyObservatoryPage />} />
        <Route path="performance"  element={<OptionsPaperPerformancePage />} />
        <Route path="diagnostics"  element={<OptionsStrategyDiagnosticsPage />} />
        <Route path="replay"       element={<OptionsScenarioReplayPage />} />
        {/* Phase 11H — Strategy Evaluation (read-only) */}
        <Route path="evaluation"   element={<OptionsStrategyEvaluationPage />} />
        {/* Phase 11I — Decision Support (read-only) */}
        <Route path="decision-support" element={<OptionsDecisionSupportPage />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
