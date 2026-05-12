// Phase Opt-A — Options Diagnostics card.
//
// Truth dump in plain English. Reads /api/options/pipeline-status
// and renders a key-value grid showing exactly what's wired and
// what's stale / missing. No graph, no chart, no drama.

import { useOptionsPipelineStatus } from "@/lib/options/hooks";
import { cn } from "@/lib/cn";


function fmtTs(iso: string | null): string {
  if (!iso) return "never";
  return new Date(iso).toLocaleString();
}


function ageDays(iso: string | null): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  return Math.floor((Date.now() - t) / 86_400_000);
}


function staleClass(iso: string | null, freshDays: number = 1): string {
  const age = ageDays(iso);
  if (age == null) return "is-warn";
  return age > freshDays ? "is-warn" : "is-pos";
}


function KV({
  k, v, tone,
}: { k: string; v: string; tone?: "pos" | "neg" | "warn" | "neutral" | "" }) {
  return (
    <div className="opt-diag-kv">
      <span className="opt-diag-k">{k}</span>
      <span className={cn("opt-diag-v", tone && `is-${tone}`)}>{v}</span>
    </div>
  );
}


export default function OptionsDiagnosticsCard() {
  const { data, isLoading, isError } = useOptionsPipelineStatus();

  if (isLoading || !data) {
    return (
      <section className="u-card opt-card" data-test="options-diagnostics">
        <header className="opt-card-header">
          <span className="opt-card-eyebrow">Diagnostics</span>
        </header>
        <p className="opt-empty-body">loading…</p>
      </section>
    );
  }

  if (isError) {
    return (
      <section className="u-card opt-card" data-test="options-diagnostics">
        <header className="opt-card-header">
          <span className="opt-card-eyebrow">Diagnostics</span>
          <span className="opt-card-meta is-warn">unreachable</span>
        </header>
        <p className="opt-empty-body">
          /api/options/pipeline-status did not respond.
        </p>
      </section>
    );
  }

  const chainStale = staleClass(data.options_chain_snapshot_max_ts, 1);
  const shadowStale = staleClass(data.options_shadow_decision_max_date, 1);
  const paperStale = staleClass(data.options_paper_trade_max_ts, 30);
  const outcomeStale = staleClass(data.options_strategy_outcome_max_ts, 7);

  return (
    <section className="u-card opt-card" data-test="options-diagnostics">
      <header className="opt-card-header">
        <span className="opt-card-eyebrow">Diagnostics</span>
        <span className="opt-card-meta">
          read-only · refreshes every 60s
        </span>
      </header>

      {/* Master flag truths */}
      <div className="opt-diag-section">
        <div className="opt-diag-section-label">Configuration</div>
        <div className="opt-diag-grid">
          <KV k="OPTIONS_ENABLED"
              v={data.options_enabled ? "true" : "false"}
              tone={data.options_enabled ? "pos" : "warn"} />
          <KV k="OPTIONS_PAPER_ONLY"
              v={data.options_paper_only ? "true (locked)" : "false"}
              tone={data.options_paper_only ? "pos" : "neg"} />
          <KV k="OPTIONS_SHADOW_EVAL_ENABLED"
              v={data.options_shadow_eval_enabled ? "true" : "false"}
              tone={data.options_shadow_eval_enabled ? "pos" : "neutral"} />
          <KV k="OPTIONS_ML_CAN_AFFECT_TRADES"
              v={data.options_ml_can_affect_trades ? "true" : "false (locked)"}
              tone={data.options_ml_can_affect_trades ? "warn" : "pos"} />
        </div>
      </div>

      {/* Scheduler wiring */}
      <div className="opt-diag-section">
        <div className="opt-diag-section-label">Scheduler wiring</div>
        <div className="opt-diag-grid">
          <KV k="job_schedule rows (options)"
              v={String(data.scheduler_jobs_count)}
              tone={data.scheduler_jobs_count > 0 ? "pos" : "warn"} />
        </div>
      </div>

      {/* Chain ingest */}
      <div className="opt-diag-section">
        <div className="opt-diag-section-label">Chain ingest</div>
        <div className="opt-diag-grid">
          <KV k="Total snapshots"
              v={String(data.options_chain_snapshot_count)} />
          <KV k="Latest snapshot"
              v={fmtTs(data.options_chain_snapshot_max_ts)}
              tone={chainStale === "is-pos" ? "pos" : "warn"} />
        </div>
      </div>

      {/* Shadow eval */}
      <div className="opt-diag-section">
        <div className="opt-diag-section-label">Shadow evaluator</div>
        <div className="opt-diag-grid">
          <KV k="Total decisions"
              v={String(data.options_shadow_decision_count)} />
          <KV k="Distinct run dates"
              v={String(data.options_shadow_distinct_runs)} />
          <KV k="Latest run date"
              v={data.options_shadow_decision_max_date ?? "never"}
              tone={shadowStale === "is-pos" ? "pos" : "warn"} />
        </div>
      </div>

      {/* Paper trades */}
      <div className="opt-diag-section">
        <div className="opt-diag-section-label">Paper trades</div>
        <div className="opt-diag-grid">
          <KV k="Total trades"
              v={String(data.options_paper_trade_count)} />
          <KV k="Latest trade"
              v={fmtTs(data.options_paper_trade_max_ts)}
              tone={paperStale === "is-pos" ? "pos" : "warn"} />
        </div>
      </div>

      {/* Strategy outcomes */}
      <div className="opt-diag-section">
        <div className="opt-diag-section-label">Strategy outcomes</div>
        <div className="opt-diag-grid">
          <KV k="Total outcomes"
              v={String(data.options_strategy_outcome_count)} />
          <KV k="Latest outcome"
              v={fmtTs(data.options_strategy_outcome_max_ts)}
              tone={outcomeStale === "is-pos" ? "pos" : "warn"} />
        </div>
      </div>
    </section>
  );
}
