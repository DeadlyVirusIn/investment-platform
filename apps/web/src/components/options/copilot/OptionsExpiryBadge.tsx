// OptionsExpiryBadge — DTE + expiry date + earnings-overlap flag.
//
// Tiny chip used on every Opportunity / Position card. Surfaces:
//   * DTE (days to expiration)
//   * expiry calendar date
//   * earnings-intersect badge when an earnings event falls within
//     the DTE window (caller passes the boolean — earnings detection
//     lives in the events service).
//
// Honest fallback when DTE/expiry missing → renders "expiry n/a".

import { cn } from "@/lib/cn";

export interface OptionsExpiryBadgeProps {
  expiry: string | null;             // ISO date
  dte: number | null;
  earningsBetween?: boolean;         // true if any earnings event falls in window
  className?: string;
}

function formatExpiry(iso: string | null): string {
  if (!iso) return "n/a";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, {
      month: "short", day: "numeric", year: "2-digit",
    });
  } catch {
    return iso;
  }
}

function dteTone(dte: number | null): "short" | "mid" | "long" | "none" {
  if (dte == null) return "none";
  if (dte <= 7) return "short";
  if (dte <= 45) return "mid";
  return "long";
}

export default function OptionsExpiryBadge({
  expiry, dte, earningsBetween, className,
}: OptionsExpiryBadgeProps) {
  const tone = dteTone(dte);
  return (
    <span
      className={cn("opt-expiry-badge", `opt-expiry-${tone}`, className)}
      data-test="opt-expiry-badge"
    >
      <span className="opt-expiry-dte">
        {dte != null ? `${dte}d` : "—"}
      </span>
      <span className="opt-expiry-date">{formatExpiry(expiry)}</span>
      {earningsBetween && (
        <span className="opt-expiry-earnings"
              title="Earnings event falls within this expiry window">
          earnings
        </span>
      )}
    </span>
  );
}
