// UX-2 Phase B (initial) — /portfolio router switch.
// Phase 15b2 — Default flipped from working -> brief; visible toggle.
//
// Routes:
//   /portfolio              -> CopilotHoldings (Brief view, default since 15b2)
//   /portfolio?view=brief   -> CopilotHoldings (explicit)
//   /portfolio?view=working -> PortfolioTerminal (legacy dense view, preserved)
//
// Why the flip: docs/ux/PHASE_15_elite_audit.md §3 — 4-of-4 panelist
// unanimous finding. CopilotHoldings is the most premium AI-narrative
// surface in the product but was URL-only discoverable. The Phase F
// default flip was planned in earlier code comments but never shipped.
// Working view is preserved verbatim and reachable via the visible
// toggle (no functionality removed).

import { Link, useLocation } from "react-router-dom";

import PortfolioTerminal from "@/pages/PortfolioTerminal";
import CopilotHoldings from "@/pages/copilot/CopilotHoldings";
// Phase 15b3 — route-level NextStepCard so brief and working views
// both inherit the FLOW chain's next-step nudge (audit P1.14).
import NextStepCard from "@/components/shell/NextStepCard";


export default function PortfolioRouteSwitch() {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  const view = params.get("view");
  const isWorking = view === "working";

  return (
    <div className="portfolio-shell">
      <PortfolioViewToggle isWorking={isWorking} />
      {isWorking ? <PortfolioTerminal /> : <CopilotHoldings />}
      {/* Phase 15b3 — route-level NextStepCard. Sits below either view
          so the page_flow chain (Portfolio -> Risk) terminates with a
          consistent next-step affordance whichever lens the user is in. */}
      <div className="portfolio-shell-footer">
        <NextStepCard pathname="/portfolio" />
      </div>
    </div>
  );
}


// Two-segment pill — Brief | Working. Same primitive shape as
// DensityToggle so the affordance reads as consistent. Renders above
// every Portfolio view so the user always knows which lens they're
// in and how to switch.
function PortfolioViewToggle({ isWorking }: { isWorking: boolean }) {
  return (
    <div className="portfolio-view-toggle" role="group"
         aria-label="Portfolio view">
      <Link
        to="/portfolio"
        className="portfolio-view-toggle-btn"
        data-active={!isWorking ? "true" : "false"}
        aria-current={!isWorking ? "page" : undefined}
      >
        Brief
      </Link>
      <Link
        to="/portfolio?view=working"
        className="portfolio-view-toggle-btn"
        data-active={isWorking ? "true" : "false"}
        aria-current={isWorking ? "page" : undefined}
      >
        Working
      </Link>
    </div>
  );
}
