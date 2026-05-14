// Phase 6b-3-i — Declared configuration (universe + provider + thresholds).
//
// Read-only single section combining what governs the engine's
// observable space:
//   - configured universe of underlyings
//   - active data provider (and the production whitelist)
//   - max chain age (freshness bound)
//   - scheduler row count
//
// Per the queued direction:
//   "Universe + provider transparency matter. These are core
//    epistemological boundaries."

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


interface IntegrityShape {
  active_batch: null | {
    provider:         string;
    provider_version: string;
  };
  thresholds: {
    max_run_chain_age_hours: number;
    production_providers:    string[];
    run_universe:            string[];
  };
}

interface SchedulerShape {
  count: number;
  rows: Array<{ name: string; cron_expr: string }>;
}


export default function OptionsDeclaredConfig() {
  const { data: integ } = useQuery<IntegrityShape>({
    queryKey: ["options", "analytics", "integrity"],
    queryFn:  () => apiGet("/options/analytics/integrity"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });
  const { data: sched } = useQuery<SchedulerShape>({
    queryKey: ["options", "analytics", "scheduler-rows"],
    queryFn:  () => apiGet("/options/analytics/scheduler-rows"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });

  const universe = integ?.thresholds?.run_universe ?? [];
  const productionProviders = integ?.thresholds?.production_providers ?? [];
  const maxAgeHours = integ?.thresholds?.max_run_chain_age_hours ?? 24;
  const activeProvider = integ?.active_batch?.provider_version ?? "—";

  return (
    <section
      className="u-card opt-settings-declared"
      data-test="options-declared-config"
    >
      <header className="opt-card-header" style={{ marginBottom: 16 }}>
        <span className="opt-card-eyebrow">Declared configuration</span>
        <span className="opt-card-meta">read-only · v1 frozen</span>
      </header>

      <dl className="opt-declared-list">

        <div className="opt-declared-row">
          <dt className="opt-declared-key">Universe</dt>
          <dd className="opt-declared-val">
            <div className="opt-declared-val-primary">
              {universe.length} underlying{universe.length === 1 ? "" : "s"}
              {" "}authorized for evaluation
            </div>
            <div className="opt-declared-val-list">
              {universe.join(" · ")}
            </div>
          </dd>
        </div>

        <div className="opt-declared-row">
          <dt className="opt-declared-key">Active provider</dt>
          <dd className="opt-declared-val">
            <div className="opt-declared-val-primary">
              {activeProvider}
            </div>
            <div className="opt-declared-val-list">
              production whitelist · {productionProviders.join(" · ")}
            </div>
          </dd>
        </div>

        <div className="opt-declared-row">
          <dt className="opt-declared-key">Freshness bound</dt>
          <dd className="opt-declared-val">
            <div className="opt-declared-val-primary">
              chain batch must be ≤ {maxAgeHours} h old
            </div>
            <div className="opt-declared-val-list">
              live age computed via NOW() − snapshot_at_utc
            </div>
          </dd>
        </div>

        <div className="opt-declared-row">
          <dt className="opt-declared-key">Scheduler</dt>
          <dd className="opt-declared-val">
            <div className="opt-declared-val-primary">
              {sched?.count ?? 0} authorized job
              {sched?.count === 1 ? "" : "s"}
            </div>
            <div className="opt-declared-val-list">
              {(sched?.rows ?? []).map(r =>
                `${r.name} (${r.cron_expr})`).join(" · ") || "—"}
            </div>
          </dd>
        </div>

      </dl>
    </section>
  );
}
