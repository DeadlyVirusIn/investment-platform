// Phase 11I — Shortlist bucket panel.
// Computed view only — NEVER persisted server-side, NEVER mutated.

import type { DecisionSupportBucketsResponse } from '@/lib/options/optionsApi';
import { OptionsFlagList } from './OptionsFlagChip';

export default function OptionsShortlistBuckets({
  data, onSelect,
}: {
  data: DecisionSupportBucketsResponse;
  onSelect?: (id: string) => void;
}) {
  return (
    <div className="space-y-4">
      {data.groups.map((g) => (
        <section key={g.bucket}>
          <header className="mb-2 flex items-baseline justify-between">
            <h3 className="text-sm font-semibold text-zinc-100">
              {g.label}
            </h3>
            <span className="text-[11px] text-zinc-500">
              {g.count} entr{g.count === 1 ? 'y' : 'ies'} · computed view, not persisted
            </span>
          </header>
          {g.rows.length === 0 ? (
            <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-2 text-xs text-zinc-400">
              No entries in this bucket.
            </div>
          ) : (
            <table className="w-full text-xs">
              <thead className="text-zinc-500">
                <tr>
                  <th className="px-2 py-1 text-right">Rank</th>
                  <th className="px-2 py-1 text-left">Date</th>
                  <th className="px-2 py-1 text-left">Underlying</th>
                  <th className="px-2 py-1 text-left">Strategy</th>
                  <th className="px-2 py-1 text-right">Score</th>
                  <th className="px-2 py-1 text-left">Flags</th>
                </tr>
              </thead>
              <tbody>
                {g.rows.map((r) => (
                  <tr
                    key={r.id}
                    className="border-b border-zinc-800 hover:bg-zinc-900/50 cursor-pointer"
                    onClick={() => onSelect?.(r.id)}
                  >
                    <td className="px-2 py-1 text-right font-mono">
                      {r.rank_position}
                    </td>
                    <td className="px-2 py-1">{r.as_of_date}</td>
                    <td className="px-2 py-1">{r.underlying}</td>
                    <td className="px-2 py-1">{r.rule_id}</td>
                    <td className="px-2 py-1 text-right tabular-nums">
                      {r.total_score}
                    </td>
                    <td className="px-2 py-1">
                      <OptionsFlagList flags={r.flags} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      ))}
    </div>
  );
}
