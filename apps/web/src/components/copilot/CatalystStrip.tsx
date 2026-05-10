// UX-13 cinematic — catalyst countdown strip.
//
// Compact horizontal strip of upcoming catalysts. Each shows
// "Earnings · 8d 14h" with live countdown via useTickEverySecond.
// Operational density without dashboard chrome.

import type { Catalyst } from "@/lib/copilot/living_compose";


export interface CatalystStripProps {
  catalysts: Catalyst[];
  onCatalystClick?: (ticker: string) => void;
}


function fmtCountdown(c: Catalyst): string {
  if (c.daysAway === 0 && (c.hoursAway ?? 0) < 24) {
    return c.hoursAway && c.hoursAway > 0 ? `${c.hoursAway}h` : "today";
  }
  if (c.daysAway < 7) return `${c.daysAway}d`;
  if (c.daysAway < 30) return `${c.daysAway}d`;
  return `${Math.round(c.daysAway / 7)}w`;
}


export default function CatalystStrip({ catalysts, onCatalystClick }: CatalystStripProps) {
  if (catalysts.length === 0) return null;

  return (
    <div className="ux13-catalysts" data-test="ux13-catalysts">
      <span className="ux13-catalysts-label">Catalysts</span>
      {catalysts.map((c, i) => (
        <button
          key={`${c.ticker}-${i}`}
          type="button"
          className="ux13-catalyst-pill"
          data-ticker={c.ticker}
          data-imminent={c.daysAway < 3 ? "true" : "false"}
          onClick={() => c.ticker !== "MARKET" && onCatalystClick?.(c.ticker)}
          aria-label={`${c.label}, ${c.ticker}, in ${fmtCountdown(c)}`}
        >
          <span className="ux13-catalyst-ticker">
            {c.ticker === "MARKET" ? "—" : c.ticker}
          </span>
          <span className="ux13-catalyst-label">{c.label}</span>
          <span className="ux13-catalyst-time">{fmtCountdown(c)}</span>
        </button>
      ))}
    </div>
  );
}
