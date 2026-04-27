// Phase 11I — Review Queue ranked table.
// Read-only. Neutral language. No "Buy/Sell/Execute/Recommended" anywhere.

import type { ReviewQueueRow } from '@/lib/options/optionsApi';
import { OptionsFlagList } from './OptionsFlagChip';

function _bucketChip(bucket: string, label: string): React.ReactNode {
  // Neutral coloring — never green "approved" / red "danger" coding.
  // Distinguish only by neutral border tone.
  return (
    <span
      title={bucket}
      className="inline-flex items-center gap-1 rounded-full border border-zinc-700/60 bg-zinc-900/40 px-2 py-0.5 text-[11px] text-zinc-200"
    >
      {label}
    </span>
  );
}

function _qualified(qualified: boolean) {
  return qualified ? 'Candidate rule match' : 'Rejected by rule';
}

function _keyPenalties(row: ReviewQueueRow): string {
  if (!row.penalties || row.penalties.length === 0) return '—';
  const top = row.penalties.slice(0, 2).map((p) => p.label);
  const rest = row.penalties.length - top.length;
  return rest > 0 ? `${top.join(' · ')} +${rest}` : top.join(' · ');
}

export default function OptionsReviewQueueTable({
  rows, onSelect,
}: {
  rows: ReviewQueueRow[];
  onSelect?: (id: string) => void;
}) {
  if (rows.length === 0) {
    return (
      <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-4 text-sm text-zinc-400">
        No review queue rows match the current filter.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-md border border-zinc-800">
      <table className="w-full text-xs text-zinc-200">
        <thead className="bg-zinc-900/60 text-zinc-400">
          <tr>
            <th className="px-2 py-1 text-right font-medium">Rank</th>
            <th className="px-2 py-1 text-left font-medium">Date</th>
            <th className="px-2 py-1 text-left font-medium">Underlying</th>
            <th className="px-2 py-1 text-left font-medium">Strategy</th>
            <th className="px-2 py-1 text-left font-medium">Bucket</th>
            <th className="px-2 py-1 text-right font-medium">Score</th>
            <th className="px-2 py-1 text-left font-medium">Qualified?</th>
            <th className="px-2 py-1 text-left font-medium">Flags</th>
            <th className="px-2 py-1 text-left font-medium">Key penalties</th>
            <th className="px-2 py-1 text-left font-medium">Inclusion reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.id}
              className="border-b border-zinc-800 hover:bg-zinc-900/50 cursor-pointer"
              onClick={() => onSelect?.(r.id)}
            >
              <td className="px-2 py-1 text-right tabular-nums font-mono">
                {r.rank_position}
              </td>
              <td className="px-2 py-1">{r.as_of_date}</td>
              <td className="px-2 py-1">{r.underlying}</td>
              <td className="px-2 py-1">{r.rule_id}</td>
              <td className="px-2 py-1">{_bucketChip(r.bucket, r.bucket_label)}</td>
              <td className="px-2 py-1 text-right tabular-nums font-semibold">
                {r.total_score} / 100
              </td>
              <td className="px-2 py-1">{_qualified(r.qualified)}</td>
              <td className="px-2 py-1"><OptionsFlagList flags={r.flags} /></td>
              <td className="px-2 py-1 text-[11px] text-zinc-300">
                {_keyPenalties(r)}
              </td>
              <td className="px-2 py-1 text-[11px] text-zinc-400">
                {r.inclusion_reason}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
