// Phase 1C — Options Diagnostics truth split.
// Splits previously-mixed diagnostics into four clearly separated cards:
//   1. Chain Coverage     — what raw options data we actually have
//   2. Shadow Evaluator   — read-only candidate evaluation output
//   3. Strategy Suggestions — qualified candidates surfaced by evaluator,
//                             execution_allowed=false (live exec blocked)
//   4. Paper Trades       — rows from options_paper_trade
//
// All four cards are read-only. NO trade execution wiring.
// Surfaces the known live-execution blocker
// (`_build_legs_payload` field mismatch) on the Suggestions card.

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';
import OptionsPaperOnlyBanner from '@/components/options/OptionsPaperOnlyBanner';
import OptionsObservationOnlyBanner from '@/components/options/OptionsObservationOnlyBanner';
import {
  useOptionsDiagnostics,
  useOptionsSymbols,
  useOptionsEvaluationScores,
  useOptionsPaperTrades,
} from '@/lib/options/hooks';

const LOOKBACKS = [7, 14, 30, 60, 90] as const;

const EXECUTION_BLOCKER_NOTE =
  'Options live execution blocked by _build_legs_payload field mismatch.';

interface PipelineStatus {
  active: boolean;
  last_run: string | null;
  reason: string;
  options_chain_snapshot_count: number;
  options_chain_snapshot_max_date: string | null;
  options_feature_daily_count: number;
  options_feature_daily_max_date: string | null;
  options_paper_trade_count: number;
  options_paper_trade_max_date: string | null;
  next_phase_required: string;
  notice: string;
}

interface ShadowSummary {
  active: boolean;
  latest_run_date: string | null;
  total_runs: number;
  contracts_evaluated?: number;
  would_trade_count?: number;
  underlying_count?: number;
  blocked_reason_counts?: Record<string, number>;
  freshness_warnings: string[];
}

