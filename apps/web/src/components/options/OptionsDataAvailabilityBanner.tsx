// Phase 11Z — top-level banner showing whether the platform has any
// options chain / shadow data ingested. Renders silently when data
// exists; renders a clear "no data ingested" message otherwise.
//
// Read-only. Does NOT trigger any data fetch beyond the existing
// /options/health, /options/symbols, /options/shadow/summary calls.

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

interface ShadowSummary {
  active: boolean;
  latest_run_date: string | null;
  total_runs: number;
  freshness_warnings: string[];
}

interface PaperTradesEnvelope {
  count: number;
}

export default function OptionsDataAvailabilityBanner() {
  const shadow = useQuery<ShadowSummary>({
    queryKey: ['options', 'shadow', 'summary'],
    queryFn: () => apiGet<ShadowSummary>('/options/shadow/summary'),
    staleTime: 60_000,
  });
  const trades = useQuery<PaperTradesEnvelope>({
    queryKey: ['options', 'paper-trades', 'count'],
    queryFn: () => apiGet<PaperTradesEnvelope>('/options/paper-trades?limit=1'),
    staleTime: 60_000,
  });

  const noShadow = shadow.data && shadow.data.total_runs === 0;
  const noTrades = trades.data && trades.data.count === 0;

  // Only surface the banner when BOTH are empty — that's the
  // "platform has no options data" state. If either has data, the
  // sub-pages will show it themselves.
  if (!noShadow || !noTrades) return null;

  return (
    <div
      role="status"
      className="mb-3 rounded-md border border-zinc-700 bg-zinc-900/60 px-3 py-2 text-sm text-zinc-200"
    >
      <div className="font-semibold">No options data ingested yet</div>
      <div className="text-xs text-zinc-400 mt-1 leading-relaxed">
        The platform is paper-only and has no live options chain feed.
        To populate diagnostics, run the operator shadow evaluator
        once chain snapshots exist:{' '}
        <code className="text-zinc-300">
          OPTIONS_SHADOW_EVAL_ENABLED=true python -m
          scripts.run_options_shadow_eval --date YYYY-MM-DD --commit
        </code>
        . No trades will be executed; only{' '}
        <code className="text-zinc-300">options_shadow_decision_log</code>{' '}
        receives writes.
      </div>
    </div>
  );
}
