// Phase 11Q (post-11P) — "Pending T+1 Decisions" diagnostic.
// READ-ONLY. Table only. Banner only. NEVER mutates. NEVER triggers
// fills. NEVER changes the v1 next-bar fill model.

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

interface PendingRow {
  submitted_at: string;
  as_of_date: string;
  symbol: string;
  asset_id: string | null;
  engine: string | null;
  rule: string | null;
  kind: string;
  fill_status: string;
  reason: string;
  latest_bar_ts: string | null;
  expected_fill_run: string;
  source: string;
}

interface PendingResponse {
  as_of_date: string;
  now_utc: string;
  n_pending: number;
  pending: PendingRow[];
  summary: {
    by_kind: Record<string, number>;
    next_ingest_eta: string;
    next_paper_run_eta: string;
    artifacts_seen: string[];
  };
  fill_model_note: string;
}

export default function PendingT1Page() {
  const q = useQuery({
    queryKey: ['diagnostics', 'pending-t1'],
    queryFn: () => apiGet<PendingResponse>('/diagnostics/pending-t1'),
  });

  return (
    <div className="space-y-4 p-4">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold text-zinc-100">
          Pending T+1 Decisions
        </h1>
        <p
          className="text-xs"
          style={{ color: 'var(--color-muted)' }}
        >
          Decisions waiting for next-bar fill (T+1 model).
        </p>
      </header>

      <div
        className="rounded p-3 text-xs"
        style={{
          background: 'var(--color-warning)',
          border: '1px solid var(--color-border)',
          color: 'var(--fg)',
        }}
      >
        <strong>Read-only.</strong> v1 fill model is next-bar-open.
        Decisions submitted at time T fill at the open of the next
        available daily bar. No actions on this page.
      </div>

      {q.isLoading && (
        <p className="text-sm text-zinc-400">Loading…</p>
      )}
      {q.isError && (
        <p className="text-sm text-red-400">
          Failed to load pending T+1 decisions.
        </p>
      )}

      {q.data && (
        <>
          <div
            className="text-xs"
            style={{ color: 'var(--color-muted)' }}
          >
            as_of_date {q.data.as_of_date} ·
            n_pending={q.data.n_pending} ·
            next_ingest_eta {q.data.summary.next_ingest_eta} ·
            next_paper_run_eta {q.data.summary.next_paper_run_eta}
          </div>

          <table
            className="w-full text-xs"
            style={{ borderCollapse: 'collapse' }}
          >
            <thead>
              <tr
                style={{
                  borderBottom: '1px solid var(--color-border)',
                  color: 'var(--color-muted)',
                }}
              >
                <th className="px-2 py-1 text-right">#</th>
                <th className="px-2 py-1 text-left">submitted_at</th>
                <th className="px-2 py-1 text-left">as_of_date</th>
                <th className="px-2 py-1 text-left">symbol</th>
                <th className="px-2 py-1 text-left">engine</th>
                <th className="px-2 py-1 text-left">rule</th>
                <th className="px-2 py-1 text-left">kind</th>
                <th className="px-2 py-1 text-left">fill_status</th>
                <th className="px-2 py-1 text-left">latest_bar_ts</th>
                <th className="px-2 py-1 text-left">expected_fill_run</th>
                <th className="px-2 py-1 text-left">source</th>
              </tr>
            </thead>
            <tbody>
              {q.data.pending.length === 0 && (
                <tr>
                  <td
                    colSpan={11}
                    className="px-2 py-3 text-center text-zinc-500"
                  >
                    No pending T+1 decisions in the lookback window.
                  </td>
                </tr>
              )}
              {q.data.pending.map((row, i) => (
                <tr
                  key={`${row.submitted_at}:${row.symbol}:${row.kind}:${i}`}
                  style={{
                    borderBottom: '1px solid var(--color-border)',
                  }}
                >
                  <td className="px-2 py-1 text-right text-zinc-500">
                    {i + 1}
                  </td>
                  <td className="px-2 py-1">{row.submitted_at}</td>
                  <td className="px-2 py-1">{row.as_of_date}</td>
                  <td className="px-2 py-1 font-mono">{row.symbol}</td>
                  <td className="px-2 py-1">{row.engine ?? '—'}</td>
                  <td className="px-2 py-1">{row.rule ?? '—'}</td>
                  <td className="px-2 py-1">{row.kind}</td>
                  <td
                    className="px-2 py-1"
                    style={{ color: 'var(--color-muted)' }}
                  >
                    {row.fill_status}
                  </td>
                  <td className="px-2 py-1">
                    {row.latest_bar_ts ?? '—'}
                  </td>
                  <td className="px-2 py-1">{row.expected_fill_run}</td>
                  <td
                    className="px-2 py-1"
                    style={{ color: 'var(--color-muted)' }}
                  >
                    {row.source}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <p
            className="pt-2 text-[11px]"
            style={{ color: 'var(--color-muted)' }}
          >
            {q.data.fill_model_note}
          </p>
        </>
      )}
    </div>
  );
}
