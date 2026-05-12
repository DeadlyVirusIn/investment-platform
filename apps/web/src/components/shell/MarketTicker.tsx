// Market Tape — Phase 15h.5 polished render.
//
// Reads /api/market/tape (backend-cached Polygon delayed snapshots,
// SPY/QQQ/DIA, 90s refresh, with 30-min minute-bar history per symbol).
// Frontend NEVER calls Polygon directly.
//
// Operator decision (2026-05-12): the original "no animation / no fake
// real-time motion" lock is RELAXED for the tape ribbon only. Scroll
// + price-change flash + real sparklines are restored. The data layer
// remains honest — 15-min delayed, real minute-bar history — only the
// presentation gets the Bloomberg-tape polish back.

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { useTape, type TapeQuote, type TapeScope } from "@/lib/market/hooks";
import Sparkline from "./Sparkline";


export interface MarketTickerProps {
  /** Render density.
   *  "full"    = ticker items + delay chip + sparkline + scroll animation
   *  "compact" = ticker items + scroll, no chip, no sparkline */
  mode?: "full" | "compact";
  /** Data source. Defaults to "macro" (SPY/QQQ/DIA from /api/market/tape).
   *  "holdings" reads /api/market/holdings-tape (open paper positions). */
  kind?: TapeScope;
}


export default function MarketTicker({ mode = "full", kind = "macro" }: MarketTickerProps) {
  const isCompact = mode === "compact";
  const { data, isLoading, isError } = useTape(kind);

  const containerCls = cn(
    "u-market-ticker",
    isCompact && "u-market-ticker--compact",
  );

  const tapeName =
    kind === "holdings" ? "Holdings tape"
    : kind === "combined" ? "Market tape"
    : "Market tape";

  // -------- Loading first fetch --------
  if (isLoading || !data) {
    return (
      <div
        className={cn(containerCls, "u-market-ticker--disabled")}
        role="status"
        aria-label={`Loading ${tapeName.toLowerCase()}`}
        data-tape-state="loading"
        data-tape-kind={kind}
      >
        <div className="u-market-ticker-disabled-text">
          Loading {tapeName.toLowerCase()}…
        </div>
      </div>
    );
  }

  // -------- Empty positions (holdings only): calm "no holdings" --------
  if (kind === "holdings" && data.quotes.length === 0
      && (data.symbols_tracked?.length ?? 0) === 0) {
    return (
      <div
        className={cn(containerCls, "u-market-ticker--disabled")}
        role="status"
        aria-label="No open holdings to display"
        data-tape-state="empty"
        data-tape-kind={kind}
      >
        <div className="u-market-ticker-disabled-text">
          No open paper holdings · holdings tape activates with open positions
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
        aria-label={`${tapeName} unavailable, awaiting live quote feed`}
        data-tape-state="disabled"
        data-tape-kind={kind}
      >
        <div className="u-market-ticker-disabled-text">
          {tapeName} unavailable · awaiting live quote feed
        </div>
      </div>
    );
  }

  // -------- Real quotes --------
  // Duplicate for seamless scroll loop. With only 3 symbols the
  // duplicated set fills the visible width comfortably.
  const track = [...data.quotes, ...data.quotes];

  return (
    <div
      className={containerCls}
      data-tape-state="live"
      data-tape-source={data.source ?? undefined}
      data-tape-kind={kind}
    >
      <div className="u-ticker-track">
        {track.map((q, i) => (
          <TickerItem
            key={`${q.symbol}-${i}`}
            q={q}
            compact={isCompact}
            // Holdings symbols never carry minute-bar history (cycle
            // cost). For combined-tape, per-quote suppression is
            // driven by the absence of `q.history` rather than the
            // outer kind — macro symbols still get sparklines, holdings
            // segment renders price+% only.
            suppressSpark={kind === "holdings"}
          />
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


function TickerItem({
  q, compact, suppressSpark = false,
}: {
  q: TapeQuote;
  compact: boolean;
  suppressSpark?: boolean;
}) {
  const change = q.change_abs;
  const pct = q.change_pct;
  const toneCls =
    change == null ? "" : change > 0 ? "is-pos" : change < 0 ? "is-neg" : "";
  const arrow = change == null ? "·" : change > 0 ? "▲" : change < 0 ? "▼" : "·";
  const priceDigits =
    q.price == null ? 0 : q.price >= 1000 ? 2 : q.price >= 10 ? 2 : 3;

  // Price-change flash — fire briefly when the price differs from the
  // previously-rendered value for this symbol. Pure presentational; no
  // data fabrication.
  const prevPriceRef = useRef<number | null>(q.price);
  const [flash, setFlash] = useState<"pos" | "neg" | null>(null);
  useEffect(() => {
    if (q.price == null || prevPriceRef.current == null) {
      prevPriceRef.current = q.price;
      return;
    }
    if (q.price !== prevPriceRef.current) {
      setFlash(q.price > prevPriceRef.current ? "pos" : "neg");
      prevPriceRef.current = q.price;
      const t = window.setTimeout(() => setFlash(null), 500);
      return () => window.clearTimeout(t);
    }
  }, [q.price]);

  const sparkTone: "pos" | "neg" = (change ?? 0) >= 0 ? "pos" : "neg";

  return (
    <div
      className={cn("u-ticker-item", toneCls)}
      data-flash={flash ?? undefined}
    >
      <span className="u-ticker-sym">{q.symbol}</span>
      <span className="u-ticker-px">
        {q.price != null ? q.price.toFixed(priceDigits) : "—"}
      </span>
      {!compact && !suppressSpark && q.history && q.history.length > 1 && (
        <Sparkline points={q.history} tone={sparkTone} />
      )}
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
        <span className={cn("u-ticker-chg", toneCls)}>
          {arrow} {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
        </span>
      )}
    </div>
  );
}
