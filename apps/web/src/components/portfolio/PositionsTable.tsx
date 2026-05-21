// PositionsTable — Position Intelligence.
// Smart empty cells per row + outcome-oriented colors.

import { useEffect, useMemo, useState } from "react";

import { fetchOpenPositions, fmtCurrency, fmtPct, fmtSigned, type PositionRow } from "@/lib/portfolio/api";


type SortKey = "symbol" | "quantity" | "avg_cost" | "market_value" | "unrealized_pnl" | "return_pct";


function strategyHint(portfolio: string | null): string {
  if (!portfolio) return "Long";
  const lo = portfolio.toLowerCase();
  if (lo.includes("wheel")) return "Wheel";
  if (lo.includes("leap")) return "LEAPS";
  if (lo.includes("call")) return "Covered call";
  if (lo.includes("put")) return "CSP";
  if (lo.includes("spread")) return "Spread";
  return "Long";
}


interface PositionState { text: string; tone: "good" | "warn" | "bad" | "info"; tooltip: string; }


// Cohesion polish: replaces the prior `nextStep()` function. The output
// was a JS conditional on `return_pct` ("Lock partial gains", "Review
// thesis") rendered as AI advice in a column titled "AI Next Step". It
// is not AI — it is a deterministic threshold on a single number. We
// keep the threshold-driven coloring (useful at a glance) but convert
// the text to observational state, not imperative advice. Same pattern
// Phase L UI-1 already enforced for PickModal rationale text.
function positionState(r: PositionRow): PositionState {
  if (r.return_pct != null) {
    if (r.return_pct >= 100) return {
      text: "Up 100% or more", tone: "warn",
      tooltip: "Unrealized return is at or above +100% based on current marked price.",
    };
    if (r.return_pct >= 25) return {
      text: "Up 25–100%", tone: "good",
      tooltip: "Unrealized return is between +25% and +100% based on current marked price.",
    };
    if (r.return_pct <= -10) return {
      text: "Down 10% or more", tone: "bad",
      tooltip: "Unrealized return is at or below −10% based on current marked price.",
    };
    if (r.return_pct < 0) return {
      text: "Below cost basis", tone: "warn",
      tooltip: "Unrealized return is between 0% and −10% based on current marked price.",
    };
    return {
      text: "Near entry", tone: "good",
      tooltip: "Unrealized return is roughly flat versus cost basis.",
    };
  }
  if (r.unrealized_pnl != null) {
    if (r.unrealized_pnl > 0) return {
      text: "In profit", tone: "good",
      tooltip: "Unrealized P&L is positive versus cost basis.",
    };
    if (r.unrealized_pnl < 0) return {
      text: "Below cost basis", tone: "warn",
      tooltip: "Unrealized P&L is negative versus cost basis.",
    };
  }
  return {
    text: "Awaiting price", tone: "info",
    tooltip: "A current price is not available, so P&L cannot be computed yet.",
  };
}


export default function PositionsTable() {
  const [rows, setRows] = useState<PositionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>("unrealized_pnl");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchOpenPositions()
      .then(r => { if (!cancelled) { setRows(r); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const sorted = useMemo(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [rows, sortKey, sortDir]);

  function header(key: SortKey, label: string, align: "left" | "right" = "right") {
    const active = sortKey === key;
    const ariaSort = active
      ? (sortDir === "asc" ? "ascending" : "descending")
      : "none";

    function onActivate() {
      if (active) setSortDir(d => d === "asc" ? "desc" : "asc");
      else { setSortKey(key); setSortDir("desc"); }
    }

    return (
      <th
        data-align={align}
        data-active={active ? "true" : "false"}
        aria-sort={ariaSort}
        onClick={onActivate}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onActivate();
          }
        }}
        tabIndex={0}
        role="columnheader"
      >
        {label}{active && <span className="pi-pos-sort" aria-hidden="true">{sortDir === "asc" ? " ↑" : " ↓"}</span>}
      </th>
    );
  }

  if (loading) {
    return (
      <section className="pi-positions" data-test="pi-positions-loading">
        <header className="pi-section-header">
          <h3>Position Intelligence</h3>
          <span className="pi-section-sub">Loading…</span>
        </header>
      </section>
    );
  }

  if (rows.length === 0) {
    return (
      <section className="pi-positions" data-test="pi-positions-empty">
        <header className="pi-section-header">
          <h3>Position Intelligence</h3>
          <span className="pi-section-sub">Activate paper trading to see positions here</span>
        </header>
        <div className="pi-empty-state">
          <h4>No open positions yet</h4>
          <p>
            Once paper trades execute, your open positions appear here with
            real-time P&L, return %, premium income (where applicable), and
            AI-suggested next steps for each name.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="pi-positions" data-test="pi-positions">
      <header className="pi-section-header">
        <h3>Position Intelligence</h3>
        <span className="pi-section-sub">{rows.length} open · paper · sorted by {sortKey === "unrealized_pnl" ? "open P&L" : sortKey}</span>
      </header>
      <div className="pi-positions-tablewrap">
        <table className="pi-positions-table">
          <caption className="u-sr-only">
            Open paper-trading positions, sortable by symbol, quantity,
            average cost, market value, open P&amp;L, and return percent.
          </caption>
          <thead>
            <tr>
              {header("symbol", "Symbol", "left")}
              <th data-align="left">Strategy</th>
              {header("quantity", "Position")}
              {header("avg_cost", "Avg Cost")}
              {header("market_value", "Market Value")}
              {header("unrealized_pnl", "Unrealized P&L")}
              {header("return_pct", "Return")}
              <th data-align="left">Position state</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(r => {
              const pnlTone = r.unrealized_pnl == null ? "" : r.unrealized_pnl > 0 ? "good" : r.unrealized_pnl < 0 ? "bad" : "";
              const retTone = r.return_pct == null ? "" : r.return_pct > 100 ? "warn" : r.return_pct > 0 ? "good" : r.return_pct < 0 ? "bad" : "";
              const next = positionState(r);
              return (
                <tr key={r.position_id}>
                  <td data-align="left"><span className="pi-pos-symbol">{r.symbol}</span></td>
                  <td data-align="left">
                    <span className="pi-pos-strategy">{strategyHint(r.portfolio_name)}</span>
                  </td>
                  <td data-align="right">{r.quantity.toLocaleString()}</td>
                  <td data-align="right">
                    {r.avg_cost != null ? fmtCurrency(r.avg_cost) : <span className="pi-pos-na">—</span>}
                  </td>
                  <td data-align="right">
                    {r.market_value != null ? fmtCurrency(r.market_value) : <span className="pi-pos-na" title="Market value depends on a current price mark.">needs price mark</span>}
                  </td>
                  <td data-align="right" data-tone={pnlTone}>
                    {r.unrealized_pnl != null ? fmtSigned(r.unrealized_pnl) : <span className="pi-pos-na">—</span>}
                  </td>
                  <td data-align="right" data-tone={retTone}>
                    {r.return_pct != null ? fmtPct(r.return_pct) : <span className="pi-pos-na">—</span>}
                  </td>
                  <td data-align="left">
                    <span className="pi-pos-next" data-tone={next.tone} title={next.tooltip}>{next.text}</span>
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
