// Phase 6b-3-g — Health triage matrix.
//
// 5 trust primitives. Each row: name + status + observed value.
// Calm-by-default: when all pass, the matrix renders muted; when
// anything fails, the failing rows become the only visual emphasis.
//
// Per the queued direction:
//   "Healthy systems should visually recede."
//   "Triage-oriented hierarchy: Is anything unhealthy? before
//    show me all telemetry."

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


interface IntegrityShape {
  coherent_batch_present:    boolean;
  provider_homogeneous:      boolean;
  universe_closure_pass:     boolean;
  freshness_bound_pass:      boolean;
  shadow_persistence_active: boolean;
  active_batch: null | {
    provider:         string;
    provider_version: string;
    age_hours:        number;
  };
  today_underlying_count:        number;
  today_out_of_universe_count:   number;
  today_provider_version_count:  number;
  thresholds: {
    max_run_chain_age_hours: number;
    run_universe:            string[];
  };
}


interface CheckRow {
  name:     string;
  pass:     boolean;
  observed: string;
}


function _checks(i: IntegrityShape): CheckRow[] {
  return [
    {
      name:     "Coherent batch",
      pass:     i.coherent_batch_present,
      observed: i.active_batch
        ? `${i.active_batch.provider}/${i.active_batch.provider_version}`
        : "no batch",
    },
    {
      name:     "Freshness bound",
      pass:     i.freshness_bound_pass,
      observed: i.active_batch
        ? `${i.active_batch.age_hours.toFixed(1)} h of ` +
          `${i.thresholds.max_run_chain_age_hours} h`
        : "—",
    },
    {
      name:     "Provider homogeneous",
      pass:     i.provider_homogeneous,
      observed: `${i.today_provider_version_count} version` +
                `${i.today_provider_version_count === 1 ? "" : "s"} today`,
    },
    {
      name:     "Universe closure",
      pass:     i.universe_closure_pass,
      observed: i.universe_closure_pass
        ? `${i.thresholds.run_universe.length}/` +
          `${i.thresholds.run_universe.length} ETFs in scope`
        : `${i.today_out_of_universe_count.toLocaleString()} ` +
          `out-of-universe rows`,
    },
    {
      name:     "Shadow persistence",
      pass:     i.shadow_persistence_active,
      observed: i.shadow_persistence_active ? "active" : "paused",
    },
  ];
}


export default function OptionsHealthTriage() {
  const { data, isLoading } = useQuery<IntegrityShape>({
    queryKey: ["options", "analytics", "integrity"],
    queryFn:  () => apiGet("/options/analytics/integrity"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });

  if (isLoading || !data) {
    return (
      <section className="u-card opt-ops-health">
        <div className="u-label">HEALTH</div>
        <p className="u-body" style={{ color: "var(--fg-3)" }}>
          loading…
        </p>
      </section>
    );
  }

  const rows = _checks(data);
  const failing = rows.filter(r => !r.pass);

  return (
    <section
      className="u-card opt-ops-health"
      data-test="options-health-triage"
      data-failing={failing.length > 0 ? "true" : "false"}
    >
      <header className="opt-card-header" style={{ marginBottom: 12 }}>
        <span className="opt-card-eyebrow">Health</span>
        <span className="opt-card-meta">
          {failing.length === 0
            ? "all five checks pass"
            : `${failing.length} of 5 failing`}
        </span>
      </header>

      <ul className="opt-ops-health-list">
        {rows.map((r) => (
          <li
            key={r.name}
            className="opt-ops-health-row"
            data-pass={r.pass ? "true" : "false"}
          >
            <span className="opt-ops-health-mark" aria-hidden>
              {r.pass ? "·" : "!"}
            </span>
            <span className="opt-ops-health-name">{r.name}</span>
            <span className="opt-ops-health-observed">{r.observed}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
