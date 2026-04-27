// Phase 11F — Options chain table (read-only).
// No buy/sell buttons. No execute trade. Pure observation.

import { OptionsFlagList } from './OptionsFlagChip';
import { fmtRaw, fmtInt } from './format';
import type { ChainQuote } from '@/lib/options/optionsApi';

function Cell({ v }: { v: string }) {
  return <td className="px-2 py-1 text-right tabular-nums">{v}</td>;
}

function Row({ q }: { q: ChainQuote }) {
  return (
    <tr className="border-b border-zinc-800 hover:bg-zinc-900/50">
      <Cell v={fmtRaw(q.strike, { digits: 2 })} />
      <Cell v={fmtRaw(q.bid)} />
      <Cell v={fmtRaw(q.ask)} />
      <Cell v={fmtRaw(q.mid)} />
      <Cell v={fmtRaw(q.spread)} />
      <Cell v={fmtInt(q.volume)} />
      <Cell v={fmtInt(q.open_interest)} />
      <Cell v={fmtRaw(q.iv, { digits: 4 })} />
      <Cell v={fmtRaw(q.delta, { digits: 4 })} />
      <Cell v={fmtRaw(q.gamma, { digits: 4 })} />
      <Cell v={fmtRaw(q.theta, { digits: 4 })} />
      <Cell v={fmtRaw(q.vega, { digits: 4 })} />
      <td className="px-2 py-1 text-left">
        <OptionsFlagList flags={q.data_quality_flags} />
      </td>
    </tr>
  );
}

const HEADERS = [
  'Strike', 'Bid', 'Ask', 'Mid', 'Spread', 'Vol', 'OI',
  'IV', 'Delta', 'Gamma', 'Theta', 'Vega', 'Data quality',
];

export default function OptionsChainTable({
  side, rows,
}: { side: 'CALLS' | 'PUTS'; rows: ChainQuote[] }) {
  return (
    <section className="rounded-md border border-zinc-800 bg-zinc-950/50">
      <header className="border-b border-zinc-800 px-3 py-2 text-sm font-semibold text-zinc-100">
        {side} (observe — paper-only)
      </header>
      {rows.length === 0 ? (
        <div className="px-3 py-4 text-sm text-zinc-400">
          No accepted quotes for this expiry. Liquidity filter excluded all rows
          or no chain snapshot exists.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-zinc-200">
            <thead className="bg-zinc-900/60 text-zinc-400">
              <tr>
                {HEADERS.map((h) => (
                  <th
                    key={h}
                    className={
                      h === 'Data quality'
                        ? 'px-2 py-1 text-left font-medium'
                        : 'px-2 py-1 text-right font-medium'
                    }
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>{rows.map((q) => <Row key={q.option_symbol} q={q} />)}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}
