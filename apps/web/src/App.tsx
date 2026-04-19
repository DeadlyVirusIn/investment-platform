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
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
