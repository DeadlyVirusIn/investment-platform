// Phase 11G — scenario replay timeline.
// Read-only. No execute / copy / create buttons.

import type { ScenarioReplayResponse } from '@/lib/options/optionsApi';
import { OptionsFlagList } from './OptionsFlagChip';
import { fmtMoney, fmtTimestamp } from './format';

function StatusChip({ qualified }: { qualified: boolean }) {
  return qualified ? (
    <span className="rounded-full border border-emerald-700/40 bg-emerald-900/30 px-2 py-0.5 text-[11px] text-emerald-200">
      Candidate rule match
    </span>
  ) : (
    <span className="rounded-full border border-zinc-700/60 bg-zinc-900/40 px-2 py-0.5 text-[11px] text-zinc-300">
      Rejected by rule
    </span>
  );
}

export default function OptionsReplayTimeline({
  data,
}: { data: ScenarioReplayResponse }) {
  return (
    <div className="space-y-4">
      <section className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3">
        <header className="mb-2 text-xs uppercase tracking-wide text-zinc-400">
          Chain summary at {data.as_of_date}
        </header>
        <div className="grid grid-cols-2 gap-2 text-sm md:grid-cols-5">
          <div>Raw rows: {data.chain_summary.n_raw}</div>
          <div>Accepted: {data.chain_summary.n_accepted}</div>
          <div>Calls: {data.chain_summary.n_calls_accepted}</div>
          <div>Puts: {data.chain_summary.n_puts_accepted}</div>
          <div>Expiries: {data.chain_summary.expiries_accepted.length}</div>
        </div>
      </section>

      <section>
        <header className="mb-2 text-xs uppercase tracking-wide text-zinc-400">
          Rule evaluations (observation only)
        </header>
        <ul className="space-y-2">
          {data.rule_evaluations.map((ev) => (
            <li
              key={ev.rule_id}
              className="rounded-md border border-zinc-800 bg-zinc-950/40 p-3"
            >
              <div className="flex items-center justify-between">
                <div className="font-semibold text-zinc-100">{ev.name}</div>
                <StatusChip qualified={ev.qualified} />
              </div>
              <div className="mt-1 text-[11px] text-zinc-400">
                {ev.n_passed} / {ev.n_criteria} criteria passed
              </div>
              <ul className="mt-2 space-y-1 text-[11px]">
                {ev.checks.map((c) => (
                  <li
                    key={c.code}
                    className={c.passed ? 'text-emerald-300' : 'text-zinc-300'}
                  >
                    {c.passed ? '✓' : '✗'} <span className="font-mono">{c.code}</span>
                    <span className="ml-2 text-zinc-400">{c.reason}</span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <header className="mb-2 text-xs uppercase tracking-wide text-zinc-400">
          Nearby paper trades (±3 days, observation only)
        </header>
        {data.nearby_trades.length === 0 ? (
          <div className="text-sm text-zinc-400">No nearby paper trades.</div>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-zinc-500">
              <tr>
                <th className="px-2 py-1 text-left">ID</th>
                <th className="px-2 py-1 text-left">Strategy</th>
                <th className="px-2 py-1 text-left">Status</th>
                <th className="px-2 py-1 text-left">Opened</th>
                <th className="px-2 py-1 text-left">Closed</th>
                <th className="px-2 py-1 text-right">Realized PnL</th>
              </tr>
            </thead>
            <tbody>
              {data.nearby_trades.map((t) => (
                <tr key={t.id} className="border-b border-zinc-800">
                  <td className="px-2 py-1">{t.id}</td>
                  <td className="px-2 py-1">{t.strategy_name}</td>
                  <td className="px-2 py-1">{t.status}</td>
                  <td className="px-2 py-1">{fmtTimestamp(t.opened_at)}</td>
                  <td className="px-2 py-1">{fmtTimestamp(t.closed_at)}</td>
                  <td className="px-2 py-1 text-right tabular-nums">
                    {fmtMoney(t.realized_pnl_dollars, { nullText: 'Pending' })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {data.data_quality_flags.length > 0 ? (
        <section>
          <header className="mb-1 text-xs uppercase tracking-wide text-zinc-400">
            Data quality
          </header>
          <OptionsFlagList flags={data.data_quality_flags} />
        </section>
      ) : null}
    </div>
  );
}
