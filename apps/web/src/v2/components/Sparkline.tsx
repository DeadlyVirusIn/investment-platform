// V2 Sparkline — pure SVG, no chart library. Inherits currentColor
// so theme switches automatically. Used by LearnHome book teaser and
// by Pick Detail / Watchlist later.

interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  strokeWidth?: number;
  className?: string;
  filled?: boolean;
}

export function Sparkline({
  values,
  width = 60,
  height = 18,
  strokeWidth = 1.25,
  className,
  filled = false,
}: SparklineProps) {
  if (!values || values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * width;
    const y =
      height - ((v - min) / range) * (height - strokeWidth) - strokeWidth / 2;
    return { x, y };
  });
  const line = pts.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' ');
  const area = [
    `${pts[0].x},${height}`,
    ...pts.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`),
    `${pts[pts.length - 1].x},${height}`,
  ].join(' ');
  return (
    <svg
      width={width}
      height={height}
      className={`overflow-visible ${className ?? ''}`}
      aria-hidden
    >
      {filled && <polygon points={area} fill="currentColor" opacity={0.08} />}
      <polyline
        points={line}
        fill="none"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={0.7}
      />
    </svg>
  );
}

// Deterministic sparkline data based on a seed string so each symbol
// gets a consistent shape across renders.
export function sparkFromSymbol(symbol: string, points = 24): number[] {
  let h = 0;
  for (let i = 0; i < symbol.length; i++)
    h = (h * 31 + symbol.charCodeAt(i)) >>> 0;
  const rand = () => {
    h = (h * 1103515245 + 12345) >>> 0;
    return h / 0xffffffff;
  };
  const out: number[] = [];
  let v = 50;
  for (let i = 0; i < points; i++) {
    v += (rand() - 0.5) * 5;
    out.push(v);
  }
  return out;
}
