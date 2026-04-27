// Phase UI-TICKER — premium market ribbon.
// Seamless horizontal loop, pause-on-hover, macro/focus mode toggle.

import { useState } from "react";
import { useMarketQuotes, type Quote } from "@/lib/market/hooks";
import Sparkline from "./Sparkline";
import { cn } from "@/lib/cn";

const MACRO = ["SPX", "DJI", "NDX", "VIX", "TNX"];
const FOCUS = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA"];

type Mode = "macro" | "focus";

export default function MarketTicker() {
  const [mode, setMode] = useState<Mode>("macro");
  const symbols = mode === "macro" ? MACRO : FOCUS;
  const { data: quotes, isError } = useMarketQuotes(symbols);

  if (isError || !quotes || quotes.length === 0) {
    return (
      <div className="u-market-ticker">
        <div className="flex items-center px-5 u-caption-2 text-fg-3">
          market feed unavailable
        </div>
        <ModeToggle mode={mode} setMode={setMode} />
      </div>
    );
  }

  // Duplicate for seamless loop
  const track = [...quotes, ...quotes];

  return (
    <div className="u-market-ticker">
      <div className="u-ticker-track">
        {track.map((q, i) => (
          <TickerItem key={`${q.symbol}-${i}`} q={q} />
        ))}
      </div>
      <ModeToggle mode={mode} setMode={setMode} />
    </div>
  );
}

function ModeToggle({
  mode, setMode,
}: { mode: Mode; setMode: (m: Mode) => void }) {
  return (
    <div className="u-ticker-toggle">
      <button onClick={() => setMode("macro")}
        className={cn("u-chip",
          mode === "macro" ? "u-chip-accent" : "u-chip-neutral")}>
        macro
      </button>
      <button onClick={() => setMode("focus")}
        className={cn("u-chip",
          mode === "focus" ? "u-chip-accent" : "u-chip-neutral")}>
        focus
      </button>
    </div>
  );
}

function TickerItem({ q }: { q: Quote }) {
  const toneCls = q.change > 0 ? "is-pos" : q.change < 0 ? "is-neg" : "";
  const arrow   = q.change > 0 ? "▲" : q.change < 0 ? "▼" : "·";
  const digits  = q.price >= 1000 ? 2 : q.price >= 10 ? 2 : 3;
  const sparkTone: "pos" | "neg" = q.change >= 0 ? "pos" : "neg";
  return (
    <div className={cn("u-ticker-item", toneCls)}>
      <span className="u-ticker-sym">{q.symbol}</span>
      <span className="u-ticker-px">{q.price.toFixed(digits)}</span>
      {q.history && q.history.length > 1 && (
        <Sparkline points={q.history} tone={sparkTone} />
      )}
      <span className={cn("u-ticker-chg", toneCls)}>
        {arrow} {q.change >= 0 ? "+" : ""}{q.change.toFixed(digits)}
        {" "}({q.changePct >= 0 ? "+" : ""}{q.changePct.toFixed(2)}%)
      </span>
    </div>
  );
}
