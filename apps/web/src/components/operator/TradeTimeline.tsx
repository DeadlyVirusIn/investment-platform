import { usePaperTrades } from "@/lib/operator/hooks";
import { cn } from "@/lib/cn";
import type { TradeRow } from "@/lib/operator/types";

function fmtPct(n: number | null): string {
  if (n === null) return "—";
  const s = n > 0 ? "+" : "";
  return `${s}${n.toFixed(2)}%`;
}

function fmtUSD(n: number | null): string {
  if (n === null) return "—";
  const v = Math.abs(n).toFixed(2);
  return `${n >= 0 ? "+" : "−"}$${v}`;
}

function TradeCard({
  t, selected, onClick,
}: {
  t: TradeRow; selected: boolean; onClick: () => void;
}) {
  const retTone = t.net_ret_pct === null ? "neutral"
    : t.net_ret_pct > 0 ? "pos" : "neg";
  const retCls = retTone === "pos" ? "text-success"
    : retTone === "neg" ? "text-danger" : "text-text-secondary";
  const engineChipCls = t.engine === "A"
    ? "bg-info-muted text-info border-info/40"
    : "bg-accent-subtle text-accent border-accent/40";

  return (
    <button onClick={onClick}
      className={cn(
        "group w-full text-left rounded-md border px-4 py-3",
        "transition-all duration-150 ease-out",
        selected
          ? "border-accent/70 bg-accent-subtle shadow-card-hover"
          : "border-surface-border/70 bg-surface-card hover:border-accent/30"
          + " hover:bg-surface-elev/60",
      )}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={cn("chip", engineChipCls)}>
            {t.engine}
          </span>
          <span className="text-tiny text-text-muted font-mono tabular-nums">
            {t.entry_date}
          </span>
          {t.status === "open" && (
            <span className="chip bg-warning-muted text-warning border-warning/40">
              OPEN
            </span>
          )}
        </div>
        <div className={cn("text-num-sm font-semibold tabular-nums", retCls)}>
          {fmtPct(t.net_ret_pct)}
        </div>
      </div>
      <div className="flex items-center justify-between text-tiny text-text-muted">
        <span className="capitalize">{t.regime_at_entry} regime</span>
        <span className="tabular-nums">
          {t.days_held !== null ? `${t.days_held}d held` : "holding"}
          {t.pnl_dollar !== null && (
            <span className={cn("ml-2", retCls)}>
              {fmtUSD(t.pnl_dollar)}
            </span>
          )}
        </span>
      </div>
    </button>
  );
}

export default function TradeTimeline({
  selectedTradeId, onSelect,
}: {
  selectedTradeId: string | null;
  onSelect: (t: TradeRow) => void;
}) {
  const { data, isLoading } = usePaperTrades();
  const rows = data ?? [];

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between mb-4 px-1">
        <h2 className="section-label">Trade Timeline</h2>
        <span className="text-tiny text-text-muted tabular-nums">
          {rows.length} trades
        </span>
      </div>

      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {isLoading ? (
          <>
            <div className="h-[72px] bg-surface-elev/40 animate-pulse rounded-md" />
            <div className="h-[72px] bg-surface-elev/40 animate-pulse rounded-md" />
            <div className="h-[72px] bg-surface-elev/40 animate-pulse rounded-md" />
          </>
        ) : rows.length === 0 ? (
          <div className="text-center py-16 text-text-muted">
            <div className="text-2xl mb-3 opacity-60">◎</div>
            <p className="text-body">No trades yet.</p>
            <p className="text-tiny mt-1">
              System will record activity as it fires.
            </p>
          </div>
        ) : rows.map(t => (
          <TradeCard key={t.trade_id} t={t}
            selected={selectedTradeId === t.trade_id}
            onClick={() => onSelect(t)} />
        ))}
      </div>
    </div>
  );
}
