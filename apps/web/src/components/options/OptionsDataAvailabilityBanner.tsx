// Phase 11Z — top-level banner showing the options data-availability
// state. Three explicit states:
//
//   STATE 1 — no chain data
//     options_chain_snapshot_count == 0
//     → "No options chain data ingested"
//     → instruct operator to run scripts/ingest_options_chain.py
//
//   STATE 2 — chain available but no shadow evaluations yet
//     chain count > 0, shadow.total_runs == 0
//     → "Chain ingested. Shadow evaluator has not run yet"
//     → instruct operator to run scripts/run_options_shadow_eval
//
//   STATE 3 — shadow evaluations available
//     shadow.total_runs > 0
//     → render silently; sub-pages show their own data
//
// Read-only. Reads /options/pipeline-status (chain count + max date)
// and /options/shadow/summary (run count). Does NOT trigger writes,
// scheduling, or any POSTs.

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

interface ShadowSummary {
  active: boolean;
  latest_run_date: string | null;
  total_runs: number;
  freshness_warnings: string[];
}

interface PipelineStatus {
  active: boolean;
  options_chain_snapshot_count: number;
  options_chain_snapshot_max_date: string | null;
  options_paper_trade_count: number;
}

export default function OptionsDataAvailabilityBanner() {
  const shadow = useQuery<ShadowSummary>({
    queryKey: ['options', 'shadow', 'summary'],
    queryFn: () => apiGet<ShadowSummary>('/options/shadow/summary'),
    staleTime: 60_000,
  });
  const pipeline = useQuery<PipelineStatus>({
    queryKey: ['options', 'pipeline-status'],
    queryFn: () => apiGet<PipelineStatus>('/options/pipeline-status'),
    staleTime: 60_000,
  });

  const chainCount = pipeline.data?.options_chain_snapshot_count ?? null;
  const chainMaxDate = pipeline.data?.options_chain_snapshot_max_date ?? null;
  const shadowRuns = shadow.data?.total_runs ?? null;

  // STATE 1 — no chain data ingested yet.
  if (chainCount === 0) {
    return (
      <div
        role="status"
        data-test="options-banner-no-chain"
        className="mb-3 rounded-md border border-zinc-700 bg-zinc-900/60 px-3 py-2 text-sm text-zinc-200"
      >
        <div className="font-semibold">No options chain data ingested</div>
        <div className="text-xs text-zinc-400 mt-1 leading-relaxed">
          options_chain_snapshot is empty. The platform has no options
          quotes to evaluate. Operator must ingest a chain snapshot first
          (CSV or provider). NO live feed is connected; this is a
          paper-only environment.{' '}
          <code className="text-zinc-300">
            OPTIONS_CHAIN_INGEST_CONFIRM=I_UNDERSTAND_THIS_WRITES_OPTIONS_CHAIN_DATA
            python -m scripts.ingest_options_chain --symbol SPY
            --as-of YYYY-MM-DD --source csv --csv path/to/chain.csv --commit
          </code>
        </div>
      </div>
    );
  }

  // STATE 2 — chain data exists, shadow evaluator not run yet.
  if (chainCount !== null && chainCount > 0 && shadowRuns === 0) {
    return (
      <div
        role="status"
        data-test="options-banner-chain-no-evals"
        className="mb-3 rounded-md border border-amber-700 bg-amber-900/20 px-3 py-2 text-sm text-zinc-200"
      >
        <div className="font-semibold">
          Options chain ingested · shadow evaluator has not run yet
        </div>
        <div className="text-xs text-zinc-400 mt-1 leading-relaxed">
          {chainCount} chain rows present
          {chainMaxDate ? ` (latest snapshot ${chainMaxDate})` : ''} but
          options_shadow_decision_log is empty. Evaluator runs only when
          an operator triggers it manually:{' '}
          <code className="text-zinc-300">
            OPTIONS_SHADOW_EVAL_ENABLED=true python -m
            scripts.run_options_shadow_eval --date YYYY-MM-DD --commit
          </code>
          . Only options_shadow_decision_log receives writes — no
          trades are opened.
        </div>
      </div>
    );
  }

  // STATE 3 — evaluations available; sub-pages render their own data.
  return null;
}
