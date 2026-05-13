// Phase Opt-C1 Step 11 — Lifecycle timeline component.
//
// Reads the new GET /api/options/trades/{id}/lifecycle endpoint.
// Renders a horizontal timeline with state nodes + a full event
// log table. Audit-grade — every event shows source + timestamp +
// reason code from the Opt-B2 sole-writer payload.

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


interface LifecycleEvent {
  id: number;
  event_type: string;
  event_at_utc: string | null;
  triggered_by: string;
  payload: Record<string, unknown>;
}


interface LifecycleResponse {
  trade_id: number;
  found: boolean;
  current_status: string | null;
  underlying?: string;
  strategy_name?: string;
  opened_at?: string | null;
  closed_at?: string | null;
  proposal_hash?: string | null;
  events: LifecycleEvent[];
}


function useLifecycle(trade_id: number | null) {
  return useQuery<LifecycleResponse>({
    queryKey: ["options", "trade-lifecycle", trade_id],
    queryFn: () => apiGet<LifecycleResponse>(`/options/trades/${trade_id}/lifecycle`),
    enabled: trade_id !== null,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}


function _fmtTs(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${m}/${day} ${hh}:${mm}`;
}


function _reasonOf(p: Record<string, unknown>): string | null {
  const r = p.reason;
  return typeof r === "string" ? r : null;
}


export default function OptionsLifecycleTimeline({ trade_id }: { trade_id: number | null }) {
  const { data, isLoading, isError } = useLifecycle(trade_id);

  if (trade_id === null) return null;

  if (isLoading || !data) {
    return (
      <section className="u-card opt-card" data-test="options-lifecycle-timeline">
        <header className="opt-card-header">
          <span className="opt-card-eyebrow">Trade lifecycle</span>
        </header>
        <p className="opt-empty-body">loading…</p>
      </section>
    );
  }

  if (isError || !data.found) {
    return (
      <section className="u-card opt-card" data-test="options-lifecycle-timeline">
        <header className="opt-card-header">
          <span className="opt-card-eyebrow">Trade lifecycle</span>
          <span className="opt-card-meta is-warn">trade not found</span>
        </header>
        <p className="opt-empty-body">
          No trade with id {trade_id} in the paper journal.
        </p>
      </section>
    );
  }

  const { current_status, events, underlying, strategy_name,
          opened_at, closed_at, proposal_hash } = data;

  return (
    <section className="u-card opt-card" data-test="options-lifecycle-timeline">
      <header className="opt-card-header">
        <span className="opt-card-eyebrow">
          Trade lifecycle · #{trade_id}
        </span>
        <span className="opt-card-meta">
          {underlying} {strategy_name} · current {current_status?.toLowerCase()}
        </span>
      </header>

      {/* Provenance row */}
      <div className="opt-lifecycle-prov">
        <div>
          <span className="opt-lifecycle-prov-k">opened</span>
          <span className="opt-lifecycle-prov-v">{_fmtTs(opened_at)}</span>
        </div>
        <div>
          <span className="opt-lifecycle-prov-k">closed</span>
          <span className="opt-lifecycle-prov-v">{_fmtTs(closed_at)}</span>
        </div>
        <div>
          <span className="opt-lifecycle-prov-k">proposal hash</span>
          <span className="opt-lifecycle-prov-v opt-lifecycle-prov-mono">
            {proposal_hash ? proposal_hash.slice(0, 12) + "…" : "—"}
          </span>
        </div>
      </div>

      {/* Event log */}
      {events.length === 0 && (
        <div className="opt-empty">
          <p className="opt-empty-headline">No lifecycle events yet.</p>
          <p className="opt-empty-body">
            The first event arrives on FILL transition (Opt-B3 paper exec
            wires the lifecycle calls into the daily runner).
          </p>
        </div>
      )}

      {events.length > 0 && (
        <table className="opt-lifecycle-events">
          <thead>
            <tr>
              <th>When</th><th>Event</th><th>Source</th><th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id} data-event-type={e.event_type}>
                <td className="opt-lifecycle-events-when">
                  {_fmtTs(e.event_at_utc)}
                </td>
                <td>
                  <span
                    className="opt-lifecycle-events-type"
                    data-event-type={e.event_type}
                  >
                    {e.event_type}
                  </span>
                </td>
                <td className="opt-lifecycle-events-src">{e.triggered_by}</td>
                <td className="opt-lifecycle-events-reason">
                  {_reasonOf(e.payload) ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
