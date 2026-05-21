import { cn } from "@/lib/cn";
import { usePaperSummary } from "@/lib/operator/hooks";

function fmtUSD(n: number, digits = 0): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  }).format(n);
}

function fmtPct(n: number, digits = 2): string {
  const s = n > 0 ? "+" : "";
  return `${s}${n.toFixed(digits)}%`;
}

function MetricBlock({
  label, value, sub, tone,
}: {
  label: string; value: string; sub?: string;
  tone: "pos" | "neg" | "neutral";
}) {
  const valueCls = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger" : "text-text-primary";
  return (
    <div className="flex-1 px-6 first:pl-0 last:pr-0
                     border-l border-surface-border/50 first:border-l-0">
      <div className="stat-label mb-2">{label}</div>
      <div className={cn("text-num-xl font-semibold tabular-nums", valueCls)}>
        {value}
      </div>
      {sub && (
        <div className="text-tiny text-text-muted mt-1.5">{sub}</div>
      )}
    </div>
  );
}

export default function KeyMetricsRow() {
  const { data } = usePaperSummary();
  if (!data) {
    return (
      <div className="card">
        <div className="h-24 bg-surface-elev/40 animate-pulse rounded-md" />
      </div>
    );
  }
  const dailyTone = data.daily_pnl > 0 ? "pos"
    : data.daily_pnl < 0 ? "neg" : "neutral";
  const cumTone = data.total_return_pct > 0 ? "pos"
    : data.total_return_pct < 0 ? "neg" : "neutral";

  return (
    <div className="card">
      <div className="flex flex-wrap gap-y-6">
        <MetricBlock label="Account value (NAV)"
                     value={fmtUSD(data.equity)}
                     sub={`cash ${fmtUSD(data.cash)}`}
                     tone="neutral" />
        <MetricBlock label="Today P&L"
                     value={fmtUSD(data.daily_pnl, 2)}
                     sub={fmtPct(data.daily_pnl / (data.equity || 1) * 100, 3)}
                     tone={dailyTone} />
        <MetricBlock label="Total return"
                     value={fmtPct(data.total_return_pct)}
                     sub="since inception · aggregate" tone={cumTone} />
        <MetricBlock label="Biggest drop from peak"
                     value={fmtPct(data.max_drawdown_pct)}
                     sub="peak-to-trough" tone="neg" />
      </div>
    </div>
  );
}