export default function OptionsStrategyDiagnosticsPage() {
  const symbolsQ = useOptionsSymbols();
  const [lookback, setLookback] = useState<number>(30);
  const [underlying, setUnderlying] = useState<string | undefined>(undefined);

  return (
    <div className="space-y-4">
      <OptionsPaperOnlyBanner />
      <OptionsObservationOnlyBanner />

      <section className="flex flex-wrap items-end gap-3">
        <label className="text-xs">
          <div className="mb-1 uppercase tracking-wide text-zinc-400">Lookback</div>
          <select
            value={lookback}
            onChange={(e) => setLookback(Number(e.target.value))}
            className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
          >
            {LOOKBACKS.map((n) => (
              <option key={n} value={n}>{n} days</option>
            ))}
          </select>
        </label>
        <label className="text-xs">
          <div className="mb-1 uppercase tracking-wide text-zinc-400">Underlying</div>
          <select
            value={underlying ?? ''}
            onChange={(e) => setUnderlying(e.target.value || undefined)}
            className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
          >
            <option value="">(all)</option>
            {(symbolsQ.data?.symbols ?? []).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
      </section>

      <ChainCoverageCard
        lookback={lookback}
        underlying={underlying}
        symbols={symbolsQ.data?.symbols ?? []}
      />
      <ShadowEvaluatorCard />
      <StrategySuggestionsCard
        lookback={lookback}
        underlying={underlying}
      />
      <PaperTradesCard underlying={underlying} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// shared primitives
// ---------------------------------------------------------------------------

function CardShell({
  title, source, children, headerExtra,
}: {
  title: string;
  source: string;
  children: React.ReactNode;
  headerExtra?: React.ReactNode;
}) {
  return (
    <section
      className="rounded-md border border-zinc-700 bg-zinc-900/40 p-4"
    >
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">{title}</h2>
          <div className="mt-0.5 text-[10px] uppercase tracking-wide text-zinc-500">
            source: {source}
          </div>
        </div>
        {headerExtra}
      </header>
      {children}
    </section>
  );
}

function StatBlock({
  label, value, hint, warn,
}: {
  label: string; value: string | number; hint?: string; warn?: boolean;
}) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/50 px-3 py-2">
      <div className="text-xs uppercase tracking-wide text-zinc-400">{label}</div>
      <div className={
        'mt-1 text-lg font-semibold tabular-nums ' +
        (warn ? 'text-amber-300' : 'text-zinc-100')
      }>{value}</div>
      {hint ? <div className="mt-1 text-[11px] text-zinc-500">{hint}</div> : null}
    </div>
  );
}

function EmptyState({ note }: { note: string }) {
  return (
    <div className="rounded border border-dashed border-zinc-800 px-3 py-4 text-xs text-zinc-500">
      {note}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card 1 — Chain Coverage
// ---------------------------------------------------------------------------

function ChainCoverageCard({
  lookback, underlying, symbols,
}: {
  lookback: number;
  underlying: string | undefined;
  symbols: string[];
}) {
  const pipelineQ = useQuery<PipelineStatus>({
    queryKey: ['options', 'pipeline-status'],
    queryFn: () => apiGet<PipelineStatus>('/options/pipeline-status'),
    staleTime: 60_000,
  });
  const diagQ = useOptionsDiagnostics({
    lookback_days: lookback,
    underlying,
  });

  const p = pipelineQ.data;
  const d = diagQ.data;

  const hasChain =
    !!p && p.options_chain_snapshot_count > 0;
  const missingChainWarning =
    !p || p.options_chain_snapshot_count === 0 || !p.options_chain_snapshot_max_date;

  return (
    <CardShell
      title="Chain Coverage"
      source="GET /options/pipeline-status · GET /options/symbols · GET /options/diagnostics (chain section)"
      headerExtra={
        missingChainWarning ? (
          <span className="rounded border border-amber-700/60 bg-amber-900/20 px-2 py-0.5 text-[10px] uppercase tracking-wide text-amber-300">
            Missing chain
          </span>
        ) : null
      }
    >
      {pipelineQ.isLoading ? (
        <p className="text-xs text-zinc-400">Loading chain status…</p>
      ) : !hasChain ? (
        <EmptyState note="No options chain rows ingested. Run options_chain_snapshot worker / backfill before diagnostics will populate." />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <StatBlock
              label="Total chain rows"
              value={p!.options_chain_snapshot_count}
              hint="options_chain_snapshot table"
            />
            <StatBlock
              label="Latest chain date"
              value={p!.options_chain_snapshot_max_date ?? '—'}
              warn={!p!.options_chain_snapshot_max_date}
            />
            <StatBlock
              label="Underlyings available"
              value={symbols.length}
              hint={symbols.length > 0
                ? symbols.slice(0, 6).join(', ') + (symbols.length > 6 ? '…' : '')
                : 'no symbols'}
            />
            <StatBlock
              label="Feature rows"
              value={p!.options_feature_daily_count}
              hint={p!.options_feature_daily_max_date ?? '—'}
            />
          </div>

          <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-3">
            <StatBlock
              label={`Chain rows (last ${lookback}d)`}
              value={d?.chain.n_rows ?? '—'}
            />
            <StatBlock
              label="Missing IV"
              value={d?.chain.n_missing_iv ?? '—'}
              warn={(d?.chain.n_missing_iv ?? 0) > 0}
            />
            <StatBlock
              label="Missing Greeks"
              value={d?.chain.n_missing_greeks ?? '—'}
              warn={(d?.chain.n_missing_greeks ?? 0) > 0}
            />
          </div>

          {missingChainWarning ? (
            <p className="mt-3 text-[11px] text-amber-300">
              Missing-chain warning: max snapshot date is unset — most
              downstream cards will be empty until next ingest.
            </p>
          ) : null}
        </>
      )}
    </CardShell>
  );
}

// ---------------------------------------------------------------------------
// Card 2 — Shadow Evaluator
// ---------------------------------------------------------------------------

function ShadowEvaluatorCard() {
  const shadowQ = useQuery<ShadowSummary>({
    queryKey: ['options', 'shadow', 'summary'],
    queryFn: () => apiGet<ShadowSummary>('/options/shadow/summary'),
    staleTime: 60_000,
  });

  const s = shadowQ.data;
  const blocked = s?.blocked_reason_counts ?? {};
  const blockedRows = Object.entries(blocked)
    .sort((a, b) => b[1] - a[1]);

  return (
    <CardShell
      title="Shadow Evaluator"
      source="GET /options/shadow/summary"
      headerExtra={
        <span className="rounded border border-zinc-700 bg-zinc-950 px-2 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">
          Shadow-only · no execution
        </span>
      }
    >
      {shadowQ.isLoading ? (
        <p className="text-xs text-zinc-400">Loading shadow summary…</p>
      ) : !s || s.total_runs === 0 ? (
        <EmptyState note="No shadow evaluator runs yet. Once OPTIONS_SHADOW_EVAL_ENABLED is set and the daily job fires, evaluated/blocked candidate counts will appear here." />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <StatBlock
              label="Active"
              value={s.active ? 'YES' : 'NO'}
              warn={!s.active}
            />
            <StatBlock
              label="Latest run"
              value={s.latest_run_date ?? '—'}
            />
            <StatBlock
              label="Contracts evaluated"
              value={s.contracts_evaluated ?? 0}
              hint="latest run"
            />
            <StatBlock
              label="Would-trade (eval only)"
              value={s.would_trade_count ?? 0}
              hint="never reaches executor"
            />
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
            <StatBlock
              label="Underlyings"
              value={s.underlying_count ?? 0}
            />
            <StatBlock
              label="Total shadow runs"
              value={s.total_runs}
            />
          </div>

          <div className="mt-3">
            <h3 className="mb-1 text-xs font-semibold text-zinc-300">
              Block reasons (latest run)
            </h3>
            {blockedRows.length === 0 ? (
              <EmptyState note="No blocked candidates on latest run." />
            ) : (
              <table className="w-full text-xs">
                <thead className="text-zinc-500">
                  <tr>
                    <th className="px-2 py-1 text-left">Reason</th>
                    <th className="px-2 py-1 text-right">Count</th>
                  </tr>
                </thead>
                <tbody>
                  {blockedRows.map(([reason, n]) => (
                    <tr key={reason} className="border-b border-zinc-800">
                      <td className="px-2 py-1 text-zinc-300">{reason}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{n}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {s.freshness_warnings.length > 0 ? (
            <div className="mt-3 rounded border border-amber-700/60 bg-amber-900/20 px-3 py-2 text-[11px] text-amber-300">
              {s.freshness_warnings.join(' · ')}
            </div>
          ) : null}
        </>
      )}
    </CardShell>
  );
}

// ---------------------------------------------------------------------------
// Card 3 — Strategy Suggestions
// ---------------------------------------------------------------------------

function StrategySuggestionsCard({
  lookback, underlying,
}: {
  lookback: number;
  underlying: string | undefined;
}) {
  const evalQ = useOptionsEvaluationScores({
    qualified_only: true,
    lookback_days: lookback,
    underlying,
    limit: 25,
  });

  const scores = evalQ.data?.scores ?? [];

  return (
    <CardShell
      title="Strategy Suggestions"
      source="GET /options/evaluation/scores?qualified_only=true"
      headerExtra={
        <span className="rounded border border-rose-700/60 bg-rose-900/20 px-2 py-0.5 text-[10px] uppercase tracking-wide text-rose-300">
          execution_allowed = false
        </span>
      }
    >
      <div className="mb-3 rounded border border-amber-700/60 bg-amber-900/20 px-3 py-2 text-[11px] text-amber-200">
        {EXECUTION_BLOCKER_NOTE} Suggestions are read-only candidates from
        the evaluator — they are NOT routed to any executor in this phase.
      </div>

      {evalQ.isLoading ? (
        <p className="text-xs text-zinc-400">Loading suggestions…</p>
      ) : scores.length === 0 ? (
        <EmptyState note="No qualified suggestions in the lookback window. Either no observations cleared the threshold, or the evaluator has not produced rows for the selected filters." />
      ) : (
        <table className="w-full text-xs">
          <thead className="text-zinc-500">
            <tr>
              <th className="px-2 py-1 text-left">As of</th>
              <th className="px-2 py-1 text-left">Underlying</th>
              <th className="px-2 py-1 text-left">Rule</th>
              <th className="px-2 py-1 text-right">Score</th>
              <th className="px-2 py-1 text-left">Flags</th>
              <th className="px-2 py-1 text-left">Exec</th>
            </tr>
          </thead>
          <tbody>
            {scores.map((s) => (
              <tr key={s.id} className="border-b border-zinc-800">
                <td className="px-2 py-1 text-zinc-400">{s.as_of_date}</td>
                <td className="px-2 py-1 text-zinc-200">{s.underlying}</td>
                <td className="px-2 py-1 text-zinc-300">{s.rule_id}</td>
                <td className="px-2 py-1 text-right tabular-nums text-zinc-100">
                  {s.total_score.toFixed(1)}
                </td>
                <td className="px-2 py-1 text-zinc-400">
                  {s.flags.length === 0 ? '—' : s.flags.join(', ')}
                </td>
                <td className="px-2 py-1 text-rose-300">blocked</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <p className="mt-3 text-[11px] text-zinc-500">
        Scores reflect rule-level qualification only. They are not order
        intents and do not imply execution_allowed. The live-execution
        path remains disabled until the legs-payload field mismatch in
        <code className="mx-1 rounded bg-zinc-800 px-1">
          scripts/run_options_paper_exec.py:_build_legs_payload
        </code>
        is fixed in a separate phase.
      </p>
    </CardShell>
  );
}

// ---------------------------------------------------------------------------
// Card 4 — Paper Trades
// ---------------------------------------------------------------------------

function PaperTradesCard({
  underlying,
}: {
  underlying: string | undefined;
}) {
  const tradesQ = useOptionsPaperTrades({
    underlying,
    limit: 25,
  });

  const trades = tradesQ.data?.trades ?? [];

  return (
    <CardShell
      title="Paper Trades"
      source="GET /options/paper-trades"
      headerExtra={
        <span className="rounded border border-emerald-700/60 bg-emerald-900/20 px-2 py-0.5 text-[10px] uppercase tracking-wide text-emerald-300">
          paper_only = true
        </span>
      }
    >
      {tradesQ.isLoading ? (
        <p className="text-xs text-zinc-400">Loading paper trades…</p>
      ) : trades.length === 0 ? (
        <EmptyState note="No options paper trades match the selected underlying. The options_paper_trade table currently holds backfill rows only — automatic seeding is gated on the execution blocker noted above." />
      ) : (
        <table className="w-full text-xs">
          <thead className="text-zinc-500">
            <tr>
              <th className="px-2 py-1 text-left">ID</th>
              <th className="px-2 py-1 text-left">Underlying</th>
              <th className="px-2 py-1 text-left">Strategy</th>
              <th className="px-2 py-1 text-left">Status</th>
              <th className="px-2 py-1 text-left">Opened</th>
              <th className="px-2 py-1 text-right">Entry credit ($)</th>
              <th className="px-2 py-1 text-right">Exit debit ($)</th>
              <th className="px-2 py-1 text-right">Realized PnL ($)</th>
              <th className="px-2 py-1 text-left">Fill model</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.id} className="border-b border-zinc-800">
                <td className="px-2 py-1 text-zinc-400">{t.id}</td>
                <td className="px-2 py-1 text-zinc-200">{t.underlying}</td>
                <td className="px-2 py-1 text-zinc-300">
                  {t.strategy_name}
                  <span className="ml-1 text-[10px] text-zinc-500">
                    v{t.strategy_version}
                  </span>
                </td>
                <td className="px-2 py-1 text-zinc-300">{t.status}</td>
                <td className="px-2 py-1 text-zinc-400">
                  {t.opened_at ?? '—'}
                </td>
                <td className="px-2 py-1 text-right tabular-nums text-zinc-100">
                  {t.entry_credit_dollars ?? '—'}
                </td>
                <td className="px-2 py-1 text-right tabular-nums text-zinc-100">
                  {t.exit_debit_dollars ?? '—'}
                </td>
                <td className="px-2 py-1 text-right tabular-nums text-zinc-100">
                  {t.realized_pnl_dollars ?? '—'}
                </td>
                <td className="px-2 py-1 text-zinc-500">
                  {t.fill_model_version}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <p className="mt-3 text-[11px] text-zinc-500">
        Leg detail (strikes, qty, entry/exit prices) is available on the
        Paper Trades tab via the row-level drawer. This card lists
        headers only so it stays cheap to render.
      </p>
    </CardShell>
  );
}
