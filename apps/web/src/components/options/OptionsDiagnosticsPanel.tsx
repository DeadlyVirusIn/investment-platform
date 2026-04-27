// Phase 11G — diagnostics panel.
// Counts of data-quality failures within the lookback window.

import type { DiagnosticsResponse } from '@/lib/options/optionsApi';

function StatBlock({
  label, value, hint,
}: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/50 px-3 py-2">
      <div className="text-xs uppercase tracking-wide text-zinc-400">{label}</div>
      <div className="mt-1 text-lg font-semibold tabular-nums text-zinc-100">{value}</div>
      {hint ? <div className="mt-1 text-[11px] text-zinc-500">{hint}</div> : null}
    </div>
  );
}

export default function OptionsDiagnosticsPanel({
  data,
}: { data: DiagnosticsResponse }) {
  return (
    <div className="space-y-4">
      <section>
        <header className="mb-2 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-zinc-100">Chain</h2>
          <span className="text-[11px] text-zinc-500">
            since {data.lookback_cutoff} ({data.lookback_days}d)
          </span>
        </header>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
          <StatBlock label="Chain rows ingested"   value={data.chain.n_rows} />
          <StatBlock label="Missing IV"            value={data.chain.n_missing_iv} />
          <StatBlock label="Missing Greeks"        value={data.chain.n_missing_greeks} />
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-100">Features</h2>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-4">
          <StatBlock label="Feature rows"
                     value={data.features.n_rows} />
          <StatBlock
            label="Naive GEX warnings"
            value={data.features.n_naive_gex_warnings}
            hint={data.naive_gex_label}
          />
          <StatBlock label="No price history"
                     value={data.features.n_no_price_history} />
          <StatBlock label="Insufficient IV history"
                     value={data.features.n_insufficient_iv_history} />
        </div>
        {Object.keys(data.features.flag_counts).length > 0 ? (
          <details className="mt-2 text-xs">
            <summary className="cursor-pointer text-zinc-400">
              All feature-engine flag counts
            </summary>
            <pre className="mt-1 rounded bg-zinc-900/50 p-2 text-[11px] text-zinc-300">
              {JSON.stringify(data.features.flag_counts, null, 2)}
            </pre>
          </details>
        ) : null}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-100">Expirations</h2>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
          <StatBlock
            label="Pin-risk events"
            value={data.expirations.n_pin_risk}
            hint="Pin risk — outcome uncertain"
          />
          <StatBlock
            label="Missing settlement events"
            value={data.expirations.n_missing_settlement}
            hint="Missing settlement — expiry unresolved"
          />
          <StatBlock
            label="Assignment events"
            value={data.assignments.n_events}
            hint="Assignment — simplified exit model"
          />
        </div>
        {data.expirations.by_classification.length > 0 ? (
          <table className="mt-2 w-full text-xs">
            <thead className="text-zinc-500">
              <tr><th className="px-2 py-1 text-left">Classification</th>
                  <th className="px-2 py-1 text-right">N</th></tr>
            </thead>
            <tbody>
              {data.expirations.by_classification.map((r) => (
                <tr key={r.classification} className="border-b border-zinc-800">
                  <td className="px-2 py-1">{r.classification}</td>
                  <td className="px-2 py-1 text-right">{r.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </section>
    </div>
  );
}
