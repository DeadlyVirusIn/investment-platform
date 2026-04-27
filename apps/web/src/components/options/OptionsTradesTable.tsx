// Phase 11F — Options paper trades table.
// Read-only. Surfaces flag chips next to PnL so an uncertain outcome
// is never displayed as a clean number.

import type { PaperTradeHeader } from '@/lib/options/optionsApi';
import { OptionsFlagList, flagLabel } from './OptionsFlagChip';
import { fmtMoney, fmtTimestamp } from './format';

function PnlCell({
  pnl, flags,
}: { pnl: string | null; flags: string[] }) {
  const text = fmtMoney(pnl, { nullText: 'Pending' });
  if (flags.length === 0) {
    return <span className="tabular-nums">{text}</span>;
  }
  return (
    <span className="inline-flex items-center gap-1">
      <span className="tabular-nums">{text}</span>
      <span aria-hidden="true">⚠</span>
      <span className="text-[11px] text-amber-300">{flagLabel(flags[0])}</span>
    </span>
  );
}

export default function OptionsTradesTable({
  trades,
  flagsById,
  onSelect,
}: {
  trades: PaperTradeHeader[];
  flagsById: Record<number, string[]>;
  onSelect?: (id: number) => void;
}) {
  if (trades.length === 0) {
    return (
      <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-4 text-sm text-zinc-400">
        No paper trades yet.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-md border border-zinc-800">
      <table className="w-full text-xs text-zinc-200">
        <thead className="bg-zinc-900/60 text-zinc-400">
          <tr>
            <th className="px-2 py-1 text-left font-medium">ID</th>
            <th className="px-2 py-1 text-left font-medium">Underlying</th>
            <th className="px-2 py-1 text-left font-medium">Strategy</th>
            <th className="px-2 py-1 text-left font-medium">Status</th>
            <th className="px-2 py-1 text-right font-medium">PnL</th>
            <th className="px-2 py-1 text-right font-medium">Max loss</th>
            <th className="px-2 py-1 text-right font-medium">Fees</th>
            <th className="px-2 py-1 text-left font-medium">Opened</th>
            <th className="px-2 py-1 text-left font-medium">Closed</th>
            <th className="px-2 py-1 text-left font-medium">Flags</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => {
            const flags = flagsById[t.id] ?? [];
            return (
              <tr
                key={t.id}
                className="border-b border-zinc-800 hover:bg-zinc-900/50 cursor-pointer"
                onClick={() => onSelect?.(t.id)}
              >
                <td className="px-2 py-1">{t.id}</td>
                <td className="px-2 py-1">{t.underlying}</td>
                <td className="px-2 py-1">{t.strategy_name}</td>
                <td className="px-2 py-1">
                  {t.status}
                  {flags.includes('ASSIGNMENT_SIMPLIFIED_EXIT') ? (
                    <span className="ml-1 text-[11px] text-amber-300">
                      ⚠ Assignment — simplified exit model
                    </span>
                  ) : null}
                </td>
                <td className="px-2 py-1 text-right">
                  <PnlCell pnl={t.realized_pnl_dollars} flags={flags} />
                </td>
                <td className="px-2 py-1 text-right tabular-nums">
                  {fmtMoney(t.max_loss_dollars, { nullText: 'Unavailable' })}
                </td>
                <td className="px-2 py-1 text-right tabular-nums">
                  {fmtMoney(t.fees_total_dollars, { nullText: '0.00' })}
                </td>
                <td className="px-2 py-1">{fmtTimestamp(t.opened_at)}</td>
                <td className="px-2 py-1">{fmtTimestamp(t.closed_at)}</td>
                <td className="px-2 py-1"><OptionsFlagList flags={flags} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
