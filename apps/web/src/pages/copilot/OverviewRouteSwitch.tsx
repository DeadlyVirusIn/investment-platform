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


export default function OverviewRouteSwitch() {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  const view = params.get("view");
  if (view === "working") return <Overview />;
  return <CopilotOverview />;
}
