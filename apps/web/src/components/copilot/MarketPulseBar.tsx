// UX-13 cinematic — market pulse bar.
//
// Thin 1px horizontal bar at very top of page. Color encodes
// current AI market state. Below it, a quiet inline label.
// Single passive signal — never a primary focal element.

import type { MarketPulse } from "@/lib/copilot/living_compose";


export interface MarketPulseBarProps {
  pulse: MarketPulse;
}


export default function MarketPulseBar({ pulse }: MarketPulseBarProps) {
  return (
    <div
      className="ux13-pulse-bar"
      data-state={pulse.state}
      data-test="ux13-pulse-bar"
      role="status"
      aria-label={`Market pulse: ${pulse.label}`}
    >
      <div className="ux13-pulse-line" aria-hidden="true" />
      <div className="ux13-pulse-label">{pulse.label}</div>
    </div>
  );
}
