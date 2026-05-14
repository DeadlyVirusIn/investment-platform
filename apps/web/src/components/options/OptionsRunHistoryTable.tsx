// Phase 6b-3-g — Recent job_run history (read-only).
//
// 4 real rows today. Renders as-is.

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


interface JobRunsResponse {
  limit: number;
  count: number;
  rows: Array<{
    id:               string;
    name:             string;
    status:           string;
    started_at:       string | null;
    finished_at:      string | null;
    duration_seconds: number | null;
    error_message:    string | null;
  }>;
}


function _humanTs(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}


function _humanDuration(s: number | null): string {
  if (s === null) return "—";
  if (s < 1) return `${Math.round(s * 1000)} ms`;
  if (s < 60) return `${s.toFixed(2)} s`;
  return `${Math.floor(s / 60)} m ${Math.round(s % 60)} s`;
}


export default function OptionsRunHistoryTable() {
  const { data, isLoading } = useQuery<JobRunsResponse>({
    queryKey: ["options", "analytics", "job-runs", 10],
    queryFn:  () => apiGet("/options/analytics/job-runs?limit=10"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });

  return (
    <section
      className="u-card opt-ops-runs"
      data-test="options-run-history-table"
    >
      <header className="opt-card-header" style={{ marginBottom: 12 }}>
        <span className="opt-card-eyebrow">Recent runs</span>
        <span className="opt-card-meta">
          {isLoading
            ? "loading…"
            : `${data?.count ?? 0} fire${data?.count === 1 ? "" : "s"} on record`}
        </span>
      </header>

      {!isLoading && (data?.rows ?? []).length === 0 && (
        <p className="u-body" style={{ color: "var(--fg-3)" }}>
          No options jobs have fired yet.
        </p>
      )}

      {(data?.rows ?? []).length > 0 && (
        <table className="opt-ops-table" role="table">
          <thead>
            <tr>
              <th scope="col">Started</th>
              <th scope="col">Job</th>
              <th scope="col">Status</th>
              <th scope="col">Duration</th>
              <th scope="col">Error</th>
            </tr>
          </thead>
          <tbody>
            {data!.rows.map((r) => (
              <tr key={r.id}>
                <td className="opt-ops-table-mono">
                  {_humanTs(r.started_at)}
                </td>
                <td className="opt-ops-table-name">{r.name}</td>
                <td>
                  <span
                    className={
                      r.status === "success"
                        ? "opt-ops-pill opt-ops-pill-ok"
                        : r.status === "running"
                          ? "opt-ops-pill opt-ops-pill-running"
                          : "opt-ops-pill opt-ops-pill-fail"
                    }
                  >
                    {r.status}
                  </span>
                </td>
                <td className="opt-ops-table-mono">
                  {_humanDuration(r.duration_seconds)}
                </td>
                <td className="opt-ops-table-error">
                  {r.error_message
                    ? <code>{r.error_message.slice(0, 80)}</code>
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
