// OptionsConfidenceMeter — score → confidence band.
//
// Single source of confidence labeling across the Copilot. Score is
// the canonical `options_shadow_decision_log.score` (0..1 or 0..100
// depending on strategy; component normalizes via `scale` prop).
//
// Bands (locked):
//   >= 0.85  Very high
//   >= 0.70  High
//   >= 0.50  Medium
//   >= 0.30  Low
//   else     Below threshold

import { cn } from "@/lib/cn";

export interface OptionsConfidenceMeterProps {
  score: number | null;
  scale?: "unit" | "percent";      // 0..1 vs 0..100. Default unit.
  size?: "sm" | "md";
  showValue?: boolean;
  className?: string;
}

type Band = "very-high" | "high" | "medium" | "low" | "below" | "unknown";

function classify(score: number | null, scale: "unit" | "percent"): Band {
  if (score == null) return "unknown";
  const u = scale === "percent" ? score / 100 : score;
  if (u >= 0.85) return "very-high";
  if (u >= 0.70) return "high";
  if (u >= 0.50) return "medium";
  if (u >= 0.30) return "low";
  return "below";
}

const COPY: Record<Band, string> = {
  "very-high": "Very high",
  "high":      "High",
  "medium":    "Medium",
  "low":       "Low",
  "below":     "Below threshold",
  "unknown":   "Unscored",
};

export default function OptionsConfidenceMeter({
  score, scale = "unit", size = "sm",
  showValue = true, className,
}: OptionsConfidenceMeterProps) {
  const band = classify(score, scale);
  const u = score == null ? 0
    : scale === "percent" ? score / 100 : score;
  const widthPct = Math.max(0, Math.min(100, u * 100));
  return (
    <div
      className={cn("opt-conf-meter", `opt-conf-${band}`,
                    `opt-conf-${size}`, className)}
      data-test={`opt-conf-${band}`}
      aria-label={`Confidence ${COPY[band]}`}
    >
      <div className="opt-conf-row">
        <span className="opt-conf-label">Confidence</span>
        <span className="opt-conf-value">
          {COPY[band]}
          {showValue && score != null && (
            <span className="opt-conf-num">
              {" "}· {u.toFixed(2)}
            </span>
          )}
        </span>
      </div>
      <div className="opt-conf-bar">
        <div className="opt-conf-fill" style={{ width: `${widthPct}%` }} />
      </div>
    </div>
  );
}
