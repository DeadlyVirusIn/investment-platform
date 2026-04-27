// Phase 11I — Ranking explanation block.
// Documents the deterministic sort key + tie-breakers verbatim.
// Surfaced in the detail drawer so operators can audit ordering.

export default function OptionsRankingExplanation({
  rankPosition, explanation, tieBreakers,
}: {
  rankPosition: number | undefined;
  explanation: string | undefined;
  tieBreakers: string[] | undefined;
}) {
  return (
    <section className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <header className="mb-1 text-xs uppercase tracking-wide text-zinc-400">
        Ranking explanation
      </header>
      <div className="text-sm tabular-nums">
        Rank position:&nbsp;
        <span className="font-semibold">
          {rankPosition ?? 'Unavailable'}
        </span>
      </div>
      {explanation ? (
        <p className="mt-1 text-[11px] text-zinc-300">{explanation}</p>
      ) : null}
      <div className="mt-2 text-xs uppercase tracking-wide text-zinc-400">
        Tie-breakers (frozen order)
      </div>
      <ol className="mt-1 list-decimal list-inside text-[11px] text-zinc-300">
        {(tieBreakers ?? []).map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ol>
    </section>
  );
}
