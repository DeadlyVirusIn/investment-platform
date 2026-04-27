// Phase UI-TERMINAL-LAYERS — Layer 4: inline sparkline for key tickers.
// Thin SVG, ~52x16, no deps.

import { cn } from "@/lib/cn";

export default function Sparkline({
  points, tone, width = 52, height = 16,
}: {
  points: number[];
  tone: "pos" | "neg";
  width?: number; height?: number;
}) {
  if (!points || points.length < 2) return null;

  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const stepX = width / (points.length - 1);

  const coords = points.map((v, i) => {
    const x = i * stepX;
    const y = height - ((v - min) / range) * (height - 2) - 1;
    return [x, y] as const;
  });

  const linePath = coords.map(([x, y], i) =>
    `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${width},${height} L0,${height} Z`;

  const toneCls = tone === "pos" ? "is-pos" : "is-neg";

  return (
    <svg className="u-spark-inline" viewBox={`0 0 ${width} ${height}`}
         preserveAspectRatio="none">
      <path d={areaPath} className={cn("u-spark-area", toneCls)} />
      <path d={linePath} className={cn("u-spark-line", toneCls)} />
    </svg>
  );
}
