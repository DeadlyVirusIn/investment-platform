import { usePerformance } from "@/lib/operator/hooks";
import { cn } from "@/lib/cn";

function MetricCell({
  label, value, tone = "neutral",
}: {
  label: string; value: string;
  tone?: "pos" | "neg" | "neutral";
}) {
  const c = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger"
    : "text-text-primary";
  return (
    <div className="flex justify-between items-baseline py-1 text-sm">
      <span className="text-text-muted text-xs">{label}</span>
      <span className={cn("tabular-nums font-medium", c)}>{value}</span>
    </div>
  );
}

function EngineCard({
  title, badge, n, hit, avg, dur, total, sharpe,
}: {
  title: string; badge: string; n: number; hit: number; avg: number;
  dur: number; total: number; sharpe: number;
}) {
  const tone = total > 0 ? "pos" : total < 0 ? "neg" : "neutral";
  return (
    <div className="rounded-md bg-surface-hover/50 border border-surface-border/60 p-3">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-sm font-semibold text-text-primary">{title}</h4>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/20 text-accent">
          {badge}
        </span>
      </div>
      <MetricCell label="Recorded state transitions" value={String(n)} />
      <MetricCell label="Win rate" value={`${(hit * 100).toFixed(1)}%`} />
      <MetricCell label="Avg return" value={`${avg > 0 ? "+" : ""}${avg.toFixed(3)}%`}
                  tone={avg > 0 ? "pos" : "neg"} />
      <MetricCell label="Avg duration" value={`${dur.toFixed(1)} bars`} />
      <MetricCell label="Sharpe proxy" value={sharpe.toFixed(2)}
                  tone={sharpe > 1 ? "pos" : sharpe < 0 ? "neg" : "neutral"} />
      <MetricCell label="Total P&L %" value={`${total > 0 ? "+" : ""}${total.toFixed(2)}%`}
                  tone={tone} />
    </div>
  );
}

export default function PerformancePanel() {
  const { data, isLoading } = usePerformance();

  if (isLoading || !data) {
    return (
      <div className="rounded-lg bg-surface-card border border-surface-border p-4">
        <div className="h-48 bg-surface-hover animate-pulse rounded" />
      </div>
    );
  }

  return (
    <div className="rounded-lg bg-surface-card border border-surface-border p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-3">
        Performance Attribution
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        <EngineCard title="Engine A — P15 Mean-Rev" badge="stress"
          n={data.engine_a.n_trades}
          hit={data.engine_a.win_rate}
          avg={data.engine_a.avg_return_pct}
          dur={data.engine_a.avg_duration_bars}
          total={data.engine_a.total_pnl_pct}
          sharpe={data.engine_a.sharpe_proxy} />
        <EngineCard title="Engine B — Credit+Rates" badge="directional"
          n={data.engine_b.n_trades}
          hit={data.engine_b.win_rate}
          avg={data.engine_b.avg_return_pct}
          dur={data.engine_b.avg_duration_bars}
          total={data.engine_b.total_pnl_pct}
          sharpe={data.engine_b.sharpe_proxy} />
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="rounded-md bg-surface-hover/40 border border-surface-border/60 p-2">
          <div className="text-xs uppercase text-text-muted mb-1">Stress regime</div>
          <div className="text-xs text-text-secondary">
            {(data.stress_regime.pct_of_time * 100).toFixed(1)}% of time ·
            n={data.stress_regime.n_trades}
          </div>
          <div className="text-sm font-medium mt-1
                          tabular-nums text-text-primary">
            mean {data.stress_regime.mean_return_pct.toFixed(3)}%
          </div>
        </div>
        <div className="rounded-md bg-surface-hover/40 border border-surface-border/60 p-2">
          <div className="text-xs uppercase text-text-muted mb-1">Directional regime</div>
          <div className="text-xs text-text-secondary">
            {(data.directional_regime.pct_of_time * 100).toFixed(1)}% of time ·
            n={data.directional_regime.n_trades}
          </div>
          <div className="text-sm font-medium mt-1
                          tabular-nums text-text-primary">
            mean {data.directional_regime.mean_return_pct.toFixed(3)}%
          </div>
        </div>
      </div>

      <div>
        <div className="text-xs uppercase text-text-muted mb-2">
          Monthly P&amp;L
        </div>
        <div className="flex items-end gap-0.5 h-24">
          {data.monthly_pnl.map(m => {
            const maxAbs = Math.max(...data.monthly_pnl.map(x => Math.abs(x.pnl_pct)), 0.1);
            const heightPct = Math.abs(m.pnl_pct) / maxAbs * 100;
            const bg = m.pnl_pct > 0 ? "bg-success/60" : "bg-danger/60";
            return (
              <div key={m.month} className="flex-1 flex flex-col items-center gap-1
                                              group relative">
                <div className={cn("w-full rounded-sm", bg)}
                     style={{ height: `${heightPct}%` }} />
                <span className="text-[9px] text-text-muted">
                  {m.month.slice(5)}
                </span>
                <div className="hidden group-hover:block absolute -top-6 bg-surface-hover
                                border border-surface-border px-1.5 py-0.5 rounded text-[10px]
                                whitespace-nowrap z-10">
                  {m.month}: {m.pnl_pct > 0 ? "+" : ""}{m.pnl_pct.toFixed(2)}% ({m.n_trades}t)
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
