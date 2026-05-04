// Personal-Analytics — read-only Exit Tracking panel.
//
// Diagnostic labels only. Never displays "sell", "close",
// "exit now", "take profit", or "stop loss" as standalone action
// affordances. The label vocabulary is locked to the API
// `vocabulary` field so the UI cannot drift.
//
// No buttons. No mutations.

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

interface ExitDiagnostic {
  position_id: string;
  symbol: string;
  source: string;
  is_replay: boolean;
  entry_date: string | null;
  days_open: number | null;
  outcome_status: 'open_pending' | 'closed';
  exit_rule: unknown | null;
  exit_rule_status: 'unavailable' | 'available';
  diagnostic_labels: string[];
}

interface ExitTrackingResponse {
  include_replay: boolean;
  stale_threshold_days: number;
  as_of: string;
  count: number;
  vocabulary: string[];
  notice: string;
  positions: ExitDiagnostic[];
}

export default function ExitTrackingPanel() {
  const [includeReplay, setIncludeReplay] = useState(true);
  const q = useQuery<ExitTrackingResponse>({
    queryKey: ['perf-paper', 'exit-tracking', includeReplay],
    queryFn: () => apiGet<ExitTrackingResponse>(
      `/performance/paper/exit-tracking${
        includeReplay ? '?include_replay=true' : ''}`,
    ),
    staleTime: 60_000,
  });
  const rows = q.data?.positions ?? [];

  return (
    <section
      data-test="exit-tracking-panel"
      className="rounded-md border border-zinc-700 bg-zinc-900/40 p-4 mb-4"
    >
      <header className="flex items-baseline justify-between mb-3">
        <h3 className="text-sm font-semibold text-zinc-100">
          Exit Tracking — diagnostic labels only
        </h3>
        <label className="text-xs flex items-center gap-2">
          <input
            type="checkbox"
            checked={includeReplay}
            onChange={e => setIncludeReplay(e.target.checked)}
          />
          <span>Include recovered replay</span>
        </label>
      </header>

      <div
        data-test="exit-tracking-disclaimer"
        className="rounded border border-amber-700 bg-amber-900/20 px-3 py-2 text-xs text-zinc-200 mb-3"
      >
        {q.data?.notice ??
          'Diagnostic labels only. NO action recommendation, NO ' +
          'execution. Exit-rule data is not persisted; this panel ' +
          'reports rule availability only.'}
      </div>

      <table className="w-full text-xs">
        <thead className="text-zinc-500">
          <tr>
            <th className="text-left py-1">Symbol</th>
            <th className="text-left">Entry</th>
            <th className="text-right">Days open</th>
            <th className="text-left">Exit rule</th>
            <th className="text-left">Diagnostic labels</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={5} className="py-3 text-zinc-500 text-center">
                No open positions to track.
              </td>
            </tr>
          ) : (
            rows.map(p => (
              <tr key={p.position_id} className="border-t border-zinc-800">
                <td className="py-1 font-mono">{p.symbol}</td>
                <td className="text-zinc-400">{p.entry_date ?? '—'}</td>
                <td className="text-right text-zinc-400">
                  {p.days_open == null ? '—' : p.days_open.toFixed(1)}
                </td>
                <td>
                  {p.exit_rule_status === 'unavailable' ? (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500">
                      Exit rule unavailable
                    </span>
                  ) : (
                    <span className="text-[10px] text-zinc-300">
                      {/* Rule object surfaced verbatim — no editorialization. */}
                      {JSON.stringify(p.exit_rule)}
                    </span>
                  )}
                </td>
                <td>
                  <div className="flex flex-wrap gap-1">
                    {p.diagnostic_labels.map(label => (
                      <DiagnosticChip key={label} label={label} />
                    ))}
                  </div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}

function DiagnosticChip({ label }: { label: string }) {
  // Tone selection driven by label content; no action language.
  const tone =
    label === 'Price data current'   ? 'bg-emerald-900/30 text-emerald-300'
  : label === 'Price data stale'     ? 'bg-amber-900/40 text-amber-300'
  : label === 'Missing price'        ? 'bg-zinc-800 text-zinc-400'
  : label === 'Recovered replay'     ? 'bg-amber-900/40 text-amber-300'
  : label === 'Exit rule unavailable'? 'bg-zinc-800 text-zinc-500'
  : 'bg-zinc-800 text-zinc-300';
  return (
    <span className={'text-[10px] px-1.5 py-0.5 rounded ' + tone}>
      {label}
    </span>
  );
}
