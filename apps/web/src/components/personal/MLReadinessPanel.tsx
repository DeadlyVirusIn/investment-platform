// Personal-Analytics — read-only ML Readiness panel.
//
// Reads /api/ml/insights/readiness and renders the checklist + reason
// + warnings. No buttons. The panel never offers to train, score, or
// flip any flag. The "ML evaluation not ready — outcomes still
// pending." copy is rendered when labels are absent.

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

interface ChecklistItem { name: string; ok: boolean }

interface Readiness {
  ml_can_affect_trades: boolean;
  is_ready: boolean;
  reason: string;
  next_unlock_condition: string;
  required_min_labeled_trades: number;
  labeled_trade_count: number;
  pending_trade_count: number;
  open_position_count: number;
  replay_trade_count: number;
  live_trade_count: number;
  leakage_check_status: string;
  dataset_rows: number;
  feature_coverage: {
    feature_columns_defined: boolean;
    leakage_guard_implemented: boolean;
  };
  missing_requirements: string[];
  dataset_is_replay_only: boolean;
  warnings: string[];
  checklist: ChecklistItem[];
  notice: string;
}

const CHECKLIST_LABEL: Record<string, string> = {
  trades_exist:         'Trades exist',
  exits_recorded:       'Exits recorded',
  outcomes_labeled:     'Outcomes labeled',
  leakage_check_passed: 'Leakage check passed',
  enough_labels:        'Enough labels',
};

export default function MLReadinessPanel() {
  const q = useQuery<Readiness>({
    queryKey: ['ml-insights', 'readiness'],
    queryFn: () => apiGet<Readiness>('/ml/insights/readiness'),
    staleTime: 60_000,
  });
  const r = q.data;

  return (
    <section
      data-test="ml-readiness-panel"
      className="rounded-md border border-zinc-700 bg-zinc-900/40 p-4 mb-4"
    >
      <header className="flex items-baseline justify-between mb-3">
        <h3 className="text-sm font-semibold text-zinc-100">
          ML Readiness — read-only checklist
        </h3>
        <span className="text-[10px] uppercase tracking-wide text-amber-400">
          ML insight only — cannot affect trades
        </span>
      </header>

      <div
        data-test="ml-readiness-no-execute-banner"
        className="rounded border border-amber-700 bg-amber-900/20 px-3 py-2 text-xs text-zinc-200 mb-3"
      >
        ML_CAN_AFFECT_TRADES is pinned to <strong>false</strong>. This
        panel does not train, score, or write artifacts. State updates
        only when actual outcomes accumulate.
      </div>

      {/* State strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Cell label="Ready" value={r?.is_ready ? 'yes' : 'no'}
              tone={r?.is_ready ? 'good' : 'warn'} />
        <Cell label="Labeled trades"
              value={String(r?.labeled_trade_count ?? 0)}
              hint={`floor ${r?.required_min_labeled_trades ?? 20}`} />
        <Cell label="Pending outcomes"
              value={String(r?.pending_trade_count ?? 0)}
              tone="warn" />
        <Cell label="Open positions"
              value={String(r?.open_position_count ?? 0)} />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Cell label="Live trades"
              value={String(r?.live_trade_count ?? 0)} />
        <Cell label="Replay trades"
              value={String(r?.replay_trade_count ?? 0)}
              tone="warn" />
        <Cell label="Leakage check"
              value={r?.leakage_check_status ?? '—'}
              tone={r?.leakage_check_status === 'passed' ? 'good' : 'warn'} />
        <Cell label="Dataset rows"
              value={String(r?.dataset_rows ?? 0)} />
      </div>

      {/* Disabled-state copy */}
      {(r?.labeled_trade_count ?? 0) === 0 && (
        <div
          data-test="ml-readiness-disabled-copy"
          className="rounded border border-zinc-800 bg-zinc-900/60 px-3 py-2 text-xs text-amber-300 mb-3"
        >
          ML evaluation not ready — outcomes still pending.
          {r?.next_unlock_condition && (
            <div className="text-zinc-400 mt-1">
              {r.next_unlock_condition}
            </div>
          )}
        </div>
      )}

      {/* Replay-only warning */}
      {r?.dataset_is_replay_only && (
        <div
          data-test="ml-readiness-replay-warning"
          className="rounded border border-amber-700 bg-amber-900/20 px-3 py-2 text-xs text-zinc-200 mb-3"
        >
          {r.warnings[0] ??
            'Current dataset is replay-derived; treat model metrics as recovery diagnostics.'}
        </div>
      )}

      {/* Checklist */}
      <ul
        data-test="ml-readiness-checklist"
        className="text-xs text-zinc-300 space-y-1"
      >
        {r?.checklist?.map(item => (
          <li key={item.name} data-test={`check-${item.name}`}>
            <Badge ok={item.ok} />{' '}
            {CHECKLIST_LABEL[item.name] ?? item.name}
          </li>
        ))}
      </ul>

      {r?.missing_requirements?.length ? (
        <div
          data-test="ml-readiness-missing"
          className="text-[11px] text-zinc-500 mt-2"
        >
          Missing requirements: {r.missing_requirements.join(', ')}
        </div>
      ) : null}
    </section>
  );
}

function Cell({
  label, value, hint, tone,
}: {
  label: string; value: string; hint?: string;
  tone?: 'good' | 'warn';
}) {
  const cls =
    tone === 'good' ? 'text-emerald-300'
  : tone === 'warn' ? 'text-amber-300'
  : 'text-zinc-100';
  return (
    <div className="rounded border border-zinc-800 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div className={'text-lg font-semibold mt-0.5 ' + cls}>{value}</div>
      {hint && <div className="text-[10px] text-zinc-500 mt-0.5">{hint}</div>}
    </div>
  );
}

function Badge({ ok }: { ok: boolean }) {
  return (
    <span className={
      'inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold mr-1 ' +
      (ok ? 'bg-emerald-700/40 text-emerald-300'
          : 'bg-zinc-800 text-zinc-500')
    }>
      {ok ? '✓' : '·'}
    </span>
  );
}
