// EquitySparkline — minimal SVG line chart for the portfolio hero.
// Honest: shows nothing when no points; never fakes a curve.

import type { EquityPoint } from "@/lib/portfolio/api";


export interface EquitySparklineProps {
  points: EquityPoint[];
  height?: number;
  showAxis?: boolean;
  /**
   * PR-2 visual consistency: "neutral" makes the stroke + fill follow
   * the surrounding ink (currentColor) instead of green/red. Used by
   * the /today calm shell where emerald/red would clash with the
   * warm-paper palette. Legacy callers omit the prop and keep the
   * existing green-up / red-down behavior byte-for-byte.
   */
  theme?: "auto" | "neutral";
}


export default function EquitySparkline({
  points, height = 56, showAxis = false, theme = "auto",
}: EquitySparklineProps) {
  if (points.length < 2) {
    return <div className="ps-spark-empty">Not enough history yet</div>;
  }

  const w = 360;
  const h = height;
  const ys = points.map(p => p.equity);
  const min = Math.min(...ys);
  const max = Math.max(...ys);
  const range = max - min || 1;
  const dx = w / (points.length - 1);

  const coords = points.map((p, i) => {
    const x = i * dx;
    const y = h - ((p.equity - min) / range) * h;
    return [x, y] as const;
  });

  const path = coords
    .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`)
    .join(" ");
  const areaPath = `${path} L${w} ${h} L0 ${h} Z`;

  const lastY = coords[coords.length - 1][1];
  const firstEquity = ys[0];
  const lastEquity = ys[ys.length - 1];
  const trending = lastEquity >= firstEquity;
  const stroke = theme === "neutral"
    ? "currentColor"
    : trending ? "var(--pi-good)" : "var(--pi-bad)";
  const fill = theme === "neutral"
    ? "rgba(46, 80, 67, 0.08)"
    : trending ? "rgba(52, 211, 153, 0.16)" : "rgba(248, 113, 113, 0.16)";

  return (
    <svg className="ps-spark" viewBox={`0 0 ${w} ${h}`} width="100%" height={h} preserveAspectRatio="none">
      <defs>
        <linearGradient id="ps-spark-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={fill} stopOpacity="1" />
          <stop offset="100%" stopColor={fill} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill="url(#ps-spark-grad)" />
      <path d={path} stroke={stroke} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={w} cy={lastY} r="2.5" fill={stroke} />
      {showAxis && (
        <text x={w - 4} y={lastY - 6} fontSize="10" fill="var(--pi-ink-muted)" textAnchor="end">
          ${lastEquity.toLocaleString(undefined, { maximumFractionDigits: 0 })}
        </text>
      )}
    </svg>
  );
}
