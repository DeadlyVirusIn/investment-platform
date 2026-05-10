// StrategiesPage — options workflows: lifecycle, premium, strategy modules.

import TradeLifecycle from "@/components/portfolio/TradeLifecycle";
import PremiumIncome from "@/components/portfolio/PremiumIncome";
import StrategyModules from "@/components/portfolio/StrategyModules";
import { PAPER_ONLY_NOTE } from "@/lib/ui/disclaimers";


export default function StrategiesPage() {
  return (
    <div className="picks-root" data-test="strategies-page" data-density="cozy">
      <div className="picks-frame">
        <header className="picks-header">
          <div>
            <h1 className="picks-title">Strategy Workflows</h1>
            <p className="picks-subtitle">
              Wheel, covered calls, cash-secured puts, LEAPS, and spreads · paper trading guidance
            </p>
          </div>
        </header>

        <TradeLifecycle />
        <PremiumIncome />
        <StrategyModules />

        <footer className="picks-disclaimer">{PAPER_ONLY_NOTE}</footer>
      </div>
    </div>
  );
}
