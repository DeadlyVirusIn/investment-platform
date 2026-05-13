// Phase Opt-A — Options page Brief view (default).
//
// Truth-first composition. Six cards in a single calm column:
//   1. Engine state banner (one truthful sentence)
//   2. Today's options ideas
//   3. Open paper options trades
//   4. Closed paper options trades
//   5. Diagnostics (key/value truth dump)
//   6. Explanation panel (only when engine dormant/unscheduled)
//
// The previous 12-tab layout is preserved verbatim behind
// `?view=working` (handled by OptionsLayout). Operator can still
// reach Chain, Features, Strategy Observatory, Decision Support,
// etc. via the URL query param.

import OptionsResearchPulseHero from "@/components/options/OptionsResearchPulseHero";
import OptionsStatusBanner from "@/components/options/OptionsStatusBanner";
import OptionsDiagnosticsAccordion from "@/components/options/OptionsDiagnosticsAccordion";
import OptionsExplanationPanel from "@/components/options/OptionsExplanationPanel";
import OptionsLearningGate from "@/components/options/OptionsLearningGate";
// Phase Opt-C1 Checkpoint 1 — Steps 1-2 (catalog + evaluation flow).
import OptionsStrategyCatalog from "@/components/options/OptionsStrategyCatalog";
import OptionsEvaluationFlow from "@/components/options/OptionsEvaluationFlow";
// Phase Opt-C1 Checkpoint 2 — Steps 5-7.
import OptionsResearchCandidates from "@/components/options/OptionsResearchCandidates";
import OptionsRejectionsSection from "@/components/options/OptionsRejectionsSection";
import OptionsRejectedCandidatesGroup from "@/components/options/OptionsRejectedCandidatesGroup";
// Phase Opt-C1 Checkpoint 3 — Steps 8-11.
// Grouped tracker REPLACES Opt-A's flat OpenTradesCard + ClosedTradesCard.
// Lifecycle timeline is rendered when the operator selects a trade
// (Checkpoint 4 will add a global selection store; for now timeline is
// available via direct URL hash deep-link, e.g. #lifecycle=1).
import OptionsTrackerWorkflow from "@/components/options/OptionsTrackerWorkflow";
import OptionsLifecycleTimeline from "@/components/options/OptionsLifecycleTimeline";


/** Read trade-id from URL hash (#lifecycle=N) for Checkpoint 3.
 *  Checkpoint 4 will swap this for a proper selection state. */
function _selectedTradeId(): number | null {
  if (typeof window === "undefined") return null;
  const m = window.location.hash.match(/lifecycle=(\d+)/);
  return m ? Number(m[1]) : null;
}


export default function OptionsOverviewPage() {
  const selectedTrade = _selectedTradeId();

  return (
    <div className="opt-brief">
      <header className="opt-brief-header">
        <h2 className="opt-brief-title">Options paper trading</h2>
        <p className="opt-brief-subtitle">
          Read-only research surface. Paper-only.{" "}
          Switch to{" "}
          <a href="/options?view=working" className="opt-brief-link">
            working view
          </a>{" "}
          for the dense terminal layout.
        </p>
      </header>

      {/* Phase 6b-3-a — Research Pulse Hero (premium hero surface).
          Renders ABOVE the legacy OptionsStatusBanner for visual A/B
          during the 6b-3 redesign rollout. Banner stays visible until
          6b-3-f composition pass removes it. */}
      <OptionsResearchPulseHero />

      <OptionsStatusBanner />

      {/* Phase Opt-C1 Step 5 — Today's Research Candidates (top 3) */}
      <OptionsResearchCandidates />

      {/* Phase Opt-C1 Step 6 — Filtered Out Today (rejection bar chart) */}
      <OptionsRejectionsSection />

      {/* Phase Opt-C1 Step 9-10 — Paper options journal (6 grouped sections) */}
      <OptionsTrackerWorkflow />

      {/* Phase Opt-C1 Step 7 — Rejected Candidates workflow group */}
      <OptionsRejectedCandidatesGroup />

      {/* Phase Opt-C1 Step 11 — Lifecycle timeline (deep-link only for now) */}
      {selectedTrade !== null && (
        <OptionsLifecycleTimeline trade_id={selectedTrade} />
      )}

      {/* Phase Opt-C1 Step 12 — Learning desk gate */}
      <OptionsLearningGate />

      {/* Phase Opt-C1 — educational layer (always visible, useful in dormant) */}
      <OptionsStrategyCatalog />
      <OptionsEvaluationFlow />

      {/* Phase Opt-C1 Step 14 — Diagnostics moved into accordion (?view=ops expands) */}
      <OptionsDiagnosticsAccordion />
      <OptionsExplanationPanel />
    </div>
  );
}
