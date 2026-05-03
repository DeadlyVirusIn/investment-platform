// Phase: ENGINE-B-MIGRATION transition tracker.
// Read-only display of current mode, B-vs-B2 metrics, divergence,
// promotion gates, and kill switch state. Mode change is via env var
// only (operator-controlled). UI does NOT mutate.

import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import {
  useEngineBAnalytics, useEngineBDecision,
  useEngineBTimeline, useEngineBTransition,
} from "@/lib/engineB/hooks";


export default function EngineBTransitionCard() {
  const { data, isLoading } = useEngineBTransition(365);
  const { data: tl } = useEngineBTimeline(30);
  const { data: analytics } = useEngineBAnalytics(365);
  const { data: decision } = useEngineBDecision(365);

  if (isLoading || !data) {
    return (
      <div className="u-card">
        <Label>Engine B → B2 Migration</Label>
        <div className="u-caption-2 mt-2">loading…</div>
      </div>
    );
  }

  const { current_mode, state_order, verdict, divergence_stats,
            metrics, n_total_days, n_divergent_days,
            execution_changed_under_current_mode,
            operator_approval } = data;

  const action = verdict.action;
  const kill = verdict.kill_switch;

  return (
    <div className="u-card">
      <div className="flex items-start justify-between mb-3">
        <div>
          <Label>Engine B → B2 Migration</Label>
          <div className="u-caption-2 mt-0.5">
            controlled rollout · advisory only · operator-flipped
          </div>
        </div>
        <span className={cn("u-chip",
            current_mode === "LEGACY" ? "u-chip-neutral"
            : current_mode === "SHADOW_COMPARE" ? "u-chip-info"
            : current_mode === "FULL_B2" ? "u-chip-success"
            : "u-chip-warning")}>
          {current_mode}
        </span>
      </div>

      {/* Rollout strip */}
      <div className="mb-3 pb-3 border-b border-b1">
        <div className="u-label-sm mb-1.5">Rollout state machine</div>
        <div className="flex items-center gap-1">
          {state_order.map((s, i) => {
            const idx = state_order.indexOf(current_mode);
            const past = i < idx;
            const cur = i === idx;
            return (
              <div key={s} className="flex items-center gap-1 flex-1">
                <span className={cn(
                    "u-caption-2 px-2 py-0.5 rounded font-mono",
                    cur ? "bg-fg text-bg font-semibold"
                    : past ? "text-success bg-success/10"
                    : "text-fg-3 bg-bg-2")}>
                  {s.replace("PARTIAL_B2_", "P")}
                </span>
                {i < state_order.length - 1 && (
                  <span className={cn(
                      past ? "text-success" : "text-fg-3")}>→</span>
                )}
              </div>
            );
          })}
        </div>
        <div className="u-caption-2 mt-2 text-fg-3">
          execution_changed: {String(execution_changed_under_current_mode)} ·
          operator_approval: {String(operator_approval)}
        </div>
      </div>

      {/* Verdict */}
      <div className={cn("mb-3 pb-3 border-b border-b1 p-2 rounded",
            action === "ADVANCE" ? "bg-success/5"
            : action === "REVERT" ? "bg-danger/5"
            : "bg-bg-2")}>
        <div className="flex items-center justify-between mb-1">
          <span className="u-label-sm">Promotion verdict</span>
          <span className={cn("u-chip",
              action === "ADVANCE" ? "u-chip-success"
              : action === "REVERT" ? "u-chip-danger"
              : "u-chip-neutral")}>
            {action} → {verdict.recommended_state}
          </span>
        </div>
        <div className="u-caption-2 text-fg-3">{verdict.note}</div>
        {kill && kill.triggered && (
          <div className="u-caption-2 text-danger mt-1">
            Kill switch: {kill.reason}
          </div>
        )}
      </div>

      {/* Gates */}
      <div className="mb-3 pb-3 border-b border-b1">
        <div className="u-label-sm mb-1.5">Promotion gates ({verdict.gates.length})</div>
        <ul className="space-y-1">
          {verdict.gates.map(g => (
            <li key={g.name}
                  className="flex items-center justify-between u-caption-2">
              <span className="font-mono text-fg-2">{g.name}</span>
              <div className="flex items-center gap-2">
                <span className="u-mono-sm text-fg-3">
                  {String(g.actual)} / {String(g.threshold)}
                </span>
                <span className={cn(
                    "px-1.5 rounded text-[10px]",
                    g.passed ? "bg-success/15 text-success"
                    : "bg-danger/15 text-danger")}>
                  {g.passed ? "PASS" : "FAIL"}
                </span>
              </div>
            </li>
          ))}
        </ul>
      </div>

      {/* B vs B2 metrics */}
      <div className="grid grid-cols-3 gap-2 mb-3 pb-3 border-b border-b1">
        <Metric label="Engine B"
                 cum={metrics.engine_b?.cumulative_pct}
                 mean={metrics.engine_b?.mean_bps}
                 n={metrics.engine_b?.n} />
        <Metric label="Engine B2"
                 cum={metrics.b2?.cumulative_pct}
                 mean={metrics.b2?.mean_bps}
                 n={metrics.b2?.n} />
        <Metric label="Routed"
                 cum={metrics.routed?.cumulative_pct}
                 mean={metrics.routed?.mean_bps}
                 n={metrics.routed?.n} />
      </div>

      {/* Divergence */}
      {divergence_stats ? (
        <div className="mb-3 pb-3 border-b border-b1">
          <div className="u-label-sm mb-1.5">
            Divergence stats ({divergence_stats.n_divergent_days} days)
          </div>
          <div className="grid grid-cols-3 gap-2 mb-2">
            <Stat k="B2 won" v={`${divergence_stats.b2_won_days}d`}
                    tone="text-success" />
            <Stat k="B2 lost" v={`${divergence_stats.b2_lost_days}d`}
                    tone="text-danger" />
            <Stat k="Tied" v={`${divergence_stats.tied_days}d`} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Stat k="Mean B2-edge"
                    v={`${divergence_stats.mean_b2_advantage_bps.toFixed(1)} bps`}
                    tone={divergence_stats.mean_b2_advantage_bps > 0
                            ? "text-success" : "text-danger"} />
            <Stat k="Cum B2-edge"
                    v={`${divergence_stats.cumulative_b2_advantage_pct.toFixed(2)}%`}
                    tone={divergence_stats.cumulative_b2_advantage_pct > 0
                            ? "text-success" : "text-danger"} />
          </div>
        </div>
      ) : (
        <div className="mb-3 pb-3 border-b border-b1 u-caption-2 text-fg-3">
          No divergent days observed yet ({n_divergent_days} flagged but
          missing realized outcome).
        </div>
      )}

      {/* Recent timeline */}
      {tl && tl.timeline.length > 0 && (
        <div className="mb-2">
          <div className="u-label-sm mb-1.5">
            Last {Math.min(10, tl.timeline.length)} signals
          </div>
          <table className="w-full text-left">
            <thead>
              <tr className="u-caption-2 text-fg-3">
                <th className="font-normal">Date</th>
                <th className="font-normal">B</th>
                <th className="font-normal">B2</th>
                <th className="font-normal">Routed</th>
                <th className="font-normal text-right">Fwd 1d</th>
              </tr>
            </thead>
            <tbody>
              {tl.timeline.slice(-10).reverse().map(r => (
                <tr key={r.date} className="u-caption-2">
                  <td className="u-mono-sm text-fg-2">{r.date}</td>
                  <td className={cn("u-mono-sm",
                      r.engine_b_signal === "LONG" ? "text-success"
                      : "text-fg-3")}>{r.engine_b_signal ?? "—"}</td>
                  <td className={cn("u-mono-sm",
                      r.b2_signal === "LONG" ? "text-success"
                      : "text-fg-3")}>{r.b2_signal ?? "—"}</td>
                  <td className={cn("u-mono-sm",
                      r.divergence_flag ? "text-warning"
                      : r.routed_signal === "LONG" ? "text-success"
                      : "text-fg-3")}>{r.routed_signal ?? "—"}</td>
                  <td className={cn("u-mono-sm text-right",
                      (r.fwd_return_1d ?? 0) > 0 ? "text-success"
                      : (r.fwd_return_1d ?? 0) < 0 ? "text-danger"
                      : "text-fg-3")}>
                    {r.fwd_return_1d != null
                      ? `${(r.fwd_return_1d * 100).toFixed(2)}%`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Decision framework — confidence + 9 gates */}
      {decision && (
        <DecisionSection decision={decision} />
      )}

      {/* Analytics — divergence, tail, transition, stability */}
      {analytics && (
        <AnalyticsSection analytics={analytics} />
      )}

      <div className="u-caption-2 text-fg-3 italic">
        Advisory only · auto_promote=false · n={n_total_days}
      </div>
    </div>
  );
}


function DecisionSection({ decision }: {
  decision: import("@/lib/engineB/hooks").DecisionVerdict;
}) {
  const ready = decision.label === "STRONG_CANDIDATE"
                 && decision.failed_gates.length === 0
                 && decision.operator_approval;
  return (
    <div className="mt-4 pt-3 border-t border-b1">
      <div className="flex items-center justify-between mb-2">
        <span className="u-label-sm">Promotion decision framework</span>
        <span className={cn("u-chip",
            decision.label === "STRONG_CANDIDATE" ? "u-chip-success"
            : decision.label === "READY_FOR_REVIEW" ? "u-chip-warning"
            : "u-chip-neutral")}>
          {decision.label} · {decision.score}/100
        </span>
      </div>

      {/* Promotion pause banner — governance protection, not error */}
      {decision.promotion_pause?.active && (
        <div className={cn("mb-3 p-2 rounded u-caption",
            decision.promotion_pause.severity === "BLOCKING"
              ? "bg-danger/10 text-danger border border-danger/30"
              : "bg-warning/10 text-warning border border-warning/30")}>
          <div className="font-semibold mb-1">
            {decision.promotion_pause.severity === "BLOCKING"
              ? "🛑 Promotion paused (governance protection)"
              : "⚠ Promotion paused (warning)"}
          </div>
          <div className="u-caption-2">
            {decision.promotion_pause.reason}
          </div>
          <div className="u-caption-2 italic mt-1 opacity-80">
            Clear condition: {decision.promotion_pause.clear_condition}
          </div>
        </div>
      )}

      {/* Banner */}
      {ready && (
        <div className="mb-3 p-2 rounded bg-success/15 text-success
                          u-caption font-semibold">
          ✓ All gates pass · operator approved · ready for promotion
          to {decision.recommended_state}
        </div>
      )}
      {decision.kill_switch.triggered && (
        <div className="mb-3 p-2 rounded bg-danger/15 text-danger u-caption">
          ⚠ Kill switch: {decision.kill_switch.reason}
        </div>
      )}

      {/* Score breakdown */}
      <div className="mb-3">
        <div className="u-label-sm mb-1.5">Confidence score breakdown</div>
        <ul className="space-y-1">
          {Object.entries(decision.score_breakdown).map(([k, v]) => (
            <li key={k} className="flex justify-between u-caption-2">
              <span className="font-mono text-fg-2">{k}</span>
              <span className="u-mono-sm">{v}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* 9 hard gates */}
      <div className="mb-3">
        <div className="u-label-sm mb-1.5">
          Hard gates ({decision.gates.length - decision.failed_gates.length}/{decision.gates.length} pass)
        </div>
        <ul className="space-y-1">
          {decision.gates.map(g => (
            <li key={g.name}
                  className="flex items-center justify-between u-caption-2">
              <span className="font-mono text-fg-2">{g.name}</span>
              <div className="flex items-center gap-2">
                <span className="u-mono-sm text-fg-3">
                  {String(g.actual)} / {String(g.threshold)}
                </span>
                <span className={cn(
                    "px-1.5 rounded text-[10px]",
                    g.passed ? "bg-success/15 text-success"
                    : "bg-danger/15 text-danger")}>
                  {g.passed ? "PASS" : "FAIL"}
                </span>
              </div>
            </li>
          ))}
        </ul>
      </div>

      {/* 3-window stability */}
      {decision.stability_windows.length > 0 && (
        <div className="mb-3">
          <div className="u-label-sm mb-1.5">
            3-window stability check
          </div>
          <table className="w-full text-left">
            <thead>
              <tr className="u-caption-2 text-fg-3">
                <th className="font-normal">Window</th>
                <th className="font-normal text-right">n</th>
                <th className="font-normal text-right">Sharpe</th>
                <th className="font-normal text-right">Cum%</th>
                <th className="font-normal text-right">Edge bps</th>
                <th className="font-normal text-right">Pass</th>
              </tr>
            </thead>
            <tbody>
              {decision.stability_windows.map((w, i) => (
                <tr key={i} className="u-caption-2">
                  <td className="text-fg-2">{w.window_days}d</td>
                  <td className="text-right u-mono-sm">{w.n}</td>
                  <td className={cn("text-right u-mono-sm",
                      (w.sharpe ?? 0) >= 0.5 ? "text-success"
                      : (w.sharpe ?? 0) >= 0 ? "text-fg"
                      : "text-danger")}>
                    {w.sharpe != null ? w.sharpe.toFixed(2) : "—"}
                  </td>
                  <td className="text-right u-mono-sm">
                    {w.cumulative_pct != null
                      ? w.cumulative_pct.toFixed(2) + "%" : "—"}
                  </td>
                  <td className="text-right u-mono-sm">
                    {w.mean_edge_bps != null
                      ? w.mean_edge_bps.toFixed(1) : "—"}
                  </td>
                  <td className="text-right">
                    <span className={cn(
                        "px-1.5 rounded text-[10px]",
                        w.pass_threshold ? "bg-success/15 text-success"
                        : "bg-danger/15 text-danger")}>
                      {w.pass_threshold ? "✓" : "✗"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="u-caption-2 text-fg-3">{decision.note}</div>
    </div>
  );
}


function AnalyticsSection({ analytics }: {
  analytics: import("@/lib/engineB/hooks").AnalyticsBundle;
}) {
  const div = analytics.divergence;
  const tail = analytics.tail_risk;
  const trans = analytics.transition_zones;
  const reg = analytics.regime_consistency;
  const stab = analytics.stability;

  return (
    <div className="mt-4 pt-3 border-t border-b1">
      <div className="u-label-sm mb-2">Divergence + tail-risk analytics</div>

      {/* Edge trajectory */}
      {analytics.edge_trajectory && (
        <div className="mb-3 pb-3 border-b border-b1">
          <div className="flex items-center justify-between mb-1.5">
            <span className="u-caption-2 text-fg-3">
              Edge trajectory ({analytics.edge_trajectory.window_days}d)
            </span>
            <span className={cn("u-chip flex items-center gap-1",
                analytics.edge_trajectory.trend === "IMPROVING"
                  ? "u-chip-success"
                  : analytics.edge_trajectory.trend === "DECLINING"
                  ? "u-chip-danger"
                  : analytics.edge_trajectory.trend === "STABLE"
                  ? "u-chip-info"
                  : "u-chip-neutral")}>
              {analytics.edge_trajectory.trend === "IMPROVING" && "↑"}
              {analytics.edge_trajectory.trend === "DECLINING" && "↓"}
              {analytics.edge_trajectory.trend === "STABLE" && "→"}
              {analytics.edge_trajectory.trend === "INSUFFICIENT" && "·"}
              <span>{analytics.edge_trajectory.trend}</span>
            </span>
          </div>
          <div className="grid grid-cols-3 gap-2 u-caption-2">
            <Stat k="Recent"
                     v={analytics.edge_trajectory.recent_mean_edge_bps != null
                          ? analytics.edge_trajectory.recent_mean_edge_bps.toFixed(1) + " bps"
                          : "—"} />
            <Stat k="Prior"
                     v={analytics.edge_trajectory.prior_mean_edge_bps != null
                          ? analytics.edge_trajectory.prior_mean_edge_bps.toFixed(1) + " bps"
                          : "—"} />
            <Stat k="Δ"
                     v={analytics.edge_trajectory.delta_bps != null
                          ? (analytics.edge_trajectory.delta_bps > 0 ? "+" : "")
                            + analytics.edge_trajectory.delta_bps.toFixed(1) + " bps"
                          : "—"}
                     tone={(analytics.edge_trajectory.delta_bps ?? 0) > 0
                            ? "text-success"
                            : (analytics.edge_trajectory.delta_bps ?? 0) < 0
                            ? "text-danger" : "text-fg"} />
          </div>
          {analytics.edge_trajectory.slope_bps_per_day != null && (
            <div className="u-caption-2 text-fg-3 mt-1">
              slope:{" "}
              {analytics.edge_trajectory.slope_bps_per_day > 0 ? "+" : ""}
              {analytics.edge_trajectory.slope_bps_per_day.toFixed(2)} bps/day
            </div>
          )}
        </div>
      )}

      {/* Divergence */}
      <div className="mb-3 pb-3 border-b border-b1">
        <div className="u-caption-2 text-fg-3 mb-1.5">Divergence quality</div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 u-caption-2">
          <span className="text-fg-2">B2 win rate</span>
          <span className={cn("u-mono-sm text-right",
              (div.win_rate_b2_vs_b_pct ?? 0) >= 55
                ? "text-success" : "text-fg")}>
            {div.win_rate_b2_vs_b_pct != null
              ? div.win_rate_b2_vs_b_pct.toFixed(1) + "%" : "—"}
          </span>
          <span className="text-fg-2">Avg edge (bps)</span>
          <span className={cn("u-mono-sm text-right",
              (div.avg_return_diff_bps ?? 0) >= 10
                ? "text-success" : "text-fg")}>
            {div.avg_return_diff_bps != null
              ? "+" + div.avg_return_diff_bps.toFixed(1) : "—"}
          </span>
          <span className="text-fg-2">Cum edge</span>
          <span className={cn("u-mono-sm text-right",
              (div.cumulative_return_diff_pct ?? 0) > 0
                ? "text-success" : "text-fg")}>
            {div.cumulative_return_diff_pct != null
              ? div.cumulative_return_diff_pct.toFixed(2) + "%" : "—"}
          </span>
          <span className="text-fg-2">Avoided losses</span>
          <span className="u-mono-sm text-right">
            {div.avoided_loss_count}d
            {div.avoided_loss_avg_bps != null
              ? ` · μ ${div.avoided_loss_avg_bps.toFixed(0)}bps`
              : ""}
          </span>
          <span className="text-fg-2">Missed wins</span>
          <span className="u-mono-sm text-right">
            {div.missed_win_count}d
            {div.missed_win_avg_bps != null
              ? ` · μ ${div.missed_win_avg_bps.toFixed(0)}bps`
              : ""}
          </span>
        </div>
      </div>

      {/* Tail risk */}
      {tail.engine_b && tail.engine_b2 && (
        <div className="mb-3 pb-3 border-b border-b1">
          <div className="u-caption-2 text-fg-3 mb-1.5">
            Tail risk (B vs B2)
          </div>
          <div className="grid grid-cols-3 gap-2 u-caption-2 mb-1">
            <span></span>
            <span className="text-right text-fg-3">B</span>
            <span className="text-right text-fg-3">B2</span>
          </div>
          <div className="grid grid-cols-3 gap-2 u-caption-2">
            <span className="text-fg-2">p95 loss</span>
            <span className="u-mono-sm text-right">
              {tail.engine_b.p95_loss_pct != null
                ? tail.engine_b.p95_loss_pct.toFixed(2) + "%" : "—"}
            </span>
            <span className={cn("u-mono-sm text-right",
                (tail.engine_b2.p95_loss_pct ?? 0) >=
                  (tail.engine_b.p95_loss_pct ?? 0)
                ? "text-success" : "text-warning")}>
              {tail.engine_b2.p95_loss_pct != null
                ? tail.engine_b2.p95_loss_pct.toFixed(2) + "%" : "—"}
            </span>
            <span className="text-fg-2">p99 loss</span>
            <span className="u-mono-sm text-right">
              {tail.engine_b.p99_loss_pct != null
                ? tail.engine_b.p99_loss_pct.toFixed(2) + "%" : "—"}
            </span>
            <span className={cn("u-mono-sm text-right",
                (tail.engine_b2.p99_loss_pct ?? 0) >=
                  (tail.engine_b.p99_loss_pct ?? 0)
                ? "text-success" : "text-warning")}>
              {tail.engine_b2.p99_loss_pct != null
                ? tail.engine_b2.p99_loss_pct.toFixed(2) + "%" : "—"}
            </span>
            {tail.p99_improvement_pct != null && (
              <>
                <span className="text-fg-2">p99 imp</span>
                <span></span>
                <span className={cn("u-mono-sm text-right",
                    tail.p99_improvement_pct >= 0
                      ? "text-success" : "text-warning")}>
                  {tail.p99_improvement_pct.toFixed(2)}%
                </span>
              </>
            )}
          </div>
        </div>
      )}

      {/* Transition zones */}
      <div className="mb-3 pb-3 border-b border-b1">
        <div className="u-caption-2 text-fg-3 mb-1.5">
          Transition zones (T-5..T-1 before stress)
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 u-caption-2">
          <span className="text-fg-2">Stress entries</span>
          <span className="u-mono-sm text-right">
            {trans.n_stress_entries}
          </span>
          <span className="text-fg-2">Pre-stress obs</span>
          <span className="u-mono-sm text-right">
            {trans.n_pre_stress_obs}
          </span>
          <span className="text-fg-2">B2 avg pre-stress</span>
          <span className="u-mono-sm text-right">
            {trans.pre_stress_b2_avg_bps != null
              ? trans.pre_stress_b2_avg_bps.toFixed(1) + " bps" : "—"}
          </span>
          <span className="text-fg-2">% of total DD here</span>
          <span className="u-mono-sm text-right">
            {trans.pre_stress_share_of_total_loss_pct != null
              ? trans.pre_stress_share_of_total_loss_pct.toFixed(1)
                + "%" : "—"}
          </span>
        </div>
      </div>

      {/* Regime consistency */}
      <div className="mb-3 pb-3 border-b border-b1">
        <div className="u-caption-2 text-fg-3 mb-1.5">
          Regime consistency
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 u-caption-2">
          <span className="text-fg-2">Stress LONG %</span>
          <span className={cn("u-mono-sm text-right",
              (reg.stress_b2_long_pct ?? 0) <= 5
                ? "text-success" : "text-warning")}>
            {reg.stress_b2_long_pct != null
              ? reg.stress_b2_long_pct.toFixed(1) + "%" : "—"}
          </span>
          <span className="text-fg-2">Non-stress Sharpe</span>
          <span className={cn("u-mono-sm text-right",
              (reg.nonstress_perf?.sharpe ?? 0) >= 0.5
                ? "text-success" : "text-fg")}>
            {reg.nonstress_perf?.sharpe != null
              ? reg.nonstress_perf.sharpe.toFixed(2) : "—"}
          </span>
        </div>
      </div>

      {/* Stability halves */}
      {stab.early && stab.recent && (
        <div>
          <div className="u-caption-2 text-fg-3 mb-1.5">
            Stability (early vs recent halves)
          </div>
          <div className="grid grid-cols-3 gap-2 u-caption-2">
            <span></span>
            <span className="text-right text-fg-3">Early</span>
            <span className="text-right text-fg-3">Recent</span>
            <span className="text-fg-2">B2 Sharpe</span>
            <span className="u-mono-sm text-right">
              {stab.early.b2_sharpe != null
                ? stab.early.b2_sharpe.toFixed(2) : "—"}
            </span>
            <span className={cn("u-mono-sm text-right",
                (stab.recent.b2_sharpe ?? 0) >=
                  (stab.early.b2_sharpe ?? 0)
                ? "text-success" : "text-warning")}>
              {stab.recent.b2_sharpe != null
                ? stab.recent.b2_sharpe.toFixed(2) : "—"}
            </span>
            <span className="text-fg-2">Mean edge bps</span>
            <span className="u-mono-sm text-right">
              {stab.early.mean_b2_edge_bps != null
                ? stab.early.mean_b2_edge_bps.toFixed(1) : "—"}
            </span>
            <span className={cn("u-mono-sm text-right",
                (stab.recent.mean_b2_edge_bps ?? 0) >=
                  (stab.early.mean_b2_edge_bps ?? 0)
                ? "text-success" : "text-warning")}>
              {stab.recent.mean_b2_edge_bps != null
                ? stab.recent.mean_b2_edge_bps.toFixed(1) : "—"}
            </span>
          </div>
          {stab.sharpe_drift != null && (
            <div className="u-caption-2 text-fg-3 mt-1.5">
              Sharpe drift: {stab.sharpe_drift > 0 ? "+" : ""}
              {stab.sharpe_drift.toFixed(2)}
              {stab.edge_drift_bps != null && (
                <> · Edge drift: {stab.edge_drift_bps > 0 ? "+" : ""}
                {stab.edge_drift_bps.toFixed(1)} bps</>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}


function Metric({ label, cum, mean, n }: {
  label: string;
  cum?: number | null; mean?: number | null; n?: number | null;
}) {
  return (
    <div>
      <div className="u-caption-2 text-fg-3">{label} (n={n ?? 0})</div>
      <div className={cn("u-mono-sm font-semibold",
          (cum ?? 0) > 0 ? "text-success"
          : (cum ?? 0) < 0 ? "text-danger" : "text-fg")}>
        {cum != null ? `${cum.toFixed(2)}%` : "—"}
      </div>
      <div className="u-caption-2 text-fg-3">
        μ {mean != null ? `${mean.toFixed(1)} bps` : "—"}
      </div>
    </div>
  );
}


function Stat({ k, v, tone }: {
  k: string; v: string; tone?: string;
}) {
  return (
    <div>
      <div className="u-caption-2 text-fg-3">{k}</div>
      <div className={cn("u-mono-sm font-semibold", tone ?? "text-fg")}>
        {v}
      </div>
    </div>
  );
}
