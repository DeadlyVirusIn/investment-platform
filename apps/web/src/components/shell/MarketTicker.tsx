// Market Tape — honest disabled state (Phase 15h.5).
//
// Until a real delayed-quote provider is integrated (per
// docs/research/MARKET_QUOTE_PROVIDER_EVAL.md), this component
// renders a calm, subdued "awaiting live quote feed" strip in place
// of the previous synthetic-random-walk ticker. The render is
// deliberately quiet: no motion, no symbol prices, no chevrons, no
// color tone. It communicates that the slot is reserved without
// pretending data exists.
//
// Architecture preserved for future integration:
//   - mode prop ("full" | "compact") still routes through
//   - tickerModeForRoute(pathname) in Shell.tsx still chooses the slot
//   - .u-market-ticker / .u-market-ticker--compact CSS classes still applied
//   - hook contract (useMarketQuotes) unchanged in lib/market/hooks.ts
//
// When a provider ships, replace this file's render body with the
// quote-driven track + ModeToggle (see git history for the previous
// implementation; the structural shape is unchanged).

import { cn } from "@/lib/cn";

export interface MarketTickerProps {
  /** Render density for the tape slot.
   *  "full"    = larger row reserved for the eventual track + toggle
   *  "compact" = smaller row sized for executive surfaces (overview etc.) */
  mode?: "full" | "compact";
}

export default function MarketTicker({ mode = "full" }: MarketTickerProps) {
  const isCompact = mode === "compact";
  return (
    <div
      className={cn(
        "u-market-ticker",
        "u-market-ticker--disabled",
        isCompact && "u-market-ticker--compact",
      )}
      role="status"
      aria-label="Market tape unavailable, awaiting live quote feed"
      data-tape-state="disabled"
    >
      <div className="u-market-ticker-disabled-text">
        Market tape unavailable · awaiting live quote feed
      </div>
    </div>
  );
}
