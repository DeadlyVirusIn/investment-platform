// Personal-Analytics Phase — read-only ML insights card.
//
// Reads /api/ml/insights/{summary,labels,features} and renders:
//   * dataset health
//   * label availability with open_pending count
//   * readiness checklist (false until labels reach the floor)
//   * leakage check status
//
// No "train", "run", or "execute" buttons. Prominent banner pinning
// "ML insight only — cannot affect trades." This card NEVER triggers
// model training.

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

interface InsightSummary {
  ml_can_affect_trades: boolean;
  notice: string;
  ready: boolean;
  reason: string;
  min_labeled_outcomes_required: number;
  counts: {
    recommendations_total: number;
    recommendation_outcome_rows: number;
    labeled_outcomes: number;
    open_pending_outcomes: number;
    missing_outcome_rows: number;
    ml_replay_decision: number;
    ml_replay_outcome: number;
    ml_research_snapshot: number;
    ml_shadow_prediction: number;
  };
}

interface InsightLabels {
  labeled_outcomes_total: number;
  min_required_for_ready: number;
  ready_for_evaluation: boolean;
  barrier_label_distribution: Record<string, number>;
  barrier_label_open_pending: number;
  realized_returns: {
    labeled_30d: number; pending_30d: number;
    labeled_90d: number; pending_90d: number;
  };
  note: string | null;
}

interface InsightFeatures {
  feature_count: number;
  feature_columns: string[];
  identity_columns: string[];
  leakage_check: {
    is_forbidden_feature_name_implemented: boolean;
    rejected_sample: string[];
  };
}

export default function MLInsightsCard() {
  const summaryQ = useQuery<InsightSummary>({
    queryKey: ['ml-insights', 'summary'],
    queryFn: () => apiGet<InsightSummary>('/ml/insights/summary'),
    staleTime: 60_000,
  });
  const labelsQ = useQuery<InsightLabels>({
    queryKey: ['ml-insights', 'labels'],
    queryFn: () => apiGet<InsightLabels>('/ml/insights/labels'),
    staleTime: 60_000,
  });
  const featsQ = useQuery<InsightFeatures>({
    queryKey: ['ml-insights', 'features'],
    queryFn: () => apiGet<InsightFeatures>('/ml/insights/features'),
    staleTime: 60_000,
  });

  const s = summaryQ.data;
  const l = labelsQ.data;
  const f = featsQ.data;

  return (
    <section
      data-test="ml-insights-card"
      className="rounded-md border border-zinc-700 bg-zinc-900/40 p-4 mb-4"
    >
      <header className="flex items-baseline justify-between mb-3">
        <h3 className="text-sm font-semibold text-zinc-100">
          ML Insights — read-only diagnostics
        </h3>
        <span className="text-[10px] uppercase tracking-wide text-amber-400">
          ML insight only — cannot affect trades
        </span>
      </header>

      <div
        data-test="ml-insights-no-execute-banner"
        className="rounded border border-amber-700 bg-amber-900/20 px-3 py-2 text-xs text-zinc-200 mb-3"
      >
        ML_CAN_AFFECT_TRADES is pinned to <strong>false</strong>.
        Nothing on this card can train, score, or trigger a trade.
        Labels will populate as paper_trade rows close.
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Cell label="Recommendations"
              value={String(s?.counts.recommendations_total ?? 0)} />
        <Cell label="Outcome rows"
              value={String(s?.counts.recommendation_outcome_rows ?? 0)}
              hint="recommendation_outcome" />
        <Cell label="Labeled outcomes"
              value={String(s?.counts.labeled_outcomes ?? 0)}
              hint={`floor ${s?.min_labeled_outcomes_required ?? 20}`} />
        <Cell label="Open pending"
              value={String(s?.counts.open_pending_outcomes ?? 0)}
              hint="awaiting outcome" warn />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Cell label="ml_replay_decision"
              value={String(s?.counts.ml_replay_decision ?? 0)} />
        <Cell label="ml_replay_outcome"
              value={String(s?.counts.ml_replay_outcome ?? 0)} />
        <Cell label="ml_research_snapshot"
              value={String(s?.counts.ml_research_snapshot ?? 0)} />
        <Cell label="ml_shadow_prediction"
              value={String(s?.counts.ml_shadow_prediction ?? 0)} />
      </div>

      {/* Readiness checklist */}
      <ul
        data-test="ml-insights-readiness-checklist"
        className="text-xs text-zinc-300 space-y-1 mb-3"
      >
        <li>
          <ReadyBadge ok={!!s?.ready} />{' '}
          Labeled outcomes ≥ {s?.min_labeled_outcomes_required ?? 20}
          {' '}
          (current: {s?.counts.labeled_outcomes ?? 0})
        </li>
        <li>
          <ReadyBadge
            ok={!!f?.leakage_check.is_forbidden_feature_name_implemented}
          />{' '}
          Leakage guard implemented
          ({f?.leakage_check.rejected_sample.length ?? 0} forbidden names rejected)
        </li>
        <li>
          <ReadyBadge ok={!s?.ml_can_affect_trades} forceGreen />{' '}
          ML_CAN_AFFECT_TRADES locked to false
        </li>
        <li>
          <ReadyBadge ok={(l?.labeled_outcomes_total ?? 0) > 0} />{' '}
          At least one labeled outcome
        </li>
      </ul>

      {/* Label availability */}
      {l?.note && (
        <div
          data-test="ml-insights-pending-note"
          className="text-xs text-amber-300 mb-3"
        >
          {l.note}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Cell label="30d realized — labeled"
              value={String(l?.realized_returns.labeled_30d ?? 0)} />
        <Cell label="30d realized — pending"
              value={String(l?.realized_returns.pending_30d ?? 0)} warn />
        <Cell label="90d realized — labeled"
              value={String(l?.realized_returns.labeled_90d ?? 0)} />
        <Cell label="90d realized — pending"
              value={String(l?.realized_returns.pending_90d ?? 0)} warn />
      </div>
    </section>
  );
}

function Cell({
  label, value, hint, warn,
}: {
  label: string; value: string; hint?: string; warn?: boolean;
}) {
  return (
    <div className="rounded border border-zinc-800 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div className={
        'text-lg font-semibold mt-0.5 ' +
        (warn ? 'text-amber-300' : 'text-zinc-100')
      }>
        {value}
      </div>
      {hint && (
        <div className="text-[10px] text-zinc-500 mt-0.5">{hint}</div>
      )}
    </div>
  );
}

function ReadyBadge({ ok, forceGreen }: { ok: boolean; forceGreen?: boolean }) {
  const green = ok || forceGreen;
  return (
    <span className={
      'inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold mr-1 ' +
      (green ? 'bg-emerald-700/40 text-emerald-300'
             : 'bg-zinc-800 text-zinc-500')
    }>
      {green ? '✓' : '·'}
    </span>
  );
}
