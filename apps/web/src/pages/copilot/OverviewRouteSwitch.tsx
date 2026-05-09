// UX-5B Phase B-3 — /overview router switch.
//
// Default → CopilotOverview (Layer-1 editorial Today page).
// ?view=working → existing Overview (Elite Terminal preserved
// verbatim per Strategic lock D — never delete the current
// system).
//
// Pattern matches the Phase B PortfolioRouteSwitch
// (`apps/web/src/pages/copilot/PortfolioRouteSwitch.tsx`).

import { useLocation } from "react-router-dom";

import Overview from "@/pages/Overview";
import CopilotOverview from "@/pages/copilot/CopilotOverview";
// UX-9 Phase 9D — parallel Stream view at /overview?view=stream.
// Default and ?view=working are unchanged.
import CopilotStreamView from "@/pages/copilot/CopilotStreamView";
// UX-10 Phase 10D — parallel Conviction view at
// /overview?view=conviction. Default, ?view=working, and
// ?view=stream are all unchanged.
import CopilotConvictionView from "@/pages/copilot/CopilotConvictionView";


export default function OverviewRouteSwitch() {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  const view = params.get("view");
  if (view === "working") return <Overview />;
  if (view === "stream") return <CopilotStreamView />;
  if (view === "conviction") return <CopilotConvictionView />;
  return <CopilotOverview />;
}
