// PremiumIncome — bar chart of monthly options-premium income.
// Sourced from /api/options/performance-summary `.monthly[]` if present.
// Hides itself when no data is available — never fakes numbers.

import { useEffect, useState } from "react";

import { fetchPremiumIncome, fmtCurrency, type PremiumPoint } from "@/lib/portfolio/api";


export default function PremiumIncome() {
  const [points, setPoints] = useState<PremiumPoint[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchPremiumIncome()
      .then(p => { if (!cancelled) { setPoints(p); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading || !points || points.length === 0) {
    return null;
  }

  const max = Math.max(...points.map(p => p.amount), 0);
  const total = points.reduce((s, p) => s + p.amount, 0);

  return (
    <section className="pi-premium" data-test="pi-premium">
      <header className="pi-premium-header">
        <div>
          <h3>Premium Income</h3>
          <span className="pi-premium-sub">{points.length} months · ${total.toLocaleString(undefined, { maximumFractionDigits: 0 })} total</span>
        </div>
      </header>
      <div className="pi-premium-chart">
        {points.map(p => {
          const h = max > 0 ? Math.max(4, Math.round((p.amount / max) * 100)) : 4;
          return (
            <div key={p.month} className="pi-premium-bar-wrap" title={`${p.month}: ${fmtCurrency(p.amount)}`}>
              <div className="pi-premium-bar-amount">{fmtCurrency(p.amount, { compact: true })}</div>
              <div className="pi-premium-bar" style={{ height: `${h}%` }} />
              <div className="pi-premium-bar-label">{p.month}</div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
