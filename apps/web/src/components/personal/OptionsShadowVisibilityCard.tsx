// Personal-Analytics Phase — read-only options shadow card.
//
// Reads /api/options/shadow/summary + /api/options/pipeline-status
// and renders contracts evaluated, would_trade count, blocked-reason
// distribution, and explicit "no execution" labeling. Reuses the
// existing GET-only API surface — does not introduce any new
// endpoints. No buttons.

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

interface ShadowSummary {
  active: boolean;
  latest_run_date: string | null;
  total_runs: number;
  contracts_evaluated?: number;
  would_trade_count?: number;
  underlying_count?: number;
  blocked_reason_counts?: Record<string, number>;
  freshness_warnings: string[];
}

interface PipelineStatus {
  options_chain_snapshot_count: number;
  options_chain_snapshot_max_date: string | null;
  options_paper_trade_count: number;
}

export default function OptionsShadowVisibilityCard() {
  const summaryQ = useQuery<ShadowSummary>({
    queryKey: ['options', 'shadow', 'visibility-summary'],
    queryFn: () => apiGet<ShadowSummary>('/options/shadow/summary'),
    staleTime: 60_000,
  });
  const pipeQ = useQuery<PipelineStatus>({
    queryKey: ['options', 'visibility-pipeline'],
    queryFn: () => apiGet<PipelineStatus>('/options/pipeline-status'),
    staleTime: 60_000,
  });

  const s = summaryQ.data;
  const p = pipeQ.data;
  const blocked = s?.blocked_reason_counts ?? {};

  return (
    <section
      data-test="options-shadow-visibility-card"
      className="rounded-md border border-zinc-700 bg-zinc-900/40 p-4 mb-4"
    >
      <header className="flex items-baseline justify-between mb-3">
        <h3 className="text-sm font-semibold text-zinc-100">
          Options shadow diagnostics — read-only
        </h3>
        <span className="text-[10px] uppercase tracking-wide text-amber-400">
          Options shadow diagnostics only — no paper/live options execution
        </span>
      </header>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Cell label="Chain snapshots"
              value={String(p?.options_chain_snapshot_count ?? 0)}
              hint={p?.options_chain_snapshot_max_date ?? '—'} />
        <Cell label="Shadow runs"
              value={String(s?.total_runs ?? 0)}
              hint={s?.latest_run_date ?? '—'} />
        <Cell label="Contracts evaluated"
              value={String(s?.contracts_evaluated ?? 0)} />
        <Cell label="Would trade (eval only)"
              value={String(s?.would_trade_count ?? 0)} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Cell label="Underlyings" value={String(s?.underlying_count ?? 0)} />
        <Cell label="options_paper_trade rows"
              value={String(p?.options_paper_trade_count ?? 0)}
              hint="must remain 0" warn={(p?.options_paper_trade_count ?? 0) > 0} />
      </div>

      {Object.keys(blocked).length > 0 && (
        <table
          data-test="options-shadow-blocked-table"
          className="w-full text-xs"
        >
          <thead className="text-zinc-500">
            <tr>
              <th className="text-left py-1">Blocked reason</th>
              <th className="text-right">Count</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(blocked).map(([reason, count]) => (
              <tr key={reason}>
                <td className="py-1 text-zinc-300">{reason}</td>
                <td className="text-right">{count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="text-[10px] text-zinc-500 mt-3 leading-relaxed">
        Diagnostics only. The shadow evaluator does not open positions
        or send orders. The "would trade" column is evaluator output
        for analysis — it never reaches an executor.
      </div>
    </section>
  );
}

function Cell({
  label, value, hint, warn,
}: {
  label: string; value: string; hint?: string; warn?: boolean;
}) {
  return (
    <div className="rounded border border-zinc-800 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div className={
        'text-lg font-semibold mt-0.5 ' +
        (warn ? 'text-amber-300' : 'text-zinc-100')
      }>
        {value}
      </div>
      {hint && (
        <div className="text-[10px] text-zinc-500 mt-0.5">{hint}</div>
      )}
    </div>
  );
}
