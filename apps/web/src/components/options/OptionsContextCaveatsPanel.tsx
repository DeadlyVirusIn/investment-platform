// Phase 11J — Context caveats panel.
// Surfaces the 6 spec-mandated caveat lines + makes them visually
// distinct from the narrative content.

export default function OptionsContextCaveatsPanel({
  caveats,
}: { caveats: string[] }) {
  if (!caveats || caveats.length === 0) return null;
  return (
    <section className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3">
      <header className="mb-2">
        <h3 className="text-sm font-semibold text-zinc-100">Context caveats</h3>
      </header>
      <ul className="space-y-1 text-[11px] text-zinc-300">
        {caveats.map((c, i) => (
          <li key={i} className="flex gap-1">
            <span aria-hidden="true">⚠</span>
            <span>{c}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
