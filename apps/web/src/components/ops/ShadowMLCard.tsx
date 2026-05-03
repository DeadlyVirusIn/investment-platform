// Phase ML-3 — compact Shadow ML admin card.

import { useShadowLatestReport } from "@/lib/ml/shadow";
import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

export default function ShadowMLCard() {
  const { data } = useShadowLatestReport();

  if (!data?.present || !data.latest_model_run) {
    return (
      <div className="u-card">
        <Label>Shadow ML Status</Label>
        <div className="u-caption-2 mt-2">
          No shadow runs yet. Trigger via{" "}
          <code className="u-mono-sm">
            python -m apps.api.src.jobs.nightly_ml_shadow
          </code>.
        </div>
      </div>
    );
  }

  const r = data.latest_model_run;
  const tone = statusTone(r.status);
  const cmp = r.baseline_comparison;
  const cal = r.calibration;
  const counts = data.prediction_counts;

  return (
    <div className="u-card">
      <div className="flex items-center justify-between mb-3">
        <div>
          <Label>Shadow ML Status</Label>
          <div className="u-caption-2 mt-0.5">
            {new Date(r.created_at).toLocaleString()} ·{" "}
            <code className="u-mono-sm">{r.model_type}</code> · source{" "}
            {r.dataset_source}
          </div>
        </div>
        <span className={cn("u-chip", tone)}>
          {r.status.split("_").join(" ").toLowerCase()}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-2 mb-3">
        <KV k="Rows used" v={`${r.row_count}`} />
        <KV k="Labeled"    v={`${r.labeled_row_count}`} />
        <KV k="Winner"     v={cmp?.winner ?? "—"}
            tone={cmp?.winner === "ml" ? "pos"
                   : cmp?.winner === "baseline" ? "neg" : "neutral"} />
        <KV k="Δ Sharpe"   v={fmtNum(cmp?.delta_sharpe)} />
        <KV k="Best baseline"
            v={cmp?.baselines_best?.name
                ? `${cmp.baselines_best.name} (${fmtNum(
                    cmp.baselines_best.sharpe_proxy,
                  )})`
                : "—"} />
        <KV k="ECE"
            v={fmtNum(cal?.ece)}
            tone={cal?.poor_calibration ? "warn" : "neutral"} />
      </div>

      {counts && (
        <div className="u-card-tight mb-3"
             style={{ background: "var(--accent-subtle)",
                      borderColor: "rgba(75,139,255,0.25)" }}>
          <div className="u-label-sm mb-1">Shadow predictions</div>
          <div className="u-caption text-fg">
            {counts.n ?? 0} total · accept {counts.n_accept ?? 0} · avoid{" "}
            {counts.n_avoid ?? 0} · reduce {counts.n_reduce ?? 0} · needs{" "}
            {counts.n_needs ?? 0}
          </div>
        </div>
      )}

      {r.blockers && r.blockers.length > 0 && (
        <div>
          <div className="u-label-sm mb-1.5">Blockers</div>
          <ul className="space-y-1">
            {r.blockers.slice(0, 3).map((b, i) => (
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
           href="/api/ml/shadow/latest-report" target="_blank"
           rel="noreferrer">
          latest report
        </a>
        <a className="u-caption text-accent hover:underline"
           href="/api/ml/shadow/predictions?limit=50" target="_blank"
           rel="noreferrer">
          recent predictions
        </a>
      </div>
    </div>
  );
}

function KV({ k, v, tone = "neutral" }: {
  k: string; v: string;
  tone?: "pos" | "neg" | "warn" | "neutral";
}) {
  const cls = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger"
    : tone === "warn" ? "text-warning" : "text-fg";
  return (
    <div className="flex items-center justify-between">
      <span className="u-caption text-fg-2">{k}</span>
      <span className={cn("u-mono-sm font-semibold", cls)}>{v}</span>
    </div>
  );
}

function fmtNum(v: number | undefined): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  return v.toFixed(3);
}

function statusTone(s: string): string {
  if (s === "SHADOW_OUTPERFORMING")      return "u-chip-success";
  if (s === "TRAINED_SHADOW")            return "u-chip-accent";
  if (s === "TRAINED_BUT_BELOW_BASELINE") return "u-chip-warning";
  if (s === "TRAINED_BUT_UNCALIBRATED")   return "u-chip-warning";
  if (s === "SKIPPED_LEAKAGE_RISK")       return "u-chip-danger";
  if (s.startsWith("SKIPPED"))           return "u-chip-neutral";
  return "u-chip-neutral";
}
