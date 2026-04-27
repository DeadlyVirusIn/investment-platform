import { usePaperSummary } from "@/lib/operator/hooks";
import { cn } from "@/lib/cn";
import type { PaperSummary } from "@/lib/operator/types";

function fmtUSD(n: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: 0,
  }).format(n);
}

function fmtPct(n: number, digits = 2): string {
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(digits)}%`;
}

function StatCell({
  label, value, sub, tone,
}: {
  label: string; value: React.ReactNode; sub?: string;
  tone?: "pos" | "neg" | "warn" | "neutral";
}) {
  const toneColor = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger"
    : tone === "warn" ? "text-warning"
    : "text-text-primary";
  return (
    <div className="flex flex-col min-w-[110px]">
      <span className="text-[10px] uppercase tracking-wider text-text-muted">
        {label}
      </span>
      <span className={cn("text-lg font-semibold tabular-nums", toneColor)}>
        {value}
      </span>
      {sub && <span className="text-xs text-text-secondary">{sub}</span>}
    </div>
  );
}

export default function SummaryBar() {
  const { data, isLoading, error } = usePaperSummary();

  if (isLoading || !data) {
    return (
      <div className="sticky top-0 z-20 border-b border-surface-border
                       bg-surface/95 backdrop-blur px-6 py-3 flex gap-8">
        <div className="h-8 w-48 bg-surface-card animate-pulse rounded" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="sticky top-0 z-20 border-b border-danger/40
                       bg-danger/10 px-6 py-3 text-danger text-sm">
        Summary unavailable: {String(error)}
      </div>
    );
  }

  const s: PaperSummary = data;
  const cumTone = s.total_return_pct > 0 ? "pos"
    : s.total_return_pct < 0 ? "neg" : "neutral";

  return (
    <div className="sticky top-0 z-20 border-b border-surface-border
                     bg-surface/95 backdrop-blur px-6 py-3">
      <div className="flex items-center gap-8 flex-wrap">
        <StatCell label="Equity" value={fmtUSD(s.equity)} />
        <StatCell label="Total Return"
                  value={fmtPct(s.total_return_pct)} tone={cumTone}
                  sub={`daily ${fmtPct(s.daily_pnl / s.equity * 100, 3)}`} />
        <StatCell label="Max Drawdown"
                  value={fmtPct(s.max_drawdown_pct)} tone="neg" />
        <StatCell label="Regime" value={s.regime.toUpperCase()}
                  tone={s.regime === "none" ? "warn" : "neutral"} />
        <StatCell label="Active Engine"
                  value={s.engine_active === "none" ? "—" : s.engine_active}
                  tone={s.engine_active === "none" ? "warn" : "pos"} />
        <StatCell label="Open Positions"
                  value={s.open_positions_count} />
        <div className="ml-auto text-xs text-text-secondary">
          <span className={cn("inline-block w-2 h-2 rounded-full mr-2",
            s.pipeline_status === "success" ? "bg-success"
              : s.pipeline_status === "partial" ? "bg-warning" : "bg-danger"
          )} />
          {s.pipeline_status.toUpperCase()} · last run{" "}
          {new Date(s.last_decision_ts).toLocaleString()}
        </div>
      </div>
    </div>
  );
}
