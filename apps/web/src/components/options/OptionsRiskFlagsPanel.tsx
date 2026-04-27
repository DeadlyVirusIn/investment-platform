// Phase 11F — Risk dashboard flag panel.
// Aggregates the three model-limitation flags + per-flag counts so the
// operator never reads a clean "$X exposure" number without knowing
// which categories of uncertainty are present.

import type { RiskSummary } from '@/lib/options/optionsApi';
import { OptionsFlagList, flagLabel } from './OptionsFlagChip';

export default function OptionsRiskFlagsPanel({
  data,
}: { data: RiskSummary }) {
  return (
    <section className="space-y-2">
      <header className="text-xs uppercase tracking-wide text-zinc-400">
        Model limitations
      </header>
      {data.data_quality_flags.length === 0 ? (
        <div className="text-sm text-zinc-400">
          No model-limitation flags from any tracked event so far.
        </div>
      ) : (
        <OptionsFlagList flags={data.data_quality_flags} />
      )}

      <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
        <FlagCount
          token="ASSIGNMENT_SIMPLIFIED_EXIT"
          count={data.n_assignment_events}
        />
        <FlagCount
          token="PIN_RISK_UNCERTAIN_OUTCOME"
          count={data.n_pin_risk_events}
        />
        <FlagCount
          token="MISSING_SETTLEMENT"
          count={data.n_missing_settlement_events}
        />
      </div>

      <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3 text-xs text-zinc-400">
        <p className="font-semibold text-zinc-200">Reading these flags</p>
        <p className="mt-1">
          <strong>Assignment — simplified exit model:</strong> v1 paper engine
          records assignment as a terminal event; final payoff is taken at
          intrinsic value and no synthetic equity position is created.
        </p>
        <p className="mt-1">
          <strong>Pin risk — outcome uncertain:</strong> Settlement within $0.05
          of a strike. The recorded payoff is a model approximation; real-world
          assignment behavior is settlement-time-dependent.
        </p>
        <p className="mt-1">
          <strong>Missing settlement — expiry unresolved:</strong> No
          settlement price was supplied; do not treat the recorded PnL as
          final.
        </p>
      </div>
    </section>
  );
}

function FlagCount({ token, count }: { token: string; count: number }) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-2">
      <div className="text-[11px] uppercase tracking-wide text-zinc-400">
        {flagLabel(token)}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-zinc-100">
        {count}
      </div>
    </div>
  );
}
