// Phase 11H — Threshold diagnostics: counts above/below + common penalty +
// missing-data drivers.

import type { EvaluationDiagnostics } from '@/lib/options/optionsApi';
import { flagLabel } from './OptionsFlagChip';

export default function OptionsEvaluationDiagnosticsPanel({
  data,
}: { data: EvaluationDiagnostics }) {
  return (
    <div className="space-y-4">
      <section className="grid grid-cols-1 gap-2 md:grid-cols-3">
        <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3">
          <div className="text-xs uppercase tracking-wide text-zinc-400">
            Total scored
          </div>
          <div className="mt-1 text-lg font-semibold tabular-nums">
            {data.n_total_scored}
          </div>
        </div>
        <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3">
          <div className="text-xs uppercase tracking-wide text-zinc-400">
            At or above threshold ({data.threshold})
          </div>
          <div className="mt-1 text-lg font-semibold tabular-nums">
            {data.n_at_or_above_threshold}
          </div>
        </div>
        <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3">
          <div className="text-xs uppercase tracking-wide text-zinc-400">
            Below threshold ({data.threshold})
          </div>
          <div className="mt-1 text-lg font-semibold tabular-nums">
            {data.n_below_threshold}
          </div>
        </div>
      </section>

      <section>
        <header className="mb-1 text-xs uppercase tracking-wide text-zinc-400">
          Common penalty drivers
        </header>
        {data.common_penalty_drivers.length === 0 ? (
          <div className="text-sm text-zinc-400">No penalty drivers.</div>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-zinc-500">
              <tr>
                <th className="px-2 py-1 text-left">Code</th>
                <th className="px-2 py-1 text-left">Label</th>
                <th className="px-2 py-1 text-right">Count</th>
              </tr>
            </thead>
            <tbody>
              {data.common_penalty_drivers.map((r) => (
                <tr key={r.code} className="border-b border-zinc-800">
                  <td className="px-2 py-1 font-mono text-[11px]">{r.code}</td>
                  <td className="px-2 py-1">{flagLabel(r.code)}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{r.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section>
        <header className="mb-1 text-xs uppercase tracking-wide text-zinc-400">
          Common missing-data drivers (model limitation flags)
        </header>
        {data.common_missing_data_drivers.length === 0 ? (
          <div className="text-sm text-zinc-400">No missing-data drivers.</div>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-zinc-500">
              <tr>
                <th className="px-2 py-1 text-left">Flag</th>
                <th className="px-2 py-1 text-right">Count</th>
              </tr>
            </thead>
            <tbody>
              {data.common_missing_data_drivers.map((r) => (
                <tr key={r.code} className="border-b border-zinc-800">
                  <td className="px-2 py-1">{flagLabel(r.code)}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{r.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
