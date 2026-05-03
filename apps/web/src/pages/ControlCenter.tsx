// Phase UI4+ — Pixel-perfect Control Center layout.

import SystemStatusCard from "@/components/operator/SystemStatusCard";
import KeyMetricsRow from "@/components/operator/KeyMetricsRow";
import CurrentActionCard from "@/components/operator/CurrentActionCard";
import IntelligencePanel from "@/components/operator/IntelligencePanel";
import EquityDrawdownChart from "@/components/operator/EquityDrawdownChart";

export default function ControlCenter() {
  return (
    <div className="min-h-screen bg-surface">
      {/* 1400px container, px-8 py-6, vertical gap-y-6 */}
      <div className="max-w-[1400px] mx-auto px-8 py-6">
        <header className="mb-6">
          <h1 className="page-title">Control Center</h1>
        </header>

        {/* SECTION 1 — System Status (dominant) */}
        <div className="mb-6">
          <SystemStatusCard />
        </div>

        {/* SECTION 2 — Key metrics (4-column grid) */}
        <div className="mb-6">
          <KeyMetricsRow />
        </div>

        {/* SECTION 3 — Action (40%) + Chart (60%) */}
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]
                          gap-6 mb-6">
          <CurrentActionCard />
          <EquityDrawdownChart />
        </div>

        {/* SECTION 4 — System Intelligence (full width) */}
        <div className="mb-6">
          <IntelligencePanel />
        </div>
      </div>
    </div>
  );
}
