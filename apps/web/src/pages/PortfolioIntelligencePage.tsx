// PortfolioIntelligencePage — snapshot + positions + health rail.

import { useEffect, useState } from "react";

import PortfolioSnapshot from "@/components/portfolio/PortfolioSnapshot";
import PositionsTable from "@/components/portfolio/PositionsTable";
import HealthRail from "@/components/portfolio/HealthRail";
import { fetchPicks, type Pick } from "@/lib/picks/api";
import { buildBriefing } from "@/lib/picks/copilot";
import { PAPER_ONLY_NOTE } from "@/lib/ui/disclaimers";


export default function PortfolioIntelligencePage() {
  const [picks, setPicks] = useState<Pick[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetchPicks(30).then(rows => { if (!cancelled) setPicks(rows); });
    return () => { cancelled = true; };
  }, []);

  const briefing = buildBriefing(picks);
  const watchlistCount = picks.filter(p => (p.adjusted_action ?? p.action) === "hold").length;
  const riskCount = picks.filter(p =>
    p.stale_data || !p.enough_data || (p.adjusted_action ?? p.action) === "sell"
  ).length;
  const staleCount = picks.filter(p => p.stale_data).length;

  return (
    <div className="picks-root" data-test="portfolio-intel-page" data-density="cozy">
      <div className="picks-frame">
        <header className="picks-header">
          <div>
            <h1 className="picks-title">Portfolio Intelligence</h1>
            <p className="picks-subtitle">
              Positions, exposure, P&L · paper portfolio
            </p>
          </div>
        </header>

        <PortfolioSnapshot />

        <div className="queue-layout">
          <div className="queue-main">
            <PositionsTable />
          </div>
          <HealthRail
            staleCount={staleCount}
            watchlistCount={watchlistCount}
            riskCount={riskCount}
            posture={briefing.postureLabel}
          />
        </div>

        <footer className="picks-disclaimer">{PAPER_ONLY_NOTE}</footer>
      </div>
    </div>
  );
}
