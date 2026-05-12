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

import OptionsStatusBanner from "@/components/options/OptionsStatusBanner";
import OptionsTodayIdeasCard from "@/components/options/OptionsTodayIdeasCard";
import OptionsOpenTradesCard from "@/components/options/OptionsOpenTradesCard";
import OptionsClosedTradesCard from "@/components/options/OptionsClosedTradesCard";
import OptionsDiagnosticsCard from "@/components/options/OptionsDiagnosticsCard";
import OptionsExplanationPanel from "@/components/options/OptionsExplanationPanel";


export default function OptionsOverviewPage() {
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

      <OptionsStatusBanner />
      <OptionsTodayIdeasCard />
      <OptionsOpenTradesCard />
      <OptionsClosedTradesCard />
      <OptionsDiagnosticsCard />
      <OptionsExplanationPanel />
    </div>
  );
}
