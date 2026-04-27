// Phase 11F — Risk dashboard summary cards.
// Net Greeks come from entry-time per-leg Greeks (naive proxy).
// Label surfaced explicitly so users do not confuse with live MTM.

import type { RiskSummary } from '@/lib/options/optionsApi';
import { fmtMoney, fmtRaw } from './format';

function Card({
  label, value, hint,
}: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/50 px-3 py-2">
      <div className="text-xs uppercase tracking-wide text-zinc-400">{label}</div>
      <div className="mt-1 text-lg font-semibold text-zinc-100 tabular-nums">
        {value}
      </div>
      {hint ? <div className="mt-1 text-[11px] text-zinc-500">{hint}</div> : null}
    </div>
  );
}

export default function OptionsRiskSummaryCards({
  data,
}: { data: RiskSummary }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
        <Card label="Open trades"
              value={String(data.n_open_trades)} />
        <Card label="Max loss exposure"
              value={fmtMoney(data.max_loss_exposure_dollars)} />
        <Card label="Net delta"
              value={fmtRaw(data.net_delta, { digits: 4 })}
              hint={data.greeks_source_label} />
        <Card label="Net gamma"
              value={fmtRaw(data.net_gamma, { digits: 4 })}
              hint={data.greeks_source_label} />
        <Card label="Net theta"
              value={fmtRaw(data.net_theta, { digits: 4 })}
              hint={data.greeks_source_label} />
        <Card label="Net vega"
              value={fmtRaw(data.net_vega, { digits: 4 })}
              hint={data.greeks_source_label} />
      </div>
    </div>
  );
}
