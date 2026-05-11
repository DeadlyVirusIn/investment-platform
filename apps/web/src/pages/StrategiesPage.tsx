// StrategiesPage — execution framework for AI signals.

import { useEffect, useState } from "react";

import TradeLifecycle from "@/components/portfolio/TradeLifecycle";
import PremiumIncome from "@/components/portfolio/PremiumIncome";
import StrategyModules from "@/components/portfolio/StrategyModules";
import { PAPER_ONLY_NOTE } from "@/lib/ui/disclaimers";
import PageChapter from "@/components/shell/PageChapter";
import NextStepCard from "@/components/shell/NextStepCard";
import FetchError from "@/components/shell/FetchError";
import {
  fetchLifecycleTrades, fetchStrategies,
  type LifecycleTrade, type StrategyRow,
} from "@/lib/portfolio/api";


export default function StrategiesPage() {
  const [trades, setTrades] = useState<LifecycleTrade[]>([]);
  const [strategies, setStrategies] = useState<StrategyRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchLifecycleTrades(), fetchStrategies()])
      .then(([t, s]) => {
        if (cancelled) return;
        setTrades(t); setStrategies(s); setLoading(false);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e : new Error(String(e)));
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const openTrades = trades.filter(t => t.state === "open").length;
  const closedTrades = trades.filter(t => t.state === "closed").length;
  const totalPremium = trades.reduce(
    (s, t) => s + (t.premium_collected ?? 0), 0,
  );
  const connectedStrategies = strategies.length;

  // Honest NOW string only when there's something real to say
  const nowText = (() => {
    if (loading) return undefined;
    const parts: string[] = [];
    if (openTrades > 0) parts.push(`${openTrades} open trade${openTrades === 1 ? "" : "s"}`);
    if (closedTrades > 0) parts.push(`${closedTrades} closed`);
    if (totalPremium > 0) parts.push(`$${totalPremium.toLocaleString(undefined, { maximumFractionDigits: 0 })} premium collected`);
    if (connectedStrategies > 0) parts.push(`${connectedStrategies} strategy template${connectedStrategies === 1 ? "" : "s"} registered`);
    return parts.length ? parts.join(" · ") + "." : undefined;
  })();

  return (
    <div className="picks-root" data-test="strategies-page" data-density="cozy">
      <div className="picks-frame">
        <header className="picks-header">
          <div>
            <h1 className="picks-title">Strategies</h1>
            <p className="picks-subtitle">
              How a signal becomes a trade · paper trading guidance
            </p>
          </div>
        </header>

        <PageChapter pathname="/strategies" now={nowText} />

        {error && (
          <FetchError
            title="Could not load strategy lifecycle data"
            message={error.message}
            onRetry={() => window.location.reload()}
          />
        )}

        <section className="strategy-edu">
          <h3 className="strategy-edu-title">When each strategy fits</h3>
          <ul className="strategy-edu-list">
            <li><strong>Wheel</strong> — neutral-to-bullish underlying you would not mind owning. Sell CSPs, accept assignment, sell covered calls, repeat.</li>
            <li><strong>Covered calls</strong> — long stock with capped near-term upside view. Generates income, modestly reduces cost basis.</li>
            <li><strong>Cash-secured puts</strong> — interested in owning at a lower price. Get paid to potentially buy.</li>
            <li><strong>LEAPS</strong> — long-dated calls used as leveraged stock replacement on high-conviction names.</li>
            <li><strong>Spreads</strong> — defined-risk credit / debit setups when directional bias is strong but volatility is rich.</li>
          </ul>
        </section>

        <TradeLifecycle />
        <PremiumIncome />
        <StrategyModules />

        <NextStepCard
          pathname="/strategies"
          rationale={
            openTrades > 0
              ? `${openTrades} open trade${openTrades === 1 ? "" : "s"} need contract-level inspection on the Options surface.`
              : undefined
          }
        />

        <footer className="picks-disclaimer">{PAPER_ONLY_NOTE}</footer>
      </div>
    </div>
  );
}
