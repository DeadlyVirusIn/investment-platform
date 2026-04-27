import { useState } from "react";
import { usePaperTrades } from "@/lib/operator/hooks";
import { cn } from "@/lib/cn";
import type { TradeRow } from "@/lib/operator/types";

type Filter = "all" | "open" | "closed";

function fmtPct(n: number | null, digits = 2): string {
  if (n === null || n === undefined) return "—";
  const s = n > 0 ? "+" : "";
  return `${s}${n.toFixed(digits)}%`;
}

function fmtUSD(n: number | null): string {
  if (n === null || n === undefined) return "—";
  const s = n > 0 ? "+" : "";
  return `${s}$${n.toFixed(2)}`;
}

export default function TradeTable({
  onSelect,
}: {
  onSelect?: (t: TradeRow) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const { data, isLoading } = usePaperTrades(
    filter === "all" ? undefined : filter,
  );

  const rows = data ?? [];

  return (
    <div className="rounded-lg bg-surface-card border border-surface-border p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-primary">
          Trade Ledger <span className="text-text-muted font-normal">({rows.length})</span>
        </h3>
        <div className="flex gap-1">
          {(["all", "open", "closed"] as Filter[]).map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`text-xs px-2 py-0.5 rounded border
                ${filter === f
                  ? "bg-accent/20 text-accent border-accent/40"
                  : "bg-surface-hover text-text-muted border-surface-border hover:text-text-primary"}`}>
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-text-muted uppercase text-[10px] border-b border-surface-border">
              <th className="text-left pb-2 pr-3">Entry</th>
              <th className="text-left pb-2 pr-3">Exit</th>
              <th className="text-center pb-2 pr-3">Eng</th>
              <th className="text-right pb-2 pr-3">Ret%</th>
              <th className="text-right pb-2 pr-3">P&amp;L $</th>
              <th className="text-right pb-2 pr-3">Held</th>
              <th className="text-left pb-2 pr-3">Regime</th>
              <th className="text-center pb-2 pr-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && rows.length === 0 ? (
              <tr><td colSpan={8} className="text-center py-4 text-text-muted">Loading…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={8} className="text-center py-4 text-text-muted">No trades</td></tr>
            ) : rows.map(t => {
              const retClass = t.net_ret_pct === null
                ? "text-text-secondary"
                : t.net_ret_pct > 0 ? "text-success" : "text-danger";
              return (
                <tr key={t.trade_id}
                    onClick={() => onSelect?.(t)}
                    className="border-b border-surface-border/60 hover:bg-surface-hover
                               cursor-pointer transition-colors">
                  <td className="py-2 pr-3 text-text-primary">{t.entry_date}</td>
                  <td className="py-2 pr-3 text-text-secondary">
                    {t.exit_date ?? <span className="text-warning">open</span>}
                  </td>
                  <td className="py-2 pr-3 text-center">
                    <span className={cn(
                      "inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold",
                      t.engine === "A" ? "bg-info/20 text-info" : "bg-accent/20 text-accent",
                    )}>{t.engine}</span>
                  </td>
                  <td className={cn("py-2 pr-3 text-right tabular-nums font-medium", retClass)}>
                    {fmtPct(t.net_ret_pct)}
                  </td>
                  <td className={cn("py-2 pr-3 text-right tabular-nums", retClass)}>
                    {fmtUSD(t.pnl_dollar)}
                  </td>
                  <td className="py-2 pr-3 text-right text-text-secondary">
                    {t.days_held ?? "—"}d
                  </td>
                  <td className="py-2 pr-3 text-text-secondary uppercase text-[10px]">
                    {t.regime_at_entry}
                  </td>
                  <td className="py-2 pr-3 text-center">
                    <span className={cn("text-[10px] px-1.5 py-0.5 rounded",
                      t.status === "open" ? "bg-warning/20 text-warning"
                        : t.status === "closed" ? "bg-success/20 text-success"
                        : "bg-surface-border text-text-muted")}>
                      {t.status}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
