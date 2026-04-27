// Phase 11J — Review narrative cards (one per observation).
// Read-only. Surfaces deterministic narrative + caveats + flags.

import type { NarrativeBlock } from '@/lib/options/optionsApi';
import { OptionsFlagList } from './OptionsFlagChip';

export default function OptionsReviewNarrativeCards({
  narratives, onSelect,
}: {
  narratives: NarrativeBlock[];
  onSelect?: (id: string) => void;
}) {
  if (narratives.length === 0) {
    return (
      <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-4 text-sm text-zinc-400">
        No narratives available for the current filter.
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      {narratives.map((n) => (
        <article
          key={n.id}
          className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3 cursor-pointer hover:bg-zinc-900/50"
          onClick={() => onSelect?.(n.id)}
        >
          <header className="mb-2 flex items-baseline justify-between">
            <div>
              <div className="text-sm font-semibold text-zinc-100">
                {n.underlying} · {n.rule_id}
              </div>
              <div className="text-[11px] text-zinc-500">
                {n.as_of_date} · score {n.total_score} / 100 · rank {n.rank_position ?? '—'}
              </div>
            </div>
            <span className="rounded-full border border-zinc-700/60 bg-zinc-900/40 px-2 py-0.5 text-[11px] text-zinc-200">
              {n.bucket_label}
            </span>
          </header>

          <div className="mt-1 text-xs uppercase tracking-wide text-zinc-400">
            Why it appears
          </div>
          <p className="mt-1 text-[12px] text-zinc-200">{n.why_it_appears}</p>

          {n.caveats.length > 0 ? (
            <>
              <div className="mt-2 text-xs uppercase tracking-wide text-zinc-400">
                Caveats
              </div>
              <ul className="mt-1 list-disc list-inside text-[11px] text-zinc-300">
                {n.caveats.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </>
          ) : null}

          {n.flags.length > 0 ? (
            <div className="mt-2">
              <OptionsFlagList flags={n.flags} />
            </div>
          ) : null}

          <footer className="mt-3 border-t border-zinc-800 pt-2 text-[10px] text-zinc-500">
            {n.non_action_footer}
          </footer>
        </article>
      ))}
    </div>
  );
}
