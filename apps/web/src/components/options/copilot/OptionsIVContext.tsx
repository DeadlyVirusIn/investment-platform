// OptionsIVContext — IV-rank + premium-environment chip.
//
// Reads iv_rank_252d, atm_iv, iv_percentile_252d from
// /api/options/features. When iv_rank is NULL (history-fn gap) the
// chip degrades honestly to "IV rank unavailable" rather than
// fabricating a value.
//
// Premium environment classification (heuristic, locked):
//   iv_rank >= 75  → "Rich" (sellers favored)
//   iv_rank >= 50  → "Elevated"
//   iv_rank >= 25  → "Average"
//   iv_rank <  25  → "Cheap" (buyers favored)

import { cn } from "@/lib/cn";

export interface OptionsIVContextProps {
  ivRank: number | null;           // 0..100
  atmIv?: number | null;           // 0..1+ raw annualized
  ivPercentile?: number | null;
  className?: string;
}

type Tier = "rich" | "elevated" | "average" | "cheap" | "unknown";

function classifyIvRank(r: number | null): Tier {
  if (r == null) return "unknown";
  if (r >= 75) return "rich";
  if (r >= 50) return "elevated";
  if (r >= 25) return "average";
  return "cheap";
}

const COPY: Record<Tier, { label: string; sub: string }> = {
  rich:     { label: "Rich",     sub: "Sellers favored — premium elevated" },
  elevated: { label: "Elevated", sub: "Premium above average" },
  average:  { label: "Average",  sub: "Premium in mid-range" },
  cheap:    { label: "Cheap",    sub: "Buyers favored — premium depressed" },
  unknown:  { label: "IV unknown", sub: "Feature engine pending data" },
};

export default function OptionsIVContext({
  ivRank, atmIv, ivPercentile, className,
}: OptionsIVContextProps) {
  const tier = classifyIvRank(ivRank);
  const c = COPY[tier];
  return (
    <div
      className={cn("opt-iv-context", `opt-iv-${tier}`, className)}
      data-test={`opt-iv-${tier}`}
    >
      <div className="opt-iv-row">
        <span className="opt-iv-label">Premium</span>
        <span className="opt-iv-value">{c.label}</span>
        {ivRank != null && (
          <span className="opt-iv-rank">
            IV rank {ivRank.toFixed(0)}
          </span>
        )}
      </div>
      <div className="opt-iv-sub">
        {c.sub}
        {atmIv != null && (
          <span className="opt-iv-atm">
            {" "}· ATM IV {(atmIv * 100).toFixed(1)}%
          </span>
        )}
        {ivPercentile != null && (
          <span className="opt-iv-pct">
            {" "}· {ivPercentile.toFixed(0)} pctile
          </span>
        )}
      </div>
    </div>
  );
}
