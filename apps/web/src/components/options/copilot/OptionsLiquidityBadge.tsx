// OptionsLiquidityBadge — liquidity-quality dot + tooltip.
//
// Reads three signals from a single chain row (already computed by
// shadow_evaluator's gate-pass logic):
//   * bid > 0 and ask > bid
//   * spread <= configured threshold
//   * open_interest >= threshold
//
// Renders one of: good / fair / poor / unknown. Hover shows the
// underlying numbers. No math here — caller passes the booleans.

import { cn } from "@/lib/cn";

export type LiquidityTier = "good" | "fair" | "poor" | "unknown";

export interface OptionsLiquidityBadgeProps {
  tier: LiquidityTier;
  bid?: number | null;
  ask?: number | null;
  spread?: number | null;
  openInterest?: number | null;
  volume?: number | null;
  className?: string;
}

const COPY: Record<LiquidityTier, string> = {
  good:    "Good liquidity",
  fair:    "Fair liquidity",
  poor:    "Poor liquidity — wide spread or low OI",
  unknown: "Liquidity unknown",
};

export default function OptionsLiquidityBadge({
  tier, bid, ask, spread, openInterest, volume, className,
}: OptionsLiquidityBadgeProps) {
  const parts: string[] = [];
  if (bid != null && ask != null) parts.push(`bid ${bid.toFixed(2)} / ask ${ask.toFixed(2)}`);
  if (spread != null) parts.push(`spread $${spread.toFixed(2)}`);
  if (openInterest != null) parts.push(`OI ${openInterest.toLocaleString()}`);
  if (volume != null) parts.push(`vol ${volume.toLocaleString()}`);
  const tooltip = `${COPY[tier]}${parts.length ? ` · ${parts.join(" · ")}` : ""}`;
  return (
    <span
      className={cn("opt-liq-badge", `opt-liq-${tier}`, className)}
      title={tooltip}
      aria-label={tooltip}
      data-test={`opt-liq-${tier}`}
    >
      <span className="opt-liq-dot" />
      {COPY[tier]}
    </span>
  );
}
