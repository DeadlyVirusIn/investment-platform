// StrategyModules — option strategy cards (Covered Calls, CSPs, LEAPS, Wheel).
// Backed by /api/options/strategies. Renders only strategies returned by the API.

import { useEffect, useState } from "react";

import { fetchStrategies, fmtCurrency, type StrategyRow } from "@/lib/portfolio/api";


function iconFor(name: string): string {
  const lo = name.toLowerCase();
  if (lo.includes("covered")) return "◐";
  if (lo.includes("cash") || lo.includes("csp") || lo.includes("put")) return "◓";
  if (lo.includes("leap")) return "◑";
  if (lo.includes("wheel")) return "◉";
  if (lo.includes("swing")) return "◇";
  return "◆";
}


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

  if (loading) {
    return (
      <section className="pi-strategies" data-test="pi-strategies-loading">
        <header className="pi-strategies-header">
          <h3>Strategy Modules</h3>
          <span className="pi-strategies-sub">Loading…</span>
        </header>
      </section>
    );
  }

  if (rows.length === 0) {
    return (
      <section className="pi-strategies" data-test="pi-strategies-empty">
        <header className="pi-strategies-header">
          <h3>Strategy Modules</h3>
          <span className="pi-strategies-sub">No strategies registered</span>
        </header>
      </section>
    );
  }

  return (
    <section className="pi-strategies" data-test="pi-strategies">
      <header className="pi-strategies-header">
        <h3>Strategy Modules</h3>
        <span className="pi-strategies-sub">{rows.length} strategies · observation only</span>
      </header>
      <div className="pi-strategies-grid">
        {rows.map(r => (
          <div key={r.rule_id} className="pi-strategy-card">
            <div className="pi-strategy-top">
              <span className="pi-strategy-icon" aria-hidden="true">{iconFor(r.name)}</span>
              <h4 className="pi-strategy-name">{r.name}</h4>
            </div>
            {r.summary && <p className="pi-strategy-summary">{r.summary}</p>}
            <div className="pi-strategy-stats">
              {r.observations_count !== undefined && (
                <div className="pi-strategy-stat">
                  <span className="pi-strategy-stat-label">Observations</span>
                  <span className="pi-strategy-stat-value">{r.observations_count}</span>
                </div>
              )}
              {r.qualified_count !== undefined && (
                <div className="pi-strategy-stat">
                  <span className="pi-strategy-stat-label">Qualified</span>
                  <span className="pi-strategy-stat-value">{r.qualified_count}</span>
                </div>
              )}
              {r.win_rate !== null && r.win_rate !== undefined && (
                <div className="pi-strategy-stat">
                  <span className="pi-strategy-stat-label">Win rate</span>
                  <span className="pi-strategy-stat-value">{(r.win_rate * 100).toFixed(0)}%</span>
                </div>
              )}
              {r.avg_premium !== null && r.avg_premium !== undefined && (
                <div className="pi-strategy-stat">
                  <span className="pi-strategy-stat-label">Avg premium</span>
                  <span className="pi-strategy-stat-value">{fmtCurrency(r.avg_premium)}</span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
