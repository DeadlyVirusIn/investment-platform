// B2 vs V2 head-to-head comparison panel.
// Read-only. NEVER mutates state. NEVER triggers promotion or routing.
// Verdict + confidence + readiness are advisory; operator-only decision.

import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import {
  type DivergenceMetrics,
  type Verdict,
  useB2vsV2Comparison,
} from "@/lib/b2v2/hooks";


function fmt(
  v: number | null | undefined,
  digits = 2,
  suffix = "",
): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v.toFixed(digits)}${suffix}`;
}


function verdictChipClass(v: Verdict): string {
  if (v === "V2_BETTER") return "u-chip-success";
  if (v === "B2_BETTER") return "u-chip-danger";
  return "u-chip-neutral";
}


function readinessChipClass(r: string): string {
  if (r === "STRONG_CANDIDATE") return "u-chip-success";
  if (r === "REVIEW") return "u-chip-info";
  return "u-chip-neutral";
}


function trendChipClass(t: string): string {
  if (t === "IMPROVING") return "u-chip-success";
  if (t === "DECLINING") return "u-chip-danger";
  if (t === "STABLE") return "u-chip-info";
  return "u-chip-neutral";
}


function RegimeRow({
  label,
  m,
}: {
  label: string;
  m: DivergenceMetrics;
}) {
  return (
    <tr>
      <td className="py-1 pr-3 font-mono text-fg-2">{label}</td>
      <td className="py-1 pr-3 text-right">{m.n_divergent_days}</td>
      <td className="py-1 pr-3 text-right">{fmt(m.win_rate_v2_vs_b2_pct, 1, "%")}</td>
      <td className="py-1 pr-3 text-right">{fmt(m.avg_return_diff_1d_bps, 1)}</td>
      <td className="py-1 text-right">{fmt(m.impact_weighted_edge, 4)}</td>
    </tr>
  );
}


export default function B2vsV2ComparisonCard() {
  const { data, isLoading } = useB2vsV2Comparison(365, "SPY");

  if (isLoading || !data) {
    return (
      <div className="u-card">
        <Label>B2 vs V2 Comparison</Label>
        <div className="u-caption-2 mt-2">loading…</div>
      </div>
    );
  }

  const { metrics, metrics_by_regime, tail, stability, verdict, thresholds, params } = data;
  const guardTriggered = verdict.tail_guard_triggered;

  return (
    <div className="u-card">
      <div className="flex items-start justify-between mb-3">
        <div>
          <Label>B2 vs V2 Comparison</Label>
          <div className="u-caption-2 mt-0.5">
            advisory only · no routing change · operator-only decision · {params.instrument}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {guardTriggered && (
            <span
              className="u-chip u-chip-warning"
              title={verdict.tail_guard_reason ?? ""}
            >
              Tail-Sensitivity Guard
            </span>
          )}
          <span className={cn("u-chip", verdictChipClass(verdict.verdict))}>
            {verdict.verdict}
          </span>
          <span className={cn("u-chip", readinessChipClass(verdict.readiness))}>
            {verdict.readiness}
          </span>
        </div>
      </div>

      {/* Confidence bar */}
      <div className="mb-3 pb-3 border-b border-b1">
        <div className="flex items-center justify-between mb-1">
          <span className="u-label-sm">Confidence</span>
          <span className="u-caption-2 font-mono">
            {(verdict.confidence * 100).toFixed(0)}%
            {verdict.base_verdict_before_guard !== verdict.verdict && (
              <span className="ml-2 text-warning">
                (downgraded from {verdict.base_verdict_before_guard})
              </span>
            )}
          </span>
        </div>
        <div className="h-1.5 bg-bg-2 rounded overflow-hidden">
          <div
            className={cn(
              "h-full",
              verdict.confidence >= 0.7 ? "bg-success"
              : verdict.confidence >= 0.4 ? "bg-info"
              : "bg-fg-3",
            )}
            style={{ width: `${verdict.confidence * 100}%` }}
          />
        </div>
      </div>

      {/* Divergence stats */}
      <div className="mb-3 pb-3 border-b border-b1">
        <div className="u-label-sm mb-1.5">Divergence stats</div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 u-caption-2">
          <div>
            <div className="text-fg-3">days</div>
            <div className="font-mono">{metrics.n_divergent_days}</div>
          </div>
          <div>
            <div className="text-fg-3">win rate (V2 vs B2)</div>
            <div className="font-mono">{fmt(metrics.win_rate_v2_vs_b2_pct, 1, "%")}</div>
          </div>
          <div>
            <div className="text-fg-3">edge 1d</div>
            <div className="font-mono">{fmt(metrics.avg_return_diff_1d_bps, 2)} bps</div>
          </div>
          <div>
            <div className="text-fg-3">edge 5d</div>
            <div className="font-mono">{fmt(metrics.avg_return_diff_5d_bps, 2)} bps</div>
          </div>
          <div>
            <div className="text-fg-3">impact-weighted edge</div>
            <div className="font-mono">{fmt(metrics.impact_weighted_edge, 4)}</div>
          </div>
          <div>
            <div className="text-fg-3">cumulative diff</div>
            <div className="font-mono">{fmt(metrics.cumulative_return_diff_pct, 3, "%")}</div>
          </div>
        </div>
      </div>

      {/* Edge composition */}
      <div className="mb-3 pb-3 border-b border-b1">
        <div className="u-label-sm mb-1.5">Edge composition</div>
        <div className="grid grid-cols-2 gap-3 u-caption-2">
          <div>
            <div className="text-fg-3">avoided losses (B2 LONG → V2 FLAT)</div>
            <div className="font-mono">
              {metrics.avoided_losses_count} days · avg {fmt(metrics.avoided_losses_avg_bps, 1)} bps
            </div>
          </div>
          <div>
            <div className="text-fg-3">new losses (B2 FLAT → V2 LONG)</div>
            <div className="font-mono">
              {metrics.new_losses_count} days · avg {fmt(metrics.new_losses_avg_bps, 1)} bps
            </div>
          </div>
        </div>
      </div>

      {/* Tail comparison */}
      <div className="mb-3 pb-3 border-b border-b1">
        <div className="u-label-sm mb-1.5">Tail comparison</div>
        <table className="w-full u-caption-2 font-mono">
          <thead className="text-fg-3">
            <tr>
              <th className="text-left py-1 pr-3"></th>
              <th className="text-right py-1 pr-3">B2</th>
              <th className="text-right py-1 pr-3">V2</th>
              <th className="text-right py-1">Δ (V2 − B2)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="py-1 pr-3 text-fg-2">p95 loss (bps)</td>
              <td className="py-1 pr-3 text-right">{fmt(tail.b2.p95_loss_bps, 2)}</td>
              <td className="py-1 pr-3 text-right">{fmt(tail.v2.p95_loss_bps, 2)}</td>
              <td className="py-1 text-right">{fmt(tail.tail_delta_p95_bps, 2)}</td>
            </tr>
            <tr className={guardTriggered ? "bg-warning/10" : undefined}>
              <td className="py-1 pr-3 text-fg-2">p99 loss (bps)</td>
              <td className="py-1 pr-3 text-right">{fmt(tail.b2.p99_loss_bps, 2)}</td>
              <td className="py-1 pr-3 text-right">{fmt(tail.v2.p99_loss_bps, 2)}</td>
              <td className="py-1 text-right">{fmt(tail.tail_delta_p99_bps, 2)}</td>
            </tr>
            <tr>
              <td className="py-1 pr-3 text-fg-2 align-top">worst-5</td>
              <td className="py-1 pr-3 text-right">
                {tail.b2.worst_5_losses_bps.map((x) => x.toFixed(0)).join(", ") || "—"}
              </td>
              <td className="py-1 pr-3 text-right">
                {tail.v2.worst_5_losses_bps.map((x) => x.toFixed(0)).join(", ") || "—"}
              </td>
              <td className="py-1 text-right">—</td>
            </tr>
          </tbody>
        </table>
        {guardTriggered && (
          <div className="u-caption-2 mt-2 text-warning">
            ⚠ Tail-sensitivity guard triggered: {verdict.tail_guard_reason}
          </div>
        )}
      </div>

      {/* Regime breakdown */}
      <div className="mb-3 pb-3 border-b border-b1">
        <div className="u-label-sm mb-1.5">Regime breakdown</div>
        <table className="w-full u-caption-2">
          <thead className="text-fg-3">
            <tr>
              <th className="text-left py-1 pr-3">regime</th>
              <th className="text-right py-1 pr-3">n</th>
              <th className="text-right py-1 pr-3">win %</th>
              <th className="text-right py-1 pr-3">edge bps</th>
              <th className="text-right py-1">impact-wtd</th>
            </tr>
          </thead>
          <tbody>
            <RegimeRow label="STRESS" m={metrics_by_regime.stress} />
            <RegimeRow label="DIRECTIONAL" m={metrics_by_regime.directional} />
            <RegimeRow label="NEUTRAL" m={metrics_by_regime.neutral} />
          </tbody>
        </table>
      </div>

      {/* Stability */}
      <div>
        <div className="u-label-sm mb-1.5">Stability</div>
        <div className="grid grid-cols-2 gap-3 u-caption-2">
          <div>
            <div className="text-fg-3 mb-1">first half vs second half</div>
            <div className="font-mono">
              {fmt(stability.first_half_vs_second_half.first_half_edge_bps, 2)} →{" "}
              {fmt(stability.first_half_vs_second_half.second_half_edge_bps, 2)} bps
            </div>
            <span className={cn(
              "u-chip mt-1",
              trendChipClass(stability.first_half_vs_second_half.trend),
            )}>
              {stability.first_half_vs_second_half.trend}
            </span>
          </div>
          <div>
            <div className="text-fg-3 mb-1">last 30 vs prior 30</div>
            <div className="font-mono">
              {fmt(stability.last_30_vs_prior_30.prior_30_edge_bps, 2)} →{" "}
              {fmt(stability.last_30_vs_prior_30.last_30_edge_bps, 2)} bps
            </div>
            <span className={cn(
              "u-chip mt-1",
              trendChipClass(stability.last_30_vs_prior_30.trend),
            )}>
              {stability.last_30_vs_prior_30.trend}
            </span>
          </div>
        </div>
      </div>

      <div className="u-caption-2 mt-3 pt-3 border-t border-b1 text-fg-3">
        thresholds: edge ≥ {thresholds.verdict_edge_bps} bps · cum ≥{" "}
        {thresholds.verdict_cum_diff_pct}% · tail-guard edge floor{" "}
        {thresholds.tail_guard_edge_min_bps} bps · readiness conf ≥{" "}
        {thresholds.readiness_strong_confidence} & n ≥{" "}
        {thresholds.readiness_strong_min_n}
      </div>
    </div>
  );
}
