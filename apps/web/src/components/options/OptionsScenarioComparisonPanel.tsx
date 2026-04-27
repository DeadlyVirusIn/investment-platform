// Phase 11J — Scenario comparison panel.
// Reads two observation IDs and renders factual deltas only.
// NEVER says "better" / "worse" / "choose" / "avoid".

import { useOptionsDecisionFramingCompare } from '@/lib/options/hooks';
import { OptionsFlagList } from './OptionsFlagChip';

export default function OptionsScenarioComparisonPanel({
  idA, idB,
}: {
  idA: string | null;
  idB: string | null;
}) {
  const enabled = !!idA && !!idB;
  const { data, isLoading, error } = useOptionsDecisionFramingCompare(
    idA ?? undefined, idB ?? undefined,
  );
  if (!enabled) {
    return (
      <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3 text-sm text-zinc-400">
        Pick two observations to compare. Comparison reports factual deltas
        only — never preference or selection.
      </div>
    );
  }
  if (isLoading) return <p className="text-sm text-zinc-400">Loading comparison…</p>;
  if (error) return <p className="text-sm text-red-400">Error loading comparison.</p>;
  if (!data) return null;
  const cmp = data.comparison;
  return (
    <section className="space-y-3">
      <header className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3 text-[11px] text-zinc-300">
        {cmp.non_preference_notice}
      </header>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-md border border-zinc-800 bg-zinc-900/30 p-3">
          <div className="text-xs uppercase tracking-wide text-zinc-400">
            Observation A
          </div>
          <div className="mt-1 text-sm font-semibold text-zinc-100">
            {cmp.a.underlying} · {cmp.a.rule_id}
          </div>
          <div className="text-[11px] text-zinc-400">{cmp.a.as_of_date}</div>
          <div className="mt-2 grid grid-cols-2 gap-1 text-[11px]">
            <div>Score</div><div className="tabular-nums">{cmp.a.total_score}</div>
            <div>Bucket</div><div>{cmp.a.bucket_label ?? cmp.a.bucket}</div>
            <div>Rank</div><div className="tabular-nums">{cmp.a.rank_position ?? '—'}</div>
            <div>Liquidity comp.</div>
            <div className="tabular-nums">{cmp.a.liquidity_component_score}</div>
            <div>Penalties</div><div className="tabular-nums">{cmp.a.n_penalties}</div>
          </div>
          <div className="mt-2"><OptionsFlagList flags={cmp.a.flags} /></div>
        </div>
        <div className="rounded-md border border-zinc-800 bg-zinc-900/30 p-3">
          <div className="text-xs uppercase tracking-wide text-zinc-400">
            Observation B
          </div>
          <div className="mt-1 text-sm font-semibold text-zinc-100">
            {cmp.b.underlying} · {cmp.b.rule_id}
          </div>
          <div className="text-[11px] text-zinc-400">{cmp.b.as_of_date}</div>
          <div className="mt-2 grid grid-cols-2 gap-1 text-[11px]">
            <div>Score</div><div className="tabular-nums">{cmp.b.total_score}</div>
            <div>Bucket</div><div>{cmp.b.bucket_label ?? cmp.b.bucket}</div>
            <div>Rank</div><div className="tabular-nums">{cmp.b.rank_position ?? '—'}</div>
            <div>Liquidity comp.</div>
            <div className="tabular-nums">{cmp.b.liquidity_component_score}</div>
            <div>Penalties</div><div className="tabular-nums">{cmp.b.n_penalties}</div>
          </div>
          <div className="mt-2"><OptionsFlagList flags={cmp.b.flags} /></div>
        </div>
      </div>

      <section>
        <header className="mb-1 text-xs uppercase tracking-wide text-zinc-400">
          Factual deltas
        </header>
        <ul className="list-disc list-inside text-[12px] text-zinc-200">
          {cmp.factual_deltas.map((d, i) => <li key={i}>{d}</li>)}
        </ul>
      </section>

      <section className="text-[12px] text-zinc-200">
        <p>{cmp.bucket_phrase}</p>
        <p className="mt-1">{cmp.ranking_phrase}</p>
      </section>

      {(cmp.flags_only_in_a.length > 0 || cmp.flags_only_in_b.length > 0) ? (
        <section>
          <header className="mb-1 text-xs uppercase tracking-wide text-zinc-400">
            Flags differing between observations
          </header>
          {cmp.flags_only_in_a.length > 0 ? (
            <div className="text-[11px] text-zinc-300">
              <span className="font-semibold">Only in A:</span>{' '}
              <OptionsFlagList flags={cmp.flags_only_in_a} />
            </div>
          ) : null}
          {cmp.flags_only_in_b.length > 0 ? (
            <div className="mt-1 text-[11px] text-zinc-300">
              <span className="font-semibold">Only in B:</span>{' '}
              <OptionsFlagList flags={cmp.flags_only_in_b} />
            </div>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}
