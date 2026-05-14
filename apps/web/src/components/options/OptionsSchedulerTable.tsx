// Phase 6b-3-g — Scheduler row table (read-only).
//
// 2 real rows today. Renders as-is; no inflation.

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


interface SchedulerRowsResponse {
  count: number;
  rows: Array<{
    name:        string;
    cron_expr:   string;
    enabled:     boolean;
    next_run_at: string | null;
    last_run_at: string | null;
  }>;
}


function _humanTs(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    timeZoneName: "short",
  });
}


export default function OptionsSchedulerTable() {
  const { data, isLoading } = useQuery<SchedulerRowsResponse>({
    queryKey: ["options", "analytics", "scheduler-rows"],
    queryFn:  () => apiGet("/options/analytics/scheduler-rows"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });

  return (
    <section
      className="u-card opt-ops-scheduler"
      data-test="options-scheduler-table"
    >
      <header className="opt-card-header" style={{ marginBottom: 12 }}>
        <span className="opt-card-eyebrow">Scheduler</span>
        <span className="opt-card-meta">
          {isLoading
            ? "loading…"
            : `${data?.count ?? 0} row${data?.count === 1 ? "" : "s"}`}
        </span>
      </header>

      {!isLoading && (data?.rows ?? []).length === 0 && (
        <p className="u-body" style={{ color: "var(--fg-3)" }}>
          No options scheduler rows registered.
        </p>
      )}

      {(data?.rows ?? []).length > 0 && (
        <table className="opt-ops-table" role="table">
          <thead>
            <tr>
              <th scope="col">Job</th>
              <th scope="col">Cron</th>
              <th scope="col">Enabled</th>
              <th scope="col">Next fire</th>
              <th scope="col">Last fire</th>
            </tr>
          </thead>
          <tbody>
            {data!.rows.map((r) => (
              <tr key={r.name}>
                <td className="opt-ops-table-name">{r.name}</td>
                <td className="opt-ops-table-mono">{r.cron_expr}</td>
                <td>
                  <span
                    className={
                      r.enabled
                        ? "opt-ops-pill opt-ops-pill-on"
                        : "opt-ops-pill opt-ops-pill-off"
                    }
                  >
                    {r.enabled ? "yes" : "no"}
                  </span>
                </td>
                <td className="opt-ops-table-mono">
                  {_humanTs(r.next_run_at)}
                </td>
                <td className="opt-ops-table-mono">
                  {_humanTs(r.last_run_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
