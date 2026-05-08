// UX-2 Phase B — /portfolio router switch.
//
// ?view=brief   → CopilotHoldings (new storytelling view)
// ?view=working → PortfolioTerminal (existing dense view, unchanged)
// no ?view      → PortfolioTerminal (preserves existing default).
//                 Phase F is when the default flips to brief.
//
// Reads URL on every render via React Router's useLocation so the
// page swaps when the user clicks the brief↔working link.

import { useLocation } from "react-router-dom";

import PortfolioTerminal from "@/pages/PortfolioTerminal";
import CopilotHoldings from "@/pages/copilot/CopilotHoldings";


export default function PortfolioRouteSwitch() {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  const view = params.get("view");
  if (view === "brief") return <CopilotHoldings />;
  return <PortfolioTerminal />;
}
