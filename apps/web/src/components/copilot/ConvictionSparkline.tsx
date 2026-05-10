// UX-13 cinematic — inline conviction trajectory sparkline.
//
// Static SVG (no animation). Shows conviction direction at scan
// speed. Width 56-72px. Stroke matches pressure tone (warm amber
// strengthening / cool slate weakening / muted neutral stable).
//
// Replaces the static "●●●●" tier dot row with actual movement.

import type {
  ConvictionSeries, PressureDirection,
} from "@/lib/copilot/living_compose";


export interface ConvictionSparklineProps {
  series: ConvictionSeries;
  pressure: PressureDirection;
  width?: number;
  height?: number;
}


function toneColor(p: PressureDirection): string {
  switch (p) {
    case "strengthening": return "var(--living-tone-up)";
    case "weakening":     return "var(--living-tone-down)";
    case "stable":        return "var(--living-ink-meta)";
  }
}


export default function ConvictionSparkline({
  series,
  pressure,
  width = 64,
  height = 16,
}: ConvictionSparklineProps) {
  if (series.length < 2) return null;

  const min = Math.min(...series);
  const max = Math.max(...series);
  const range = Math.max(max - min, 0.01);   // avoid /0
  const stepX = width / (series.length - 1);

  const points = series.map((v, i) => {
    const x = i * stepX;
    const y = height - ((v - min) / range) * (height - 2) - 1;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  const stroke = toneColor(pressure);
  const lastX = (series.length - 1) * stepX;
  const lastY = height - ((series[series.length - 1] - min) / range) * (height - 2) - 1;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Conviction trajectory ${pressure}, ${series.length} points`}
      style={{ display: "inline-block", verticalAlign: "middle" }}
    >
      <polyline
        points={points}
        fill="none"
        stroke={stroke}
        strokeWidth="1.25"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={lastX} cy={lastY} r="1.75" fill={stroke} />
    </svg>
  );
}
