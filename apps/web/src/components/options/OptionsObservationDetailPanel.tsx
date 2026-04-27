// Phase 11G — observation detail (per-criterion pass/fail).
// Read-only. Surfaces every check's reason. No "act on this" CTA.

import { useOptionsStrategyObservationDetail } from '@/lib/options/hooks';

export default function OptionsObservationDetailPanel({
  observationId, onClose,
}: { observationId: string | null; onClose: () => void }) {
  const { data, isLoading, error } =
    useOptionsStrategyObservationDetail(observationId ?? undefined);
  if (observationId === null) return null;
  return (
    <aside className="fixed inset-y-0 right-0 z-30 w-full max-w-xl overflow-y-auto border-l border-zinc-800 bg-zinc-950 p-4 text-zinc-100 shadow-xl">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Observation</h2>
          <p className="text-[11px] text-zinc-500">{observationId}</p>
        </div>
        <button
          onClick={onClose}
          className="rounded-md border border-zinc-700 px-2 py-1 text-xs hover:bg-zinc-900"
        >
          Close
        </button>
      </header>
      {isLoading ? (
        <p className="text-sm text-zinc-400">Loading…</p>
      ) : error ? (
        <p className="text-sm text-red-400">Error loading observation.</p>
      ) : data ? (
        <div className="space-y-3 text-sm">
          <section>
            <div className="text-xs uppercase tracking-wide text-zinc-400">Header</div>
            <div className="mt-1 grid grid-cols-2 gap-1">
              <div>Underlying</div><div>{data.underlying}</div>
              <div>As of</div><div>{data.as_of_date}</div>
              <div>Rule</div><div>{data.evaluation.name}</div>
              <div>Outcome</div>
              <div>
                {data.evaluation.qualified
                  ? 'Candidate rule match'
                  : 'Rejected by rule'}{' '}
                ({data.evaluation.n_passed}/{data.evaluation.n_criteria})
              </div>
              <div>Chain rows accepted</div>
              <div>{data.n_chain_accepted}</div>
            </div>
          </section>
          <section>
            <div className="text-xs uppercase tracking-wide text-zinc-400">
              Per-criterion checks
            </div>
            <ul className="mt-1 space-y-1">
              {data.evaluation.checks.map((c) => (
                <li
                  key={c.code}
                  className={
                    'rounded border p-2 ' +
                    (c.passed
                      ? 'border-emerald-700/40 bg-emerald-900/10'
                      : 'border-zinc-700/60 bg-zinc-900/40')
                  }
                >
                  <div className="text-xs font-semibold">
                    {c.passed ? '✓' : '✗'} {c.code}
                  </div>
                  <p className="mt-0.5 text-[11px] text-zinc-300">{c.reason}</p>
                </li>
              ))}
            </ul>
          </section>
          {data.evaluation.candidate ? (
            <section>
              <div className="text-xs uppercase tracking-wide text-zinc-400">
                Selected legs (candidate, observation only)
              </div>
              <pre className="mt-1 overflow-x-auto rounded bg-zinc-900/50 p-2 text-[11px] text-zinc-300">
                {JSON.stringify(data.evaluation.candidate, null, 2)}
              </pre>
            </section>
          ) : null}
        </div>
      ) : null}
    </aside>
  );
}
