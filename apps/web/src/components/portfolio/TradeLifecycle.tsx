// TradeLifecycle — real lifecycle of paper option trades.
// Sourced from /api/options/paper-trades. Grouped by state.

import { useEffect, useMemo, useState } from "react";

import {
  fetchLifecycleTrades, fmtCurrency, fmtSigned,
  type LifecycleTrade, type LifecycleState,
} from "@/lib/portfolio/api";


const ORDER: LifecycleState[] = ["open", "pending", "rolled", "assigned", "exercised", "closed", "expired"];


function stateLabel(s: LifecycleState): string {
  switch (s) {
    case "open":      return "Open";
    case "closed":    return "Closed";
    case "assigned":  return "Assigned";
    case "expired":   return "Expired";
    case "rolled":    return "Rolled";
    case "exercised": return "Exercised";
    case "pending":   return "Pending";
  }
}


export default function TradeLifecycle() {
  const [rows, setRows] = useState<LifecycleTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeState, setActiveState] = useState<LifecycleState | "all">("all");

  useEffect(() => {
    let cancelled = false;
    fetchLifecycleTrades()
      .then(r => { if (!cancelled) { setRows(r); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const counts = useMemo(() => {
    const c: Record<LifecycleState, number> = {
      open: 0, closed: 0, assigned: 0, expired: 0,
      rolled: 0, exercised: 0, pending: 0,
    };
    rows.forEach(r => { c[r.state] += 1; });
    return c;
  }, [rows]);

  const filtered = activeState === "all"
    ? rows
    : rows.filter(r => r.state === activeState);

  if (loading) {
    return (
      <section className="tl-section" data-test="tl-loading">
        <header className="pi-section-header">
          <h3>Trade Lifecycle</h3>
          <span className="pi-section-sub">Loading…</span>
        </header>
      </section>
    );
  }

  if (rows.length === 0) {
    return (
      <section className="tl-section" data-test="tl-empty">
        <header className="pi-section-header">
          <h3>Trade Lifecycle</h3>
          <span className="pi-section-sub">Not active yet</span>
        </header>
        <div className="pi-empty-state">
          <h4>No options trades to track yet</h4>
          <p>
            Once option paper-trades execute, this section shows the full
            lifecycle of every trade — open, rolled, assigned, exercised,
            expired, or closed — with premium collected, days open, and
            realized P&L.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="tl-section" data-test="tl-section">
      <header className="pi-section-header">
        <h3>Trade Lifecycle</h3>
        <span className="pi-section-sub">{rows.length} trades · {counts.open} open · {counts.closed} closed</span>
      </header>

      <div className="tl-tabs">
        <button
          type="button"
          className="tl-tab"
          data-active={activeState === "all" ? "true" : "false"}
          onClick={() => setActiveState("all")}
        >
          <span>All</span>
          <span className="tl-tab-count">{rows.length}</span>
        </button>
        {ORDER.filter(s => counts[s] > 0).map(s => (
          <button
            key={s}
            type="button"
            className="tl-tab"
            data-active={activeState === s ? "true" : "false"}
            data-state={s}
            onClick={() => setActiveState(s)}
          >
            <span>{stateLabel(s)}</span>
            <span className="tl-tab-count">{counts[s]}</span>
          </button>
        ))}
      </div>

      <div className="tl-tablewrap">
        <table className="tl-table">
          <caption className="u-sr-only">
            Lifecycle of paper-trading option positions. Columns: state,
            underlying, contract, strategy, premium collected, realized
            P&amp;L, days held, opened date.
          </caption>
          <thead>
            <tr>
              <th data-align="left">State</th>
              <th data-align="left">Underlying</th>
              <th data-align="left">Contract</th>
              <th data-align="left">Strategy</th>
              <th data-align="right">Premium</th>
              <th data-align="right">Realized</th>
              <th data-align="right">Days</th>
              <th data-align="left">Opened</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(t => {
              const realizedTone = t.realized_pnl == null ? ""
                : t.realized_pnl > 0 ? "good"
                : t.realized_pnl < 0 ? "bad" : "";
              return (
                <tr key={t.trade_id}>
                  <td data-align="left">
                    <span className="tl-state" data-state={t.state}>{stateLabel(t.state)}</span>
                  </td>
                  <td data-align="left"><span className="tl-underlying">{t.underlying}</span></td>
                  <td data-align="left">{t.contract ?? <span className="pi-pos-na">—</span>}</td>
                  <td data-align="left">{t.strategy_name ?? <span className="pi-pos-na">—</span>}</td>
                  <td data-align="right">
                    {t.premium_collected != null ? fmtCurrency(t.premium_collected) : <span className="pi-pos-na">—</span>}
                  </td>
                  <td data-align="right" data-tone={realizedTone}>
                    {t.realized_pnl != null ? fmtSigned(t.realized_pnl) : <span className="pi-pos-na">—</span>}
                  </td>
                  <td data-align="right">{t.days_open != null ? `${t.days_open}d` : "—"}</td>
                  <td data-align="left" className="tl-opened">
                    {t.opened_at ? t.opened_at.slice(0, 10) : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
