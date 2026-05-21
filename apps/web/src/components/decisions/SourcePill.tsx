// Phase L UI-1 — source pill for reasoning envelopes.
//
// Full words: Live / Replay / Backfill / Operator.
// Color-NEUTRAL by design — every source is a valid state; no
// hierarchy of trust is implied via color.
//
// Compact variant uses single-letter chip with a title tooltip
// containing the full word — only for dense table rows.

import type { ReasoningSource } from "@/lib/reasoning/types";


const FULL_LABEL: Record<ReasoningSource, string> = {
  live: "Live",
  replay: "Replay",
  backfill: "Backfill",
  operator_manual: "Operator",
};

const SHORT_LABEL: Record<ReasoningSource, string> = {
  live: "L",
  replay: "R",
  backfill: "B",
  operator_manual: "O",
};


export interface SourcePillProps {
  source: ReasoningSource;
  /** "full" (default) = "Live" / "Replay" / etc.
   *  "compact" = single-letter chip with tooltip. */
  variant?: "full" | "compact";
  className?: string;
}


export default function SourcePill({
  source, variant = "full", className,
}: SourcePillProps) {
  const fullText = FULL_LABEL[source];
  const isCompact = variant === "compact";
  const label = isCompact ? SHORT_LABEL[source] : fullText;
  const classes = [
    "u-chip",
    "u-chip-neutral",
    isCompact ? "u-chip-compact" : null,
    className ?? null,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <span
      className={classes}
      title={isCompact ? fullText : undefined}
      data-source={source}
      data-test="source-pill"
    >
      {label}
    </span>
  );
}
