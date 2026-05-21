// OptionsBiasChip — directional-bias label primitive.
//
// Used on every Opportunity / Position card. Renders the canonical
// AI-classified bias so the reader instantly knows whether a setup
// expects up / down / sideways / catalyst-driven price action.
//
// Bias taxonomy locked across the Copilot:
//   bullish      — expects price ↑
//   bearish      — expects price ↓
//   neutral      — expects range / time decay (income)
//   event        — pure event/catalyst play; direction may be either
//   developing   — setup is forming; not yet actionable
//   conviction   — high-confidence multi-signal alignment
//
// Display-only. No state. No mutation.

import { cn } from "@/lib/cn";

export type OptionsBias =
  | "bullish" | "bearish" | "neutral"
  | "event" | "developing" | "conviction";

const COPY: Record<OptionsBias, { label: string; aria: string }> = {
  bullish:    { label: "Bullish",    aria: "bullish bias" },
  bearish:    { label: "Bearish",    aria: "bearish bias" },
  neutral:    { label: "Neutral",    aria: "neutral / income bias" },
  event:      { label: "Event",      aria: "event-driven bias" },
  developing: { label: "Developing", aria: "developing setup" },
  conviction: { label: "Conviction", aria: "high-conviction signal" },
};

export default function OptionsBiasChip({
  bias, size = "sm", className,
}: {
  bias: OptionsBias;
  size?: "xs" | "sm" | "md";
  className?: string;
}) {
  const c = COPY[bias];
  return (
    <span
      className={cn(
        "opt-bias-chip",
        `opt-bias-${bias}`,
        `opt-bias-${size}`,
        className,
      )}
      aria-label={c.aria}
      data-test={`opt-bias-${bias}`}
    >
      <span className="opt-bias-dot" />
      {c.label}
    </span>
  );
}
