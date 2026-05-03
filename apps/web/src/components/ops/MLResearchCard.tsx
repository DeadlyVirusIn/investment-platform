// Phase ML-2 — compact admin card for Ops page.
// Reads: /api/ml/research/snapshots/latest + engine-c-readiness.
// Never affects trading. Single u-card, no layout redesign.

import { useMLLatestSnapshot, useEngineCReadiness } from "@/lib/ml/hooks";
import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

export default function MLResearchCard() {
  const { data: snap } = useMLLatestSnapshot();
  const { data: ec } = useEngineCReadiness();

  if (!snap?.present || !snap.snapshot) {
    return (
      <div className="u-card">
        <Label>ML Research Status</Label>
        <div className="u-caption-2 mt-2">
          No snapshot yet. Run{" "}
          <code className="u-mono-sm">nightly_ml_diagnostics</code> to populate.
        </div>
      </div>
    );
  }

  const s = snap.snapshot;
  const baselineBest = _bestBaseline(s.baseline_results);
  const patternTop = _patternWarnings(s.patterns, s.warnings || []);
  const ecStatus = ec?.engine_c_ml_status ?? "unknown";
  const ecTone = ecStatusTone(ecStatus);

  return (
    <div className="u-card">
      <div className="flex items-center justify-between mb-3">
        <div>
          <Label>ML Research Status</Label>
          <div className="u-caption-2 mt-0.5">
            Snapshot {new Date(s.created_at).toLocaleString()} · tier{" "}
            <code className="u-mono-sm">{s.tier}</code>
          </div>
        </div>
        <span className={cn("u-chip", ecTone)}>
          engine_c: {ecStatus.split("_").join(" ").toLowerCase()}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-2 mb-3">
        <KV k="Rows"          v={`${s.row_count}`} />
        <KV k="Labeled"       v={`${s.labeled_row_count}`} />
        <KV k="Symbols"       v={`${s.symbol_count}`} />
        <KV k="Leakage"       v={s.leakage_clean ? "clean" : "violations"}
            tone={s.leakage_clean ? "pos" : "neg"} />
        <KV k="Best baseline" v={baselineBest} />
        <KV k="Min rows"      v={`${ec?.min_rows_required ?? "—"}`} />
      </div>

      {s.recommendation && (
        <div className="u-card-tight mb-3"
             style={{ background: "var(--accent-subtle)",
                      borderColor: "rgba(75,139,255,0.30)" }}>
          <div className="u-label-sm mb-1">Recommendation</div>
          <div className="u-caption text-fg leading-relaxed">
            {s.recommendation}
          </div>
        </div>
      )}

      {patternTop.length > 0 && (
        <div>
          <div className="u-label-sm mb-1.5">Top warnings</div>
          <ul className="space-y-1">
            {patternTop.slice(0, 3).map((w, i) => (
              <li key={i} className="u-caption-2 flex items-start gap-2">
                <span className="text-warning shrink-0">!</span>
                <span>{w}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3 flex items-center gap-4">
        <a className="u-caption text-accent hover:underline"
           href="/api/ml/research/latest-report" target="_blank" rel="noreferrer">
          view latest report
        </a>
        <a className="u-caption text-accent hover:underline"
           href="/api/ml/research/patterns" target="_blank" rel="noreferrer">
          view patterns
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

function ecStatusTone(status: string): string {
  switch (status) {
    case "ACTIVE_CANDIDATE":        return "u-chip-success";
    case "SHADOW_READY":
    case "ADVISORY_READY":          return "u-chip-accent";
    case "BASELINES_ONLY":          return "u-chip-warning";
    case "DISABLED_LEAKAGE_RISK":   return "u-chip-danger";
    case "DISABLED_INSUFFICIENT_DATA":
    default:                        return "u-chip-neutral";
  }
}

function _bestBaseline(br: Record<string, unknown> | undefined): string {
  if (!br) return "—";
  const all: Array<{ name: string; sharpe_proxy: number }> = [];
  for (const k of ["v1", "v2"]) {
    const rs = (br as any)[k];
    if (Array.isArray(rs)) {
      for (const r of rs) {
        if (r && typeof r.sharpe_proxy === "number"
            && Number.isFinite(r.sharpe_proxy)) {
          all.push({ name: r.name, sharpe_proxy: r.sharpe_proxy });
        }
      }
    }
  }
  if (all.length === 0) return "—";
  all.sort((a, b) => b.sharpe_proxy - a.sharpe_proxy);
  const top = all[0];
  return `${top.name} (${top.sharpe_proxy.toFixed(2)})`;
}

function _patternWarnings(
  patterns: Record<string, unknown> | undefined,
  warnings: string[],
): string[] {
  const out: string[] = [...warnings];
  if (patterns && typeof patterns === "object") {
    const pw = (patterns as any).pattern_warnings;
    if (Array.isArray(pw)) out.push(...pw);
  }
  return out;
}
