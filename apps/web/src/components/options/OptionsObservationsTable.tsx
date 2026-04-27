// Phase 11G — historical strategy observations table.
// Each row shows: (symbol, day, rule) → "Candidate rule match" or
// "Rejected by rule". NEVER "Recommended" / "Best" / "Buy" / "Sell".

import type { StrategyObservationListItem } from '@/lib/options/optionsApi';

function StatusChip({ qualified }: { qualified: boolean }) {
  if (qualified) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-700/40 bg-emerald-900/30 px-2 py-0.5 text-[11px] text-emerald-200">
        ✓ Candidate rule match
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-zinc-700/60 bg-zinc-900/40 px-2 py-0.5 text-[11px] text-zinc-300">
      Rejected by rule
    </span>
  );
}

export default function OptionsObservationsTable({
  observations, onSelect,
}: {
  observations: StrategyObservationListItem[];
  onSelect?: (id: string) => void;
}) {
  if (observations.length === 0) {
    return (
      <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-4 text-sm text-zinc-400">
        No observations in the lookback window. The engine evaluates
        rules per (symbol, day) only when a chain snapshot exists.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-md border border-zinc-800">
      <table className="w-full text-xs text-zinc-200">
        <thead className="bg-zinc-900/60 text-zinc-400">
          <tr>
            <th className="px-2 py-1 text-left font-medium">Date</th>
            <th className="px-2 py-1 text-left font-medium">Underlying</th>
            <th className="px-2 py-1 text-left font-medium">Rule</th>
            <th className="px-2 py-1 text-left font-medium">Outcome</th>
            <th className="px-2 py-1 text-right font-medium">Criteria passed</th>
            <th className="px-2 py-1 text-right font-medium">Chain rows</th>
          </tr>
        </thead>
        <tbody>
          {observations.map((o) => (
            <tr
              key={o.id}
              className="border-b border-zinc-800 hover:bg-zinc-900/50 cursor-pointer"
              onClick={() => onSelect?.(o.id)}
            >
              <td className="px-2 py-1">{o.as_of_date}</td>
              <td className="px-2 py-1">{o.underlying}</td>
              <td className="px-2 py-1">{o.rule_name}</td>
              <td className="px-2 py-1"><StatusChip qualified={o.qualified} /></td>
              <td className="px-2 py-1 text-right tabular-nums">
                {o.n_passed} / {o.n_criteria}
              </td>
              <td className="px-2 py-1 text-right tabular-nums">{o.n_chain_accepted}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
