// Phase 11H — Score detail drawer.
// Full breakdown: components + per-criterion explanations, penalties +
// reasons, formula inputs (audit), flags. Read-only. No "act on this".

import { useOptionsEvaluationScoreDetail } from '@/lib/options/hooks';
import { OptionsFlagList } from './OptionsFlagChip';

export default function OptionsEvaluationDetailDrawer({
  observationId, onClose,
}: { observationId: string | null; onClose: () => void }) {
  const { data, isLoading, error } = useOptionsEvaluationScoreDetail(
    observationId ?? undefined,
  );
  if (observationId === null) return null;
  return (
    <aside className="fixed inset-y-0 right-0 z-30 w-full max-w-xl overflow-y-auto border-l border-zinc-800 bg-zinc-950 p-4 text-zinc-100 shadow-xl">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Evaluation score</h2>
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
        <p className="text-sm text-red-400">Error loading score detail.</p>
      ) : data ? (
        <div className="space-y-3 text-sm">
          <section className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
            <div className="text-xs uppercase tracking-wide text-zinc-400">Header</div>
            <div className="mt-1 grid grid-cols-2 gap-1">
              <div>Underlying</div><div>{data.underlying}</div>
              <div>Strategy</div><div>{data.rule_id}</div>
              <div>As of</div><div>{data.as_of_date}</div>
              <div>Qualified?</div>
              <div>{data.qualified ? 'Candidate rule match' : 'Rejected by rule'}</div>
              <div>Evaluation score</div>
              <div className="font-semibold tabular-nums">
                {data.total_score} / 100
              </div>
              <div>Model version</div><div>{data.model_version}</div>
            </div>
          </section>

          <section>
            <div className="text-xs uppercase tracking-wide text-zinc-400">
              Component breakdown
            </div>
            <ul className="mt-1 space-y-1">
              {data.components.map((c) => (
                <li
                  key={c.component}
                  className="rounded border border-zinc-800 bg-zinc-900/30 p-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold capitalize">
                      {c.component.replace('_', ' / ')}
                    </span>
                    <span className="tabular-nums">{c.score} / {c.weight_max}</span>
                  </div>
                  <p className="mt-1 text-[11px] text-zinc-400">{c.explanation}</p>
                </li>
              ))}
            </ul>
          </section>

          <section>
            <div className="text-xs uppercase tracking-wide text-zinc-400">
              Penalties
            </div>
            {data.penalties.length === 0 ? (
              <div className="text-xs text-zinc-500">No penalties applied.</div>
            ) : (
              <ul className="mt-1 space-y-1">
                {data.penalties.map((p) => (
                  <li
                    key={p.code}
                    className="rounded border border-amber-700/40 bg-amber-900/10 p-2"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-amber-200">
                        {p.label}
                      </span>
                      <span className="tabular-nums text-amber-200">
                        {p.points}
                      </span>
                    </div>
                    <div className="text-[10px] font-mono text-zinc-500">{p.code}</div>
                    <p className="mt-1 text-[11px] text-zinc-300">{p.reason}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <div className="text-xs uppercase tracking-wide text-zinc-400">
              Model limitation flags
            </div>
            {data.flags.length === 0 ? (
              <div className="text-xs text-zinc-500">No flags surfaced.</div>
            ) : (
              <OptionsFlagList flags={data.flags} />
            )}
          </section>

          <section>
            <div className="text-xs uppercase tracking-wide text-zinc-400">
              Formula inputs (audit)
            </div>
            <pre className="mt-1 overflow-x-auto rounded bg-zinc-900/50 p-2 text-[11px] text-zinc-300">
              {JSON.stringify(data.inputs, null, 2)}
            </pre>
          </section>
        </div>
      ) : null}
    </aside>
  );
}
