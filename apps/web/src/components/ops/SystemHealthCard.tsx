// Phase SYSTEM-ALPHA — System Health Score card.

import { useSystemHealthScore } from "@/lib/alpha/hooks";
import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

export default function SystemHealthCard() {
  const { data } = useSystemHealthScore();
  if (!data) {
    return (
      <div className="u-card">
        <Label>System Health Score</Label>
        <div className="u-caption-2 mt-2">Loading…</div>
      </div>
    );
  }

  const score = data.overall ?? data.computed?.overall ?? 0;
  const comps = data.components ?? data.computed ?? {};
  const rec = data.recommendation ?? data.computed?.recommendation ?? "";
  const warns = data.warnings ?? data.computed?.warnings ?? [];
  const tone = score >= 75 ? "u-chip-success"
    : score >= 55 ? "u-chip-accent"
    : score >= 40 ? "u-chip-warning" : "u-chip-danger";

  return (
    <div className="u-card">
      <div className="flex items-center justify-between mb-3">
        <div>
          <Label>System Health Score</Label>
          <div className="u-caption-2 mt-0.5">
            Phase SYSTEM-ALPHA · advisory
          </div>
        </div>
        <span className={cn("u-chip", tone)}>{score}/100</span>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-2 mb-3">
        <Row k="Data quality"     v={comps.data_quality} />
        <Row k="Signal quality"   v={comps.signal_quality} />
        <Row k="Catalyst coverage" v={comps.catalyst_coverage} />
        <Row k="Execution"        v={comps.execution_quality} />
        <Row k="Risk control"     v={comps.risk_control} />
        <Row k="ML readiness"     v={comps.ml_readiness} />
      </div>

      {rec && (
        <div className="u-card-tight mb-2"
             style={{ background: "var(--accent-subtle)",
                      borderColor: "rgba(75,139,255,0.25)" }}>
          <div className="u-label-sm mb-1">Recommendation</div>
          <div className="u-caption text-fg leading-relaxed">{rec}</div>
        </div>
      )}

      {warns.length > 0 && (
        <div>
          <div className="u-label-sm mb-1.5">Warnings</div>
          <ul className="space-y-1">
            {warns.slice(0, 3).map((w: string, i: number) => (
              <li key={i} className="u-caption-2 flex items-start gap-2">
                <span className="text-warning shrink-0">!</span>
                <span>{w}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v?: number }) {
  const val = v ?? 0;
  const tone = val >= 70 ? "text-success"
    : val >= 50 ? "text-fg"
    : val >= 30 ? "text-warning" : "text-danger";
  return (
    <div className="flex items-center justify-between">
      <span className="u-caption text-fg-2">{k}</span>
      <span className={cn("u-mono-sm font-semibold", tone)}>
        {val ? `${val}` : "—"}
      </span>
    </div>
  );
}
