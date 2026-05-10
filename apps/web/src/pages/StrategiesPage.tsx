// StrategiesPage — options workflows: lifecycle, premium, strategy modules.

import TradeLifecycle from "@/components/portfolio/TradeLifecycle";
import PremiumIncome from "@/components/portfolio/PremiumIncome";
import StrategyModules from "@/components/portfolio/StrategyModules";
import { PAPER_ONLY_NOTE } from "@/lib/ui/disclaimers";
import PageChapter from "@/components/shell/PageChapter";
import NextStepCard from "@/components/shell/NextStepCard";


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

        <PageChapter pathname="/strategies" />

        <section className="strategy-edu">
          <h3 className="strategy-edu-title">When each strategy fits</h3>
          <ul className="strategy-edu-list">
            <li><strong>Wheel</strong> — neutral-to-bullish underlying you would not mind owning. Get paid via CSPs, accept assignment, write covered calls, repeat.</li>
            <li><strong>Covered calls</strong> — long stock with capped near-term upside view. Generates income, modestly reduces cost basis.</li>
            <li><strong>Cash-secured puts</strong> — interested in owning at a lower price. Get paid to potentially buy.</li>
            <li><strong>LEAPS</strong> — long-dated calls used as leveraged stock replacement on high-conviction names.</li>
            <li><strong>Spreads</strong> — defined-risk credit / debit setups when directional bias is strong but volatility is rich.</li>
          </ul>
        </section>

        <TradeLifecycle />
        <PremiumIncome />
        <StrategyModules />

        <NextStepCard pathname="/strategies" />

        <footer className="picks-disclaimer">{PAPER_ONLY_NOTE}</footer>
      </div>
    </div>
  );
}
