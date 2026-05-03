// Phase ML-2.6 — compact readiness card. No redesign.

import { useReplayReadiness } from "@/lib/replay/readiness";
import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

export default function ReplayTrainingReadinessCard() {
  const { data } = useReplayReadiness();

  if (!data) {
    return (
      <div className="u-card">
        <Label>Replay Training Readiness</Label>
        <div className="u-caption-2 mt-2">Loading…</div>
      </div>
    );
  }

  const tone = statusTone(data.status);
  const cov = data.coverage_summary ?? {};
  const val = data.validation_summary ?? {};
  const lk  = data.leakage_summary ?? {};

  return (
    <div className="u-card">
      <div className="flex items-center justify-between mb-3">
        <div>
          <Label>Replay Training Readiness</Label>
          <div className="u-caption-2 mt-0.5">
            ML-2.6 gate · advisory only
          </div>
        </div>
        <span className={cn("u-chip", tone)}>
          {data.status.split("_").join(" ").toLowerCase()}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-2 mb-3">
        <KV k="Symbol-month cov"
            v={pct(cov.pct_symbol_month_coverage)} />
        <KV k="known_at cov"
            v={pct(cov.pct_known_at_coverage)} />
        <KV k="Comparable"
            v={`${val.comparable_decisions ?? 0}`} />
        <KV k="Action agree"
            v={pct(val.action_agreement_rate)} />
        <KV k="Leakage"
            v={lk.ok ? "clean" : "violations"}
            tone={lk.ok ? "pos" : "neg"} />
        <KV k="Tier"
            v={cov.global_quality_tier ?? "—"} />
      </div>

      {data.recommended_next_action && (
        <div className="u-card-tight mb-3"
             style={{ background: "var(--accent-subtle)",
                      borderColor: "rgba(75,139,255,0.3)" }}>
          <div className="u-label-sm mb-1">Recommendation</div>
          <div className="u-caption text-fg leading-relaxed">
            {data.recommended_next_action}
          </div>
        </div>
      )}

      {data.blockers.length > 0 && (
        <div>
          <div className="u-label-sm mb-1.5">Blockers</div>
          <ul className="space-y-1">
            {data.blockers.slice(0, 3).map((b, i) => (
              <li key={i} className="u-caption-2 flex items-start gap-2">
                <span className="text-warning shrink-0">!</span>
                <span>{b}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3 flex gap-4">
        <a className="u-caption text-accent hover:underline"
           href="/api/catalysts/backfill/runs"
           target="_blank" rel="noreferrer">
          backfill runs
        </a>
        <a className="u-caption text-accent hover:underline"
           href="/api/ml/replay/training-readiness"
           target="_blank" rel="noreferrer">
          full readiness
        </a>
      </div>
    </div>
  );
}

function KV({ k, v, tone = "neutral" }: {
  k: string; v: string; tone?: "pos" | "neg" | "neutral";
}) {
  const cls = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger" : "text-fg";
  return (
    <div className="flex items-center justify-between">
      <span className="u-caption text-fg-2">{k}</span>
      <span className={cn("u-mono-sm font-semibold", cls)}>{v}</span>
    </div>
  );
}

function pct(v: number | undefined): string {
  if (v === undefined || v === null) return "—";
  return `${(v * 100).toFixed(0)}%`;
}

function statusTone(s: string): string {
  if (s === "READY_FOR_WEIGHTED_TEST")    return "u-chip-success";
  if (s === "CALIBRATION_ONLY")           return "u-chip-accent";
  if (s === "NOT_READY_LEAKAGE_RISK")     return "u-chip-danger";
  if (s?.startsWith("NOT_READY"))         return "u-chip-warning";
  return "u-chip-neutral";
}
