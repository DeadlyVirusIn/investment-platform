// Phase UX-PHASE2 HI-2 — minimal SVG sparkline.
// No external chart lib. Subtle, non-decorative. Renders nothing
// gracefully when data is empty/insufficient.

import { useMemo } from "react";


export interface SparklineProps {
  values: ReadonlyArray<number | null | undefined>;
  width?: number;
  height?: number;
  // Color follows last-vs-first sign by default (success/danger/neutral)
  // unless explicitly overridden via `tone`.
  tone?: "auto" | "pos" | "neg" | "neutral";
  className?: string;
  ariaLabel?: string;
}


export default function Sparkline({
  values,
  width = 80,
  height = 22,
  tone = "auto",
  className,
  ariaLabel,
}: SparklineProps) {
  const points = useMemo(() => {
    const xs = (values ?? [])
      .map(v => (v === null || v === undefined ? null : Number(v)))
      .map(v => (v != null && Number.isFinite(v) ? v : null));
    return xs;
  }, [values]);

  const cleaned = points.filter((v): v is number => v != null);
  if (cleaned.length < 2) {
    return null;
  }

  const min = Math.min(...cleaned);
  const max = Math.max(...cleaned);
  const span = max - min || 1;
  const dx = points.length > 1 ? width / (points.length - 1) : 0;

  // Path: connect non-null only; use last seen y for null gaps so the
  // line stays visually continuous without inventing values.
  let prevY: number | null = null;
  const cmds: string[] = [];
  let firstSeen = false;
  points.forEach((v, i) => {
    if (v == null) {
      if (prevY != null) {
        cmds.push(`L${(i * dx).toFixed(2)},${prevY.toFixed(2)}`);
      }
      return;
    }
    const y = height - ((v - min) / span) * height;
    if (!firstSeen) {
      cmds.push(`M${(i * dx).toFixed(2)},${y.toFixed(2)}`);
      firstSeen = true;
    } else {
      cmds.push(`L${(i * dx).toFixed(2)},${y.toFixed(2)}`);
    }
    prevY = y;
  });
  const d = cmds.join(" ");

  // Tone resolution
  const first = cleaned[0];
  const last = cleaned[cleaned.length - 1];
  const resolvedTone = tone === "auto"
    ? (last > first ? "pos" : last < first ? "neg" : "neutral")
    : tone;
  // Phase 4 — drive tones via theme tokens so light mode adapts.
  const stroke = resolvedTone === "pos" ? "var(--chart-positive)"
    : resolvedTone === "neg" ? "var(--chart-negative)"
    : "var(--chart-muted)";
  const fill = resolvedTone === "pos" ? "var(--success-soft)"
    : resolvedTone === "neg" ? "var(--danger-soft)"
    : "var(--neutral-soft)";

  // Area fill path: same line + close to bottom-right + bottom-left
  const lastIdx = points.length - 1;
  const areaD = `${d} L${(lastIdx * dx).toFixed(2)},${height} `
              + `L0,${height} Z`;

  return (
    <svg
      width={width} height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      role="img"
      aria-label={ariaLabel ?? "trend"}
      preserveAspectRatio="none"
      style={{ display: "inline-block", verticalAlign: "middle" }}
    >
      <path d={areaD} fill={fill} />
      <path d={d} stroke={stroke} strokeWidth={1.25}
            fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
