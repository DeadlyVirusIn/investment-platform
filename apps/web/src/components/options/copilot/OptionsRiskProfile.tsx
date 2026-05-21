// OptionsRiskProfile — tiny risk-graph primitive.
//
// Surfaces the four numbers every options-position reader needs:
//   max loss, max gain, breakeven(s), profit zone (lower→upper).
// SVG payoff sketch is intentionally schematic — not a price-path
// simulator. Reader gets a 1-second risk picture.
//
// All values are computed server-side; this component does no math.
// Pass `null` to omit any field. Honest empty state when all null.

import { cn } from "@/lib/cn";
import { fmtUSD, fmtSignedUSD } from "@/components/ui/primitives";

export interface OptionsRiskProfileData {
  maxLoss: number | null;            // negative or zero
  maxGain: number | null;            // positive, or null = unbounded
  breakeven: number | null;
  breakevenUpper?: number | null;    // for spreads with two BEs
  profitZoneLower?: number | null;
  profitZoneUpper?: number | null;
  spotPrice?: number | null;         // for visual anchoring
}

export default function OptionsRiskProfile({
  data, compact = false, className,
}: {
  data: OptionsRiskProfileData;
  compact?: boolean;
  className?: string;
}) {
  const allNull =
    data.maxLoss == null && data.maxGain == null
    && data.breakeven == null && data.profitZoneLower == null;

  if (allNull) {
    return (
      <div className={cn("opt-risk-profile opt-risk-empty", className)}>
        <span className="opt-caption-muted">Risk profile not available</span>
      </div>
    );
  }

  return (
    <div
      className={cn("opt-risk-profile",
        compact && "opt-risk-compact", className)}
      data-test="opt-risk-profile"
    >
      <div className="opt-risk-numbers">
        {data.maxLoss != null && (
          <div className="opt-risk-num opt-risk-loss">
            <span className="opt-risk-label">Max loss</span>
            <span className="opt-risk-value">
              {fmtSignedUSD(data.maxLoss)}
            </span>
          </div>
        )}
        {data.maxGain != null ? (
          <div className="opt-risk-num opt-risk-gain">
            <span className="opt-risk-label">Max gain</span>
            <span className="opt-risk-value">
              {fmtSignedUSD(data.maxGain)}
            </span>
          </div>
        ) : data.maxGain === null ? null : (
          <div className="opt-risk-num opt-risk-gain">
            <span className="opt-risk-label">Max gain</span>
            <span className="opt-risk-value">Uncapped</span>
          </div>
        )}
        {data.breakeven != null && (
          <div className="opt-risk-num opt-risk-be">
            <span className="opt-risk-label">Breakeven</span>
            <span className="opt-risk-value">
              {fmtUSD(data.breakeven, 2)}
              {data.breakevenUpper != null
                ? ` / ${fmtUSD(data.breakevenUpper, 2)}`
                : ""}
            </span>
          </div>
        )}
      </div>
      {(data.profitZoneLower != null || data.profitZoneUpper != null) && (
        <div className="opt-risk-zone">
          <span className="opt-risk-zone-label">Profit zone</span>
          <span className="opt-risk-zone-value">
            {data.profitZoneLower != null ? fmtUSD(data.profitZoneLower, 2) : "—"}
            {" → "}
            {data.profitZoneUpper != null ? fmtUSD(data.profitZoneUpper, 2) : "—"}
            {data.spotPrice != null && (
              <span className="opt-risk-zone-spot">
                {" "}· spot {fmtUSD(data.spotPrice, 2)}
              </span>
            )}
          </span>
        </div>
      )}
    </div>
  );
}
