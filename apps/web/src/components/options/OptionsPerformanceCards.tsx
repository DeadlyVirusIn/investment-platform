// Phase 11G — paper performance summary cards.
// All metrics scoped to closed/expired/assigned trades.
// Flag chips appear when assignment / pin-risk / missing-settlement
// outcomes contributed to the aggregate.

import type { PerformanceSummary } from '@/lib/options/optionsApi';
import { OptionsFlagList } from './OptionsFlagChip';
import { fmtMoney, fmtPct } from './format';

function Card({
  label, value, hint,
}: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/50 px-3 py-2">
      <div className="text-xs uppercase tracking-wide text-zinc-400">{label}</div>
      <div className="mt-1 text-lg font-semibold text-zinc-100 tabular-nums">{value}</div>
      {hint ? <div className="mt-1 text-[11px] text-zinc-500">{hint}</div> : null}
    </div>
  );
}

export default function OptionsPerformanceCards({
  data,
}: { data: PerformanceSummary }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
        <Card label="Closed trades"      value={String(data.n_closed_trades)} />
        <Card label="Win rate"           value={fmtPct(data.win_rate)} />
        <Card label="Max-loss hit rate"  value={fmtPct(data.max_loss_hit_rate)} />
        <Card label="Assignment rate"    value={fmtPct(data.assignment_rate)} />
        <Card
          label="Pin-risk freq."
          value={fmtPct(data.pin_risk_frequency_per_expiration_event)}
          hint="per expiration event"
        />
        <Card
          label="Missing settlement freq."
          value={fmtPct(data.missing_settlement_per_expiration_event)}
          hint="per expiration event"
        />
        <Card label="Total realized PnL" value={fmtMoney(data.total_realized_pnl_dollars)} />
        <Card label="Total fees"         value={fmtMoney(data.total_fees_dollars)} />
        <Card
          label="Fee drag (Σfees / Σ|PnL|)"
          value={fmtPct(data.fee_drag_ratio_of_abs_pnl)}
        />
      </div>
      {data.data_quality_flags.length > 0 ? (
        <div>
          <div className="mb-1 text-xs uppercase tracking-wide text-zinc-400">
            Aggregate model limitations
          </div>
          <OptionsFlagList flags={data.data_quality_flags} />
        </div>
      ) : null}
    </div>
  );
}
