// Phase Opt-C1 Step 6 — Filtered Out Today (rejection-reason UX).
//
// First-class trust feature. Shows operator the system is actually
// evaluating, not blindly suggesting whatever.
//
// Surfaces:
//   - Active mode: bar chart of top 7 rejection reasons from today's
//     shadow decisions, with novice-friendly fail labels
//   - Dormant mode: 7 quality checks preview + "what appears when live"
//   - Always: the 7 quality checks listed by name

import {
  FILTER_LABELS,
  aggregateRejectionReasons,
  daysSince,
  isRunFromToday,
  useShadowRunDetail,
  useShadowRunsList,
} from "@/lib/options/researchCandidates";


const QUALITY_CHECKS: Array<{ name: keyof typeof FILTER_LABELS; label: string }> = [
  { name: "liquidity",     label: FILTER_LABELS.liquidity },
  { name: "spread",        label: FILTER_LABELS.spread },
  { name: "open_interest", label: FILTER_LABELS.open_interest },
  { name: "volume",        label: FILTER_LABELS.volume },
  { name: "greeks",        label: FILTER_LABELS.greeks },
  { name: "iv_rank",       label: FILTER_LABELS.iv_rank },
  { name: "risk",          label: FILTER_LABELS.risk },
];


export default function OptionsRejectionsSection() {
  const runsQ = useShadowRunsList();
  const latestDate = runsQ.data?.runs?.[0]?.run_date ?? null;
  const detailQ = useShadowRunDetail(latestDate);
  const decisions = detailQ.data?.decisions ?? [];
  const todayHasRun = isRunFromToday(latestDate);
  const lastAge = daysSince(latestDate);

  const reasons = aggregateRejectionReasons(decisions);
  const totalFiltered = decisions.filter(d => !d.would_trade).length;
  const maxCount = reasons[0]?.count ?? 0;

  return (
    <section className="u-card opt-card" data-test="options-rejections">
      <header className="opt-card-header">
        <span className="opt-card-eyebrow">Filtered out today</span>
        <span className="opt-card-meta">
          {todayHasRun
            ? `${totalFiltered} setup${totalFiltered === 1 ? "" : "s"} failed checks`
            : "preview"}
        </span>
      </header>

      {/* Active state — bar chart of top reasons */}
      {todayHasRun && reasons.length > 0 && (
        <>
          <p className="opt-explain-body" style={{ marginBottom: 8 }}>
            The system evaluates every candidate against 7 thresholds
            before promotion. Top reasons setups were filtered out:
          </p>
          <div className="opt-rejection-bars">
            {reasons.map((r) => {
              const pct = maxCount > 0 ? (r.count / maxCount) * 100 : 0;
              return (
                <div key={r.name} className="opt-rejection-row">
                  <span className="opt-rejection-label">{r.failLabel}</span>
                  <div className="opt-rejection-bar-track">
                    <div
                      className="opt-rejection-bar-fill"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="opt-rejection-count">{r.count}</span>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Active state but no rejections today */}
      {todayHasRun && reasons.length === 0 && (
        <div className="opt-empty">
          <p className="opt-empty-body">
            No setups were rejected today. Either no candidates were
            evaluated, or all evaluated candidates passed every check.
          </p>
        </div>
      )}

      {/* Dormant or no-run-today: show the 7 quality checks preview */}
      {!todayHasRun && (
        <>
          <p className="opt-explain-body" style={{ marginBottom: 8 }}>
            {latestDate
              ? `Last shadow evaluation ran ${lastAge}d ago. `
              : "No shadow evaluations on record yet. "}
            When live, this section ranks today's top rejection reasons.
            The system runs 7 quality checks against every candidate:
          </p>
          <ul className="opt-quality-checks-list">
            {QUALITY_CHECKS.map((c) => (
              <li key={c.name} className="opt-quality-check">
                {c.label}
              </li>
            ))}
            <li className="opt-quality-check is-extra">
              + earnings-window guard (skipped near earnings)
            </li>
          </ul>
        </>
      )}
    </section>
  );
}
