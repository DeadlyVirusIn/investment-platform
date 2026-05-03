// Phase: Shadow Strategy Tracker (research-only).
// Tracks tsmom_60_no_stress candidate. Displays current signal, last 10
// signals, cumulative perf, rolling Sharpe (30/60/90), drawdown, %
// active, % filtered. NEVER trades; advisory-only banner pinned.

import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { useShadowDivergence, useShadowReport } from "@/lib/shadow/hooks";


const STRATEGY = "tsmom_60_no_stress";


export default function ShadowStrategyCard() {
  const { data, isLoading } = useShadowReport(STRATEGY, 365);
  const { data: div } = useShadowDivergence(STRATEGY);

  if (isLoading || !data) {
    return (
      <div className="u-card">
        <Label>Shadow Strategy</Label>
        <div className="u-caption-2 mt-2">loading…</div>
      </div>
    );
  }

  if (!data.current || !data.metrics) {
    return (
      <div className="u-card">
        <Label>Shadow Strategy: {STRATEGY}</Label>
        <div className="u-caption mt-2 text-fg-3">
          No shadow log rows yet. Daily runner has not produced data.
        </div>
      </div>
    );
  }

  const { current, recent, metrics } = data;
  const r30 = metrics.rolling.find(r => r.window_days === 30);
  const r60 = metrics.rolling.find(r => r.window_days === 60);
  const r90 = metrics.rolling.find(r => r.window_days === 90);

  return (
    <div className="u-card">
      <div className="flex items-start justify-between mb-3">
        <div>
          <Label>Shadow Strategy</Label>
          <div className="u-caption-2 mt-0.5">
            <code>{STRATEGY}</code> · research only · never trades
          </div>
        </div>
        <span className={cn("u-chip",
            current.signal === "LONG" ? "u-chip-success"
            : current.regime === "STRESS" ? "u-chip-warning"
            : "u-chip-neutral")}>
          {current.signal}
          {current.regime === "STRESS" ? " · stress filter" : ""}
        </span>
      </div>

      {/* Current state */}
      <div className="grid grid-cols-3 gap-2 mb-3 pb-3 border-b border-b1">
        <Stat k="Date" v={current.as_of_date} mono />
        <Stat k="Regime" v={current.regime ?? "—"} />
        <Stat k="Engine A" v={current.engine_a_active ? "ACTIVE" : "off"}
              tone={current.engine_a_active ? "text-warning" : "text-fg-3"} />
        <Stat k="Trend score"
              v={current.trend_score != null
                  ? current.trend_score.toFixed(3) : "—"} mono />
        <Stat k="Cumulative" v={`${metrics.cumulative_pct.toFixed(2)}%`}
              mono tone={_perfTone(metrics.cumulative_pct)} />
        <Stat k="Sharpe (full)"
              v={metrics.sharpe_full != null
                  ? metrics.sharpe_full.toFixed(2) : "—"} mono
              tone={_sharpeTone(metrics.sharpe_full)} />
      </div>

      {/* Rolling windows */}
      <div className="mb-3 pb-3 border-b border-b1">
        <div className="u-label-sm mb-1.5">Rolling Sharpe</div>
        <div className="grid grid-cols-3 gap-2">
          <RollingStat label="30d" w={r30} />
          <RollingStat label="60d" w={r60} />
          <RollingStat label="90d" w={r90} />
        </div>
      </div>

      {/* Activity + drawdown */}
      <div className="grid grid-cols-4 gap-2 mb-3 pb-3 border-b border-b1">
        <Stat k="Active %"
              v={`${metrics.active_pct.toFixed(0)}%`} mono />
        <Stat k="Stress filtered"
              v={`${metrics.filtered_stress_pct.toFixed(0)}%`} mono />
        <Stat k="Hit (LONG)"
              v={metrics.hit_rate_on_long_pct != null
                  ? `${metrics.hit_rate_on_long_pct.toFixed(0)}%` : "—"}
              mono />
        <Stat k="Max DD"
              v={`${metrics.max_dd_pct.toFixed(2)}%`} mono
              tone={metrics.max_dd_pct < -5 ? "text-warning"
                      : "text-fg-3"} />
      </div>

      {/* Last 10 signals */}
      <div className="mb-3">
        <div className="u-label-sm mb-1.5">Last 10 signals</div>
        <ul className="space-y-1">
          {recent.map(r => (
            <li key={r.as_of_date}
                  className="flex items-center justify-between
                              u-caption-2">
              <span className="u-mono-sm text-fg-2">{r.as_of_date}</span>
              <span className={cn("u-mono-sm",
                  r.signal === "LONG" ? "text-success" : "text-fg-3")}>
                {r.signal}
              </span>
              <span className="u-caption-2 text-fg-3">{r.regime ?? "—"}</span>
              <span className={cn("u-mono-sm",
                  r.fwd_return_1d != null
                  ? _perfTone(r.fwd_return_1d * 100) : "text-fg-3")}>
                {r.fwd_return_1d != null
                  ? `${(r.fwd_return_1d * 100).toFixed(2)}%`
                  : "—"}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {/* Divergence vs production engines */}
      {div && (div.vs_engine_a || div.vs_engine_b) && (
        <div className="mb-3 pb-3 border-t border-b1 pt-3">
          <div className="u-label-sm mb-1.5">Divergence vs production</div>
          <ul className="space-y-1">
            {div.vs_engine_a && (
              <li className="flex justify-between u-caption-2">
                <span className="text-fg-2">vs Engine A (n={div.vs_engine_a.n})</span>
                <span className={cn("u-mono-sm",
                    _perfTone(div.vs_engine_a.cumulative_pct))}>
                  {div.vs_engine_a.cumulative_pct.toFixed(2)}% ·
                  μ {div.vs_engine_a.mean_bps.toFixed(1)}bps
                </span>
              </li>
            )}
            {div.vs_engine_b && (
              <li className="flex justify-between u-caption-2">
                <span className="text-fg-2">vs Engine B (n={div.vs_engine_b.n})</span>
                <span className={cn("u-mono-sm",
                    _perfTone(div.vs_engine_b.cumulative_pct))}>
                  {div.vs_engine_b.cumulative_pct.toFixed(2)}% ·
                  μ {div.vs_engine_b.mean_bps.toFixed(1)}bps
                </span>
              </li>
            )}
          </ul>
        </div>
      )}

      {/* Per-regime breakdown */}
      {metrics.by_regime?.length > 0 && (
        <div className="mb-3">
          <div className="u-label-sm mb-1.5">Per-regime performance</div>
          <table className="w-full text-left">
            <thead>
              <tr className="u-caption-2 text-fg-3">
                <th className="font-normal">Regime</th>
                <th className="font-normal text-right">Days</th>
                <th className="font-normal text-right">LONG</th>
                <th className="font-normal text-right">Sharpe</th>
                <th className="font-normal text-right">Cum%</th>
              </tr>
            </thead>
            <tbody>
              {metrics.by_regime.map(r => (
                <tr key={r.regime} className="u-caption-2">
                  <td className="text-fg-2">{r.regime}</td>
                  <td className="text-right u-mono-sm">{r.n_days}</td>
                  <td className="text-right u-mono-sm">{r.n_long}</td>
                  <td className={cn("text-right u-mono-sm",
                      _sharpeTone(r.sharpe))}>
                    {r.sharpe != null ? r.sharpe.toFixed(2) : "—"}
                  </td>
                  <td className={cn("text-right u-mono-sm",
                      _perfTone(r.cumulative_pct))}>
                    {r.cumulative_pct.toFixed(2)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="u-caption-2 text-fg-3 italic">
        Advisory only · execution_changed=false ·
        n_total={metrics.n_total}.
      </div>
    </div>
  );
}


function Stat({ k, v, mono, tone }: {
  k: string; v: string; mono?: boolean; tone?: string;
}) {
  return (
    <div>
      <div className="u-caption-2 text-fg-3">{k}</div>
      <div className={cn(
          mono ? "u-mono-sm font-semibold" : "u-caption font-medium",
          tone ?? "text-fg")}>
        {v}
      </div>
    </div>
  );
}


function RollingStat({ label, w }: {
  label: string; w?: { sharpe: number | null;
                       cumulative_pct: number;
                       max_dd_pct: number; n: number };
}) {
  if (!w) {
    return (
      <div>
        <div className="u-caption-2 text-fg-3">{label}</div>
        <div className="u-mono-sm font-semibold text-fg-3">—</div>
      </div>
    );
  }
  return (
    <div>
      <div className="u-caption-2 text-fg-3">{label} (n={w.n})</div>
      <div className={cn("u-mono-sm font-semibold",
                            _sharpeTone(w.sharpe))}>
        {w.sharpe != null ? w.sharpe.toFixed(2) : "—"}
      </div>
      <div className="u-caption-2 text-fg-3">
        {w.cumulative_pct.toFixed(2)}% · DD {w.max_dd_pct.toFixed(2)}%
      </div>
    </div>
  );
}


function _sharpeTone(s: number | null | undefined): string {
  if (s == null) return "text-fg-3";
  if (s >= 1.0) return "text-success";
  if (s <= -0.3) return "text-danger";
  if (s < 0.5) return "text-warning";
  return "text-fg";
}


function _perfTone(pct: number): string {
  if (pct > 0.05) return "text-success";
  if (pct < -0.05) return "text-danger";
  return "text-fg-3";
}
