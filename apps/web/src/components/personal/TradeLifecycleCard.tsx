// Personal-Analytics — read-only Trade Lifecycle card.
//
// Reads /api/performance/paper/lifecycle and renders a frozen-vocab
// timeline per trade: entry → monitoring → exit_recorded →
// label_pending → label_available. Label vocab is locked to the API
// `lifecycle_statuses` and `lifecycle_stages` arrays.
//
// No buttons. No mutations. Purely diagnostic.

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

interface LifecycleTrade {
  trade_id: string;
  symbol: string;
  source: string;
  is_replay: boolean;
  side: string;
  entry_ts: string | null;
  entry_price: number;
  quantity: number;
  notional_usd: number;
  latest_price: number | null;
  latest_price_ts: string | null;
  unrealized_pnl_usd: number | null;
  unrealized_return_pct: number | null;
  days_open: number | null;
  lifecycle_status:
    'entered' | 'open_pending' | 'closed' |
    'outcome_pending' | 'outcome_labeled';
  current_stage:
    'entry' | 'monitoring' | 'exit_recorded' |
    'label_pending' | 'label_available';
  linked_ids: {
    recommendation_id: string | null;
    decision_log_id: string | null;
    recommendation_outcome_id: string | null;
    replay_run_id: string | null;
    position_id: string | null;
  };
  data_quality: {
    has_entry: boolean;
    has_latest_price: boolean;
    has_exit: boolean;
    has_label: boolean;
    has_recommendation_outcome_row: boolean;
    missing_reason: string | null;
  };
}

interface LifecycleResponse {
  include_replay: boolean;
  as_of: string;
  count: number;
  lifecycle_statuses: string[];
  lifecycle_stages: string[];
  status_counts: Record<string, number>;
  trades: LifecycleTrade[];
}

const STAGE_ORDER: LifecycleTrade['current_stage'][] = [
  'entry', 'monitoring', 'exit_recorded',
  'label_pending', 'label_available',
];
const STAGE_LABEL: Record<LifecycleTrade['current_stage'], string> = {
  entry:           'Entered',
  monitoring:      'Monitoring',
  exit_recorded:   'Exit recorded',
  label_pending:   'Label pending',
  label_available: 'Label available',
};

const fmtUsd = (n: number | null | undefined) =>
  n == null ? '—' : `$${n.toFixed(2)}`;
const fmtPct = (n: number | null | undefined) =>
  n == null ? '—' : `${(n * 100).toFixed(2)}%`;

export default function TradeLifecycleCard() {
  const [includeReplay, setIncludeReplay] = useState(true);
  const q = useQuery<LifecycleResponse>({
    queryKey: ['perf-paper', 'lifecycle', includeReplay],
    queryFn: () => apiGet<LifecycleResponse>(
      `/performance/paper/lifecycle${
        includeReplay ? '?include_replay=true' : ''}`,
    ),
    staleTime: 30_000,
  });
  const rows = q.data?.trades ?? [];
  const sc = q.data?.status_counts ?? {};

  return (
    <section
      data-test="trade-lifecycle-card"
      className="rounded-md border border-zinc-700 bg-zinc-900/40 p-4 mb-4"
    >
      <header className="flex items-baseline justify-between mb-3">
        <h3 className="text-sm font-semibold text-zinc-100">
          Trade Lifecycle — entry → monitoring → exit → label
        </h3>
        <label className="text-xs flex items-center gap-2">
          <input
            type="checkbox"
            checked={includeReplay}
            onChange={e => setIncludeReplay(e.target.checked)}
          />
          <span>Include recovered replay</span>
        </label>
      </header>

      <div
        data-test="trade-lifecycle-disclaimer"
        className="text-[11px] text-zinc-500 mb-3"
      >
        Read-only diagnostic. No action recommendation, no execution.
        Vocabulary frozen: {q.data?.lifecycle_stages?.join(' · ') ?? '—'}.
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-3 text-xs">
        <Counter label="entered"          v={sc.entered ?? 0} />
        <Counter label="open_pending"     v={sc.open_pending ?? 0} />
        <Counter label="closed"           v={sc.closed ?? 0} />
        <Counter label="outcome_pending"  v={sc.outcome_pending ?? 0} />
        <Counter label="outcome_labeled"  v={sc.outcome_labeled ?? 0} />
      </div>

      {rows.length === 0 ? (
        <div className="rounded border border-zinc-800 px-3 py-2 text-xs text-zinc-400">
          {includeReplay
            ? 'No trades found.'
            : 'No live trades. Toggle "Include recovered replay" to see recovered rows.'}
        </div>
      ) : (
        <div className="space-y-2">
          {rows.map(t => (
            <LifecycleRow key={t.trade_id} t={t} />
          ))}
        </div>
      )}
    </section>
  );
}

function Counter({ label, v }: { label: string; v: number }) {
  return (
    <div className="rounded border border-zinc-800 px-2 py-1">
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div className="text-base font-semibold text-zinc-100">{v}</div>
    </div>
  );
}

function LifecycleRow({ t }: { t: LifecycleTrade }) {
  return (
    <div className="rounded border border-zinc-800 p-2 text-xs">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className="font-mono text-zinc-100">{t.symbol}</span>
          <span className="text-zinc-500">
            {t.entry_ts ? t.entry_ts.slice(0, 10) : '—'}
          </span>
          {t.is_replay && (
            <span
              data-test="lifecycle-replay-chip"
              className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/40 text-amber-300"
              title="Recovered replay — not live trading activity"
            >
              Recovered replay — not live trading activity
            </span>
          )}
        </div>
        <div className="text-zinc-500">
          {t.days_open == null ? '—' : `${t.days_open.toFixed(1)}d`}
          {' · '}
          {t.unrealized_pnl_usd == null
            ? <span className="text-zinc-500">unrealized unavailable</span>
            : (
              <span className={
                t.unrealized_pnl_usd >= 0
                  ? 'text-emerald-300' : 'text-rose-300'
              }>
                {fmtUsd(t.unrealized_pnl_usd)} ({fmtPct(t.unrealized_return_pct)})
              </span>
            )
          }
        </div>
      </div>

      {/* Stage timeline */}
      <div className="flex items-center gap-1">
        {STAGE_ORDER.map((stage, i) => {
          const reached = STAGE_ORDER.indexOf(t.current_stage) >= i;
          return (
            <div key={stage} className="flex items-center gap-1">
              <span
                data-test={`stage-${stage}`}
                className={
                  'text-[10px] px-1.5 py-0.5 rounded ' +
                  (reached
                    ? stage === 'label_available'
                      ? 'bg-emerald-900/40 text-emerald-300'
                      : stage === t.current_stage
                        ? 'bg-amber-900/40 text-amber-300'
                        : 'bg-zinc-800 text-zinc-300'
                    : 'bg-zinc-900 text-zinc-600 border border-dashed border-zinc-800')
                }
              >
                {STAGE_LABEL[stage]}
              </span>
              {i < STAGE_ORDER.length - 1 && (
                <span className="text-zinc-600">→</span>
              )}
            </div>
          );
        })}
        <span className="ml-auto text-[10px] text-zinc-500">
          status: {t.lifecycle_status}
        </span>
      </div>

      {!t.data_quality.has_label && !t.data_quality.has_exit && (
        <div
          data-test="waiting-natural-exit"
          className="mt-1.5 text-[11px] text-zinc-500"
        >
          Waiting for natural exit — no forced close.
          {t.data_quality.missing_reason && (
            <> Missing: {t.data_quality.missing_reason}.</>
          )}
        </div>
      )}
    </div>
  );
}
