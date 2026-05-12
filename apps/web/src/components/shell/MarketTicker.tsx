// Market Tape — Phase 15h.5 real-data render.
//
// Reads /api/market/tape (backend-cached Polygon delayed snapshots,
// SPY/QQQ/DIA, 90s refresh) via useMarketTape(). Frontend NEVER calls
// Polygon directly.
//
// UX discipline:
//   - No animation on number change. TanStack Query swaps values
//     in place; we apply no flash, no color tween.
//   - No fake real-time motion. The track is static (no infinite
//     scroll); 3 symbols fit easily on every viewport.
//   - Honest delay label: "15m delayed · Polygon" pinned to the
//     right edge in full mode. Compact mode omits the chip to keep
//     the executive surfaces' focal hierarchy intact.
//   - Loading / stale / error states render the same calm disabled
//     strip as the no-provider state — communicates the gap without
//     alarming the user.

import { cn } from "@/lib/cn";
import { useMarketTape, type TapeQuote } from "@/lib/market/hooks";


export interface MarketTickerProps {
  /** Render density.
   *  "full"    = ticker items + delay chip + larger row
   *  "compact" = ticker items only, smaller row, no chip */
  mode?: "full" | "compact";
}


export default function MarketTicker({ mode = "full" }: MarketTickerProps) {
  const isCompact = mode === "compact";
  const { data, isLoading, isError } = useMarketTape();

  const containerCls = cn(
    "u-market-ticker",
    isCompact && "u-market-ticker--compact",
  );

  // -------- Loading first fetch --------
  if (isLoading || !data) {
    return (
      <div
        className={cn(containerCls, "u-market-ticker--disabled")}
        role="status"
        aria-label="Loading market tape"
        data-tape-state="loading"
      >
        <div className="u-market-ticker-disabled-text">
          Loading market tape…
        </div>
      </div>
    );
  }

  // -------- Stale, error, or empty quotes --------
  if (isError || data.stale || data.quotes.length === 0) {
    return (
      <div
        className={cn(containerCls, "u-market-ticker--disabled")}
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

  // -------- Real quotes --------
  return (
    <div
      className={containerCls}
      data-tape-state="live"
      data-tape-source={data.source ?? undefined}
    >
      <div className="u-ticker-track u-ticker-track--static">
        {data.quotes.map((q) => (
          <TickerItem key={q.symbol} q={q} compact={isCompact} />
        ))}
      </div>
      {!isCompact && (
        <div className="u-ticker-delay-chip" aria-hidden="true">
          {`${data.max_delay_minutes ?? 15}m delayed · ${data.source ?? "polygon"}`}
        </div>
      )}
    </div>
  );
}


function TickerItem({ q, compact }: { q: TapeQuote; compact: boolean }) {
  const change = q.change_abs;
  const pct = q.change_pct;
  const toneCls =
    change == null ? "" : change > 0 ? "is-pos" : change < 0 ? "is-neg" : "";
  const arrow = change == null ? "·" : change > 0 ? "▲" : change < 0 ? "▼" : "·";
  // Decimal precision matches institutional convention (2dp for prices
  // ≥ $10, 3dp under). ETFs in MACRO scope are all ≥ $10.
  const priceDigits =
    q.price == null ? 0 : q.price >= 1000 ? 2 : q.price >= 10 ? 2 : 3;

  return (
    <div className={cn("u-ticker-item", toneCls)}>
      <span className="u-ticker-sym">{q.symbol}</span>
      <span className="u-ticker-px">
        {q.price != null ? q.price.toFixed(priceDigits) : "—"}
      </span>
      {!compact && (
        <span className={cn("u-ticker-chg", toneCls)}>
          {arrow}{" "}
          {change != null
            ? `${change >= 0 ? "+" : ""}${change.toFixed(priceDigits)}`
            : "—"}
          {pct != null
            ? ` (${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%)`
            : ""}
        </span>
      )}
      {compact && pct != null && (
        // Compact omits absolute change to save horizontal space; only %
        <span className={cn("u-ticker-chg", toneCls)}>
          {arrow} {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
        </span>
      )}
    </div>
  );
}
