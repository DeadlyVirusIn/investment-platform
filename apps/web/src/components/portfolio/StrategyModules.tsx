// StrategyModules — workflow cards for options strategies.
// Always shows the 5 canonical workflows. If backend lacks a strategy,
// the card stays useful by inviting connection (no hidden state).

import { useEffect, useMemo, useState } from "react";

import { fetchStrategies, fmtCurrency, type StrategyRow } from "@/lib/portfolio/api";


interface Workflow {
  id: string;
  name: string;
  match: (s: StrategyRow) => boolean;
  icon: string;
  blurb: string;
}


const WORKFLOWS: Workflow[] = [
  { id: "wheel", name: "Wheel Strategy", icon: "◉",
    match: s => s.name.toLowerCase().includes("wheel"),
    blurb: "Sell CSPs, get assigned, sell covered calls, repeat." },
  { id: "cc", name: "Covered Calls", icon: "◐",
    match: s => /covered\s*call/i.test(s.name),
    blurb: "Generate income on long stock by selling calls." },
  { id: "csp", name: "Cash-Secured Puts", icon: "◓",
    match: s => /(csp|cash[- ]secured|short\s*put)/i.test(s.name),
    blurb: "Get paid to potentially buy stock at a discount." },
  { id: "leap", name: "LEAPS", icon: "◑",
    match: s => /leap/i.test(s.name),
    blurb: "Long-dated calls — leveraged stock-replacement plays." },
  { id: "spread", name: "Spreads", icon: "◇",
    match: s => /spread/i.test(s.name),
    blurb: "Defined-risk credit and debit spread setups." },
];


export default function StrategyModules() {
  const [rows, setRows] = useState<StrategyRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchStrategies()
      .then(r => { if (!cancelled) { setRows(r); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const cards = useMemo(() => WORKFLOWS.map(wf => {
    const match = rows.find(wf.match);
    return { wf, data: match ?? null };
  }), [rows]);

  return (
    <section className="pi-strategies" data-test="pi-strategies">
      <header className="pi-section-header">
        <h3>Strategy Workflows</h3>
        <span className="pi-section-sub">
          {loading ? "Loading…" : `${rows.length} of 5 connected`}
        </span>
      </header>
      <div className="pi-strategies-grid">
        {cards.map(({ wf, data }) => (
          <div key={wf.id} className="pi-strategy-card" data-connected={data ? "true" : "false"}>
            <div className="pi-strategy-top">
              <span className="pi-strategy-icon" aria-hidden="true">{wf.icon}</span>
              <div>
                <h4 className="pi-strategy-name">{wf.name}</h4>
                <span className="pi-strategy-status" data-tone={data ? "good" : "muted"}>
                  {data ? "Connected" : "Not connected"}
                </span>
              </div>
            </div>
            <p className="pi-strategy-summary">{wf.blurb}</p>

            {data && (
              <div className="pi-strategy-stats">
                {data.observations_count !== undefined && (
                  <div className="pi-strategy-stat">
                    <span className="pi-strategy-stat-label">Observations</span>
                    <span className="pi-strategy-stat-value">{data.observations_count}</span>
                  </div>
                )}
                {data.qualified_count !== undefined && (
                  <div className="pi-strategy-stat">
                    <span className="pi-strategy-stat-label">Qualified</span>
                    <span className="pi-strategy-stat-value">{data.qualified_count}</span>
                  </div>
                )}
                {data.win_rate != null && (
                  <div className="pi-strategy-stat">
                    <span className="pi-strategy-stat-label">Win rate</span>
                    <span className="pi-strategy-stat-value">{(data.win_rate * 100).toFixed(0)}%</span>
                  </div>
                )}
                {data.avg_premium != null && (
                  <div className="pi-strategy-stat">
                    <span className="pi-strategy-stat-label">Avg premium</span>
                    <span className="pi-strategy-stat-value">{fmtCurrency(data.avg_premium)}</span>
                  </div>
                )}
              </div>
            )}

            {!data && (
              <p className="pi-strategy-empty">
                Track trades for this strategy to activate win rate, premium, and AI next-action.
              </p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
