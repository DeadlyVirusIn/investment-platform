// Phase ML-6 — Hybrid ML Readiness (promotion guard + window metrics).

import { usePromotionStatus } from "@/lib/ml/shadow";
import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

export default function HybridReadinessCard() {
  const { data, isLoading } = usePromotionStatus();

  if (isLoading || !data) {
    return (
      <div className="u-card">
        <Label>Hybrid ML Readiness</Label>
        <div className="u-caption-2 mt-2">loading…</div>
      </div>
    );
  }

  const p = data.promotion;
  const w7 = data.windows["7"];
  const w14 = data.windows["14"];
  const w30 = data.windows["30"];
  const stateTone = _stateTone(p.state);

  return (
    <div className="u-card">
      <div className="flex items-center justify-between mb-3">
        <div>
          <Label>Hybrid ML Readiness</Label>
          <div className="u-caption-2 mt-0.5">
            mode {data.current_mode} ·{" "}
            {p.healthy_day_count != null
              ? `${p.healthy_day_count}/${data.thresholds.required_healthy_days} healthy days`
              : "no history"}
          </div>
        </div>
        <span className={cn("u-chip", stateTone)}>
          {p.state.replace(/_/g, " ").toLowerCase()}
        </span>
      </div>

      {/* Windows table */}
      <div className="mb-3">
        <div className="u-label-sm mb-1.5">Rolling Windows</div>
        <div className="overflow-x-auto">
          <table className="w-full u-caption-2">
            <thead className="text-fg-3">
              <tr>
                <th className="text-left py-1">window</th>
                <th className="text-right py-1">advice</th>
                <th className="text-right py-1">closed</th>
                <th className="text-right py-1">avoided</th>
                <th className="text-right py-1">missed</th>
                <th className="text-right py-1">false-avoid</th>
                <th className="text-right py-1">Δ Sharpe</th>
                <th className="text-right py-1">ECE</th>
              </tr>
            </thead>
            <tbody className="u-mono-sm">
              <Row w={w7}  label="7d" />
              <Row w={w14} label="14d" />
              <Row w={w30} label="30d" />
            </tbody>
          </table>
        </div>
      </div>

      {/* Recommendation */}
      <div className="u-card-tight mb-3"
           style={{ background: "var(--accent-subtle)",
                    borderColor: "rgba(75,139,255,0.25)" }}>
        <div className="u-caption text-fg font-medium">
          {p.recommendation}
        </div>
        {p.reasons?.length > 0 && (
          <div className="u-caption-2 text-fg-3 mt-1">
            {p.reasons[0]}
          </div>
        )}
      </div>

      {/* Blockers */}
      {p.blockers.length > 0 && (
        <div>
          <div className="u-label-sm mb-1.5">Blockers</div>
          <ul className="space-y-1">
            {p.blockers.slice(0, 3).map((b, i) => (
              <li key={i} className="u-caption-2 flex items-start gap-2">
                <span className="text-warning shrink-0">!</span>
                <span>{b}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Operator note */}
      <div className="u-caption-2 text-fg-3 mt-3 italic">
        {p.operator_approval_required
          ? "Operator approval required — guard never flips mode automatically."
          : "Operator approval disabled in config."}
      </div>
    </div>
  );
}


function Row({ w, label }: {
  w: import("@/lib/ml/shadow").HybridWindow | undefined; label: string;
}) {
  if (!w) {
    return (
      <tr className="text-fg-3">
        <td className="py-1">{label}</td>
        <td colSpan={7} className="text-right italic">—</td>
      </tr>
    );
  }
  return (
    <tr>
      <td className="py-1 text-fg">{label}</td>
      <td className="text-right">{w.ml_advice_count}</td>
      <td className="text-right">{w.deterministic_trades}</td>
      <td className="text-right">
        {w.avoided_loss_estimate != null
          ? w.avoided_loss_estimate.toFixed(2)
          : "—"}
      </td>
      <td className="text-right">
        {w.missed_winner_estimate != null
          ? w.missed_winner_estimate.toFixed(2)
          : "—"}
      </td>
      <td className="text-right">
        {w.false_avoid_rate != null
          ? (w.false_avoid_rate * 100).toFixed(0) + "%"
          : "—"}
      </td>
      <td className={cn("text-right",
        w.delta_sharpe_vs_deterministic != null
          && w.delta_sharpe_vs_deterministic > 0 ? "text-success"
          : w.delta_sharpe_vs_deterministic != null
            && w.delta_sharpe_vs_deterministic < 0 ? "text-danger"
          : "text-fg-3")}>
        {w.delta_sharpe_vs_deterministic != null
          ? w.delta_sharpe_vs_deterministic.toFixed(3)
          : "—"}
      </td>
      <td className="text-right">
        {w.calibration_ece != null ? w.calibration_ece.toFixed(3) : "—"}
      </td>
    </tr>
  );
}


function _stateTone(s: string): string {
  if (s === "READY_FOR_PAPER_REDUCE") return "u-chip-success";
  if (s === "ADVISORY_HEALTHY")        return "u-chip-accent";
  if (s === "PAPER_REDUCE_PAUSED")     return "u-chip-warning";
  if (s.startsWith("NOT_READY_HIGH"))  return "u-chip-warning";
  if (s.startsWith("NOT_READY_POOR"))  return "u-chip-warning";
  if (s.startsWith("NOT_READY_BELOW")) return "u-chip-warning";
  if (s.startsWith("NOT_READY_"))      return "u-chip-neutral";
  return "u-chip-neutral";
}
