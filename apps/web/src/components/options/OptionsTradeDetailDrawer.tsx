// Phase 11F — Trade detail drawer (read-only).
// Lifecycle / expiration / assignment events. Flag chips throughout.

import { useOptionsPaperTradeDetail } from '@/lib/options/hooks';
import { OptionsFlagList } from './OptionsFlagChip';
import { fmtMoney, fmtRaw, fmtTimestamp } from './format';

export default function OptionsTradeDetailDrawer({
  tradeId, onClose,
}: { tradeId: number | null; onClose: () => void }) {
  const { data, isLoading, error } = useOptionsPaperTradeDetail(
    tradeId ?? undefined,
  );
  if (tradeId === null) return null;
  return (
    <aside className="fixed inset-y-0 right-0 z-30 w-full max-w-xl overflow-y-auto border-l border-zinc-800 bg-zinc-950 p-4 text-zinc-100 shadow-xl">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Trade #{tradeId}</h2>
        <button
          onClick={onClose}
          className="rounded-md border border-zinc-700 px-2 py-1 text-xs hover:bg-zinc-900"
        >
          Close
        </button>
      </div>
      {isLoading ? (
        <p className="text-sm text-zinc-400">Loading…</p>
      ) : error ? (
        <p className="text-sm text-red-400">Error loading trade.</p>
      ) : data ? (
        <div className="space-y-4 text-sm">
          <section>
            <div className="text-xs uppercase tracking-wide text-zinc-400">
              Header
            </div>
            <div className="mt-1 grid grid-cols-2 gap-1 tabular-nums">
              <div>Status</div><div>{data.status}</div>
              <div>Strategy</div><div>{data.strategy_name}</div>
              <div>Underlying</div><div>{data.underlying}</div>
              <div>Realized PnL</div>
              <div>{fmtMoney(data.realized_pnl_dollars, { nullText: 'Pending' })}</div>
              <div>Max loss</div><div>{fmtMoney(data.max_loss_dollars)}</div>
              <div>Max profit</div><div>{fmtMoney(data.max_profit_dollars)}</div>
              <div>Fees total</div><div>{fmtMoney(data.fees_total_dollars)}</div>
              <div>Fill model</div><div>{data.fill_model_version}</div>
              <div>Paper-only</div><div>{String(data.paper_only)}</div>
            </div>
            <div className="mt-2">
              <OptionsFlagList flags={data.data_quality_flags} />
            </div>
          </section>

          <section>
            <div className="text-xs uppercase tracking-wide text-zinc-400">
              Legs
            </div>
            <table className="mt-1 w-full text-xs">
              <thead className="text-zinc-500">
                <tr>
                  <th className="px-1 text-left">#</th>
                  <th className="px-1 text-left">Side</th>
                  <th className="px-1 text-left">Type</th>
                  <th className="px-1 text-right">Strike</th>
                  <th className="px-1 text-right">Qty</th>
                  <th className="px-1 text-right">Entry fill</th>
                  <th className="px-1 text-right">Exit fill</th>
                </tr>
              </thead>
              <tbody>
                {data.legs.map((l) => (
                  <tr key={l.leg_index} className="border-b border-zinc-800">
                    <td className="px-1">{l.leg_index}</td>
                    <td className="px-1">{l.side}</td>
                    <td className="px-1">{l.option_type}</td>
                    <td className="px-1 text-right">{fmtRaw(l.strike, { digits: 2 })}</td>
                    <td className="px-1 text-right">{l.qty}</td>
                    <td className="px-1 text-right">{fmtRaw(l.entry.fill_price)}</td>
                    <td className="px-1 text-right">{fmtRaw(l.exit.fill_price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section>
            <div className="text-xs uppercase tracking-wide text-zinc-400">
              Lifecycle events
            </div>
            <ul className="mt-1 space-y-1">
              {data.lifecycle_events.map((e) => (
                <li
                  key={e.id}
                  className="rounded border border-zinc-800 bg-zinc-900/40 p-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{e.event_type}</span>
                    <span className="text-[11px] text-zinc-500">
                      {fmtTimestamp(e.event_at_utc)}
                    </span>
                  </div>
                  {Array.isArray((e.payload as { flags?: string[] })?.flags) ? (
                    <div className="mt-1">
                      <OptionsFlagList
                        flags={(e.payload as { flags: string[] }).flags}
                      />
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>

          {data.expiration_events.length > 0 ? (
            <section>
              <div className="text-xs uppercase tracking-wide text-zinc-400">
                Expiration events
              </div>
              <table className="mt-1 w-full text-xs">
                <thead className="text-zinc-500">
                  <tr>
                    <th className="px-1 text-left">Leg</th>
                    <th className="px-1 text-left">Expiry</th>
                    <th className="px-1 text-left">Settlement</th>
                    <th className="px-1 text-left">Class</th>
                    <th className="px-1 text-right">Intrinsic</th>
                    <th className="px-1 text-right">Realized</th>
                  </tr>
                </thead>
                <tbody>
                  {data.expiration_events.map((x, idx) => (
                    <tr key={idx} className="border-b border-zinc-800">
                      <td className="px-1">{x.leg_index}</td>
                      <td className="px-1">{x.expiry_date}</td>
                      <td className="px-1">{fmtRaw(x.underlying_settlement)}</td>
                      <td className="px-1">{x.classification}</td>
                      <td className="px-1 text-right">{fmtMoney(x.intrinsic_value_dollars)}</td>
                      <td className="px-1 text-right">{fmtMoney(x.realized_pnl_dollars)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          ) : null}

          {data.assignment_events.length > 0 ? (
            <section>
              <div className="text-xs uppercase tracking-wide text-zinc-400">
                Assignment events
              </div>
              <ul className="mt-1 space-y-1">
                {data.assignment_events.map((a, idx) => (
                  <li
                    key={idx}
                    className="rounded border border-red-800/40 bg-red-900/10 p-2"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">
                        {a.event_type} (leg {a.leg_index})
                      </span>
                      <span className="text-[11px] text-zinc-500">
                        {fmtTimestamp(a.event_at_utc)}
                      </span>
                    </div>
                    <div className="mt-1 text-[11px] text-zinc-300">
                      {a.notes}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      ) : null}
    </aside>
  );
}
