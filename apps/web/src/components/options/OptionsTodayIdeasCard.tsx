// Phase Opt-A — Today's Options Ideas card.
//
// Renders shadow-flagged trade candidates from today's run. Currently
// the shadow evaluator runs manually only (last run 2026-05-03), so
// the empty state is the dominant render.
//
// Hard rule (per debate convergence): NO mock ideas. NO placeholder
// trades. NO synthetic confidence numbers. Empty state explains
// exactly when the next ideas would appear.

import { useOptionsPipelineStatus } from "@/lib/options/hooks";


function fmtDate(iso: string | null): string {
  if (!iso) return "never";
  return new Date(iso).toLocaleDateString();
}


export default function OptionsTodayIdeasCard() {
  const { data } = useOptionsPipelineStatus();

  // Real ideas list would come from a separate endpoint reading
  // today's options_shadow_decision_log rows where would_trade=true.
  // That endpoint doesn't exist yet — the shadow evaluator hasn't
  // run today, so the empty state is the only legitimate render.
  const lastRunDate = data?.options_shadow_decision_max_date ?? null;
  const totalRuns = data?.options_shadow_distinct_runs ?? 0;
  const enabled = data?.options_shadow_eval_enabled ?? false;

  return (
    <section className="u-card opt-card" data-test="options-today-ideas">
      <header className="opt-card-header">
        <span className="opt-card-eyebrow">Today's options ideas</span>
        <span className="opt-card-meta">
          {totalRuns === 0
            ? "no shadow runs ever"
            : `${totalRuns} historical run(s) · last ${fmtDate(lastRunDate)}`}
        </span>
      </header>

      <div className="opt-empty">
        <p className="opt-empty-headline">
          No options ideas today.
        </p>
        <p className="opt-empty-body">
          {enabled
            ? "Shadow evaluator is enabled but has not produced today's run yet. " +
              "Ideas appear here after the daily evaluator scores chain candidates."
            : "Shadow evaluator is OFF (OPTIONS_SHADOW_EVAL_ENABLED=false). " +
              "Ideas will appear here when the operator activates the evaluator " +
              "and a daily cron entry is added."}
        </p>
      </div>
    </section>
  );
}
