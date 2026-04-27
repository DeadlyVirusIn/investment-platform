// Phase 11F — Options feature cards.
// Read-only. Shows derived features. No strategy recommendations.

import type { FeatureRow, FeaturesResponse } from '@/lib/options/optionsApi';
import { OptionsFlagList } from './OptionsFlagChip';
import { fmtPct, fmtRaw } from './format';

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

export default function OptionsFeatureCards({
  data,
}: { data: FeaturesResponse }) {
  const f: FeatureRow | null = data.features;
  if (!f) {
    return (
      <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-4 text-sm text-zinc-400">
        No feature row computed for this symbol yet. The feature engine writes
        one row per (as_of_date, underlying); insufficient inputs would surface
        here as data quality flags rather than fabricated values.
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-4">
        <Card label="ATM IV"               value={fmtPct(f.atm_iv)} />
        <Card label="IV rank (252d)"       value={fmtPct(f.iv_rank_252d)} />
        <Card label="IV percentile (252d)" value={fmtPct(f.iv_percentile_252d)} />
        <Card label="Realized vol 20d"     value={fmtPct(f.realized_vol_20d)} />
        <Card label="VRP 30d"              value={fmtPct(f.vrp_30d)} />
        <Card label="Skew 25Δ"             value={fmtRaw(f.skew_25d, { digits: 4 })} />
        <Card label="Term structure 30/90" value={fmtRaw(f.term_structure_30_90, { digits: 4 })} />
        <Card label="Put/Call volume"      value={fmtRaw(f.put_call_volume_ratio, { digits: 3 })} />
        <Card label="Put/Call OI"          value={fmtRaw(f.put_call_oi_ratio, { digits: 3 })} />
        <Card label="Unusual call vol z"   value={fmtRaw(f.unusual_call_volume_z, { digits: 2 })} />
        <Card label="Unusual put vol z"    value={fmtRaw(f.unusual_put_volume_z, { digits: 2 })} />
        <Card
          label="Gamma exposure proxy"
          value={fmtRaw(f.gamma_exposure_proxy, { digits: 0 })}
          hint={data.gamma_exposure_label}
        />
        <Card label="Call wall strike"     value={fmtRaw(f.call_wall_strike, { digits: 2 })} />
        <Card label="Put wall strike"      value={fmtRaw(f.put_wall_strike,  { digits: 2 })} />
      </div>
      <div>
        <div className="mb-1 text-xs uppercase tracking-wide text-zinc-400">
          Data quality
        </div>
        {f.data_quality_flags.length === 0 ? (
          <span className="text-xs text-zinc-500">No flags</span>
        ) : (
          <OptionsFlagList flags={f.data_quality_flags} />
        )}
      </div>
    </div>
  );
}
