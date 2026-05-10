// PositionsTable — modern position intelligence table.
// Sourced from /api/paper/executed/positions. Shows real fields only.

import { useEffect, useMemo, useState } from "react";

import { fetchOpenPositions, fmtCurrency, fmtPct, fmtSigned, type PositionRow } from "@/lib/portfolio/api";


type SortKey = "symbol" | "quantity" | "avg_cost" | "market_value" | "unrealized_pnl" | "return_pct";


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
    return (
      <th
        data-align={align}
        data-active={active ? "true" : "false"}
        onClick={() => {
          if (active) setSortDir(d => d === "asc" ? "desc" : "asc");
          else { setSortKey(key); setSortDir("desc"); }
        }}
      >
        {label}{active && <span className="pi-pos-sort">{sortDir === "asc" ? " ↑" : " ↓"}</span>}
      </th>
    );
  }

  if (loading) {
    return (
      <section className="pi-positions" data-test="pi-positions-loading">
        <header className="pi-positions-header">
          <h3>Position Intelligence</h3>
          <span className="pi-positions-sub">Loading…</span>
        </header>
      </section>
    );
  }

  if (rows.length === 0) {
    return (
      <section className="pi-positions" data-test="pi-positions-empty">
        <header className="pi-positions-header">
          <h3>Position Intelligence</h3>
          <span className="pi-positions-sub">No open positions yet</span>
        </header>
        <div className="pi-positions-empty">
          Once paper trades execute, your open positions will appear here with live P&L,
          return %, and AI-suggested next actions.
        </div>
      </section>
    );
  }

  return (
    <section className="pi-positions" data-test="pi-positions">
      <header className="pi-positions-header">
        <h3>Position Intelligence</h3>
        <span className="pi-positions-sub">{rows.length} open · paper</span>
      </header>
      <div className="pi-positions-tablewrap">
        <table className="pi-positions-table">
          <thead>
            <tr>
              {header("symbol", "Symbol", "left")}
              <th data-align="left">Portfolio</th>
              {header("quantity", "Qty")}
              {header("avg_cost", "Avg Cost")}
              {header("market_value", "Market Value")}
              {header("unrealized_pnl", "Open P&L")}
              {header("return_pct", "Return")}
            </tr>
          </thead>
          <tbody>
            {sorted.map(r => {
              const pnlTone = r.unrealized_pnl == null ? "" : r.unrealized_pnl > 0 ? "good" : r.unrealized_pnl < 0 ? "bad" : "";
              const retTone = r.return_pct == null ? "" : r.return_pct > 0 ? "good" : r.return_pct < 0 ? "bad" : "";
              return (
                <tr key={r.position_id}>
                  <td data-align="left"><span className="pi-pos-symbol">{r.symbol}</span></td>
                  <td data-align="left" className="pi-pos-portfolio">{r.portfolio_name ?? "—"}</td>
                  <td data-align="right">{r.quantity.toLocaleString()}</td>
                  <td data-align="right">{fmtCurrency(r.avg_cost)}</td>
                  <td data-align="right">{fmtCurrency(r.market_value)}</td>
                  <td data-align="right" data-tone={pnlTone}>{fmtSigned(r.unrealized_pnl)}</td>
                  <td data-align="right" data-tone={retTone}>{fmtPct(r.return_pct)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
