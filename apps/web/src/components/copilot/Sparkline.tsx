// UX-9 Phase 9B — minimal sparkline.
//
// Pure SVG path. NO axes. NO labels. NO interaction. Renders a
// single polyline through the data points, normalized to the
// SVG viewBox. CSS handles the line-draw entrance animation
// (200ms left-to-right reveal at 1100ms, after the grid lands).

interface SparklineProps {
  /** 4-32 data points. Visualised as a continuous line. */
  points: number[];
  className?: string;
  width?: number;
  height?: number;
}


export default function Sparkline(
  { points, className, width = 120, height = 32 }: SparklineProps,
) {
  if (!points || points.length < 2) return null;

  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const stepX = width / (points.length - 1);

  const d = points
    .map((y, i) => {
      const x = i * stepX;
      // invert Y so larger values render higher
      const normY = ((y - min) / range);
      const cy = height - normY * (height - 4) - 2;
      return `${i === 0 ? "M" : "L"} ${x.toFixed(2)} ${cy.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg
      className={`ux9-sparkline ${className ?? ""}`.trim()}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      role="presentation"
      aria-hidden="true"
    >
      <path className="ux9-sparkline-path" d={d} />
    </svg>
  );
}
