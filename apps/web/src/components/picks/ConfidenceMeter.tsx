// ConfidenceMeter — small horizontal bar showing confidence 0-1.
// Color matches action tone (BUY green / SELL red / TRIM orange / HOLD amber).

import type { PickAction } from "@/lib/picks/api";


export interface ConfidenceMeterProps {
  fraction: number | null;
  action: PickAction;
  width?: number;
  height?: number;
}


function trackColor(action: PickAction): string {
  switch (action) {
    case "buy":  return "var(--picks-buy)";
    case "sell": return "var(--picks-sell)";
    case "trim": return "var(--picks-trim)";
    case "hold": return "var(--picks-hold)";
  }
}


export default function ConfidenceMeter({
  fraction, action,
  width = 60, height = 4,
}: ConfidenceMeterProps) {
  const pct = fraction == null ? 0 : Math.round(fraction * 100);
  const fillWidth = (fraction ?? 0) * width;

  return (
    <span
      className="confidence-meter"
      role="img"
      aria-label={`Confidence ${pct}%`}
      style={{
        display: "inline-block",
        width,
        height,
        background: "rgba(255,255,255,0.07)",
        borderRadius: 2,
        overflow: "hidden",
        verticalAlign: "middle",
      }}
    >
      <span
        style={{
          display: "block",
          width: fillWidth,
          height: "100%",
          background: trackColor(action),
          borderRadius: 2,
          transition: "width 280ms cubic-bezier(0.32, 0.72, 0, 1)",
        }}
      />
    </span>
  );
}
