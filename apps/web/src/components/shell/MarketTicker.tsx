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
import { useMarketTape, type TapeQuote } from "@/lib/market/hooks";
import Sparkline from "./Sparkline";


export interface MarketTickerProps {
  /** Render density.
   *  "full"    = ticker items + delay chip + sparkline + scroll animation
   *  "compact" = ticker items + scroll, no chip, no sparkline */
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
  // Duplicate for seamless scroll loop. With only 3 symbols the
  // duplicated set fills the visible width comfortably.
  const track = [...data.quotes, ...data.quotes];

  return (
    <div
      className={containerCls}
      data-tape-state="live"
      data-tape-source={data.source ?? undefined}
    >
      <div className="u-ticker-track">
        {track.map((q, i) => (
          <TickerItem
            key={`${q.symbol}-${i}`}
            q={q}
            compact={isCompact}
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


function TickerItem({ q, compact }: { q: TapeQuote; compact: boolean }) {
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
      {!compact && q.history && q.history.length > 1 && (
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
