// Options Visibility — types + read-only TanStack Query hook.
//
// Single source: GET /api/options/pipeline-status
// (apps/api/src/options/routes_readonly.py). Read-only; honest
// null/unknown values. No mutation, no trading, no execution.

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

export interface OptionsChainHealth {
  symbol: string;
  rows: number;
  valid_bid_ask: number;          // count(bid>0 AND ask>bid)
  latest_snapshot_at: string | null;
}

export interface OptionsCandidateStructure {
  structure: string;              // rule_id, e.g. LONG_CALL, IRON_CONDOR
  count: number;
  engine_compatible: boolean;
}

export interface OptionsCandidateUniverse {
  total: number;
  engine_compatible: number;
  engine_incompatible: number;
  by_structure: OptionsCandidateStructure[];
}

export interface OptionsLatestIngestRun {
  started_at: string | null;
  finished_at: string | null;
  provider: string | null;
  rows_inserted: number | null;
  rows_filtered_out: number | null;
  n_symbols_ok: number | null;
  classification: string | null;
}

export interface OptionsPipelineStatus {
  // Engine state
  engine_state: string;           // dormant | unscheduled | starting | active
  engine_state_sentence: string;

  // Flag truths
  options_enabled: boolean;
  options_paper_only: boolean;
  options_shadow_eval_enabled: boolean;
  options_ml_can_affect_trades: boolean;
  scheduler_jobs_count: number;

  // Chain / feature / shadow / paper counts
  options_chain_snapshot_count: number;
  options_chain_snapshot_max_ts: string | null;
  options_chain_snapshot_max_date: string | null;
  options_feature_daily_count: number;
  options_feature_daily_max_date: string | null;
  options_shadow_decision_count: number;
  options_strategy_outcome_count: number;
  options_paper_trade_count: number;

  // P0d additive read-only fields
  chain_provider: string | null;
  chain_provider_version: string | null;
  latest_ingest_run: OptionsLatestIngestRun | null;
  chain_health: OptionsChainHealth[];
  supported_strategies: string[];
  candidate_universe: OptionsCandidateUniverse;

  notice: string;
}

export function useOptionsVisibility() {
  return useQuery<OptionsPipelineStatus>({
    queryKey: ['options', 'pipeline-status'],
    queryFn: () => apiGet<OptionsPipelineStatus>('/options/pipeline-status'),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}
