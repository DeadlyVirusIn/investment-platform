// Phase UI3 — Operator (polished UI4).
//
// Phase 11Z: TradeTimeline reads paper_trade_log (selector path) which
// is 0 after the 2026-05-02 wipe + replay. The replay-availability
// banner here informs the operator that account-path executed trades
// + recovered replay rows live on the Paper Trading Terminal at
// /portfolio (which has the toggle).

import { useState } from "react";
import TradeTimeline from "@/components/operator/TradeTimeline";
import DecisionDetail from "@/components/operator/DecisionDetail";
import AnomalyPanel from "@/components/operator/AnomalyPanel";
import ShadowPanel from "@/components/operator/ShadowPanel";
import type { TradeRow } from "@/lib/operator/types";
import { useExecutedSummary } from "@/lib/operator/hooks";
import { cn } from "@/lib/cn";

type TabId = "decision" | "anomalies" | "shadow";

const TABS: [TabId, string][] = [
  ["decision", "Decision"],
  ["anomalies", "Anomalies"],
  ["shadow", "Shadow Signals"],
];

export default function PaperOperator() {
  const [selectedTrade, setSelectedTrade] = useState<TradeRow | null>(null);
  const [tab, setTab] = useState<TabId>("decision");

  const asOfDate = selectedTrade?.entry_date ?? null;

  const { data: execSummary } = useExecutedSummary(false);
  const liveTrades = execSummary?.live_trades_count ?? 0;
  const replayTrades = execSummary?.replay_trades_count ?? 0;
  const replayPositions = execSummary?.replay_open_positions_count ?? 0;
  const hasReplay = !!execSummary?.has_replay_recovered_rows;

  return (
    <div className="min-h-screen bg-surface">
      <div className="max-w-[1440px] mx-auto px-8 py-10">
        <header className="mb-8">
          <h1 className="page-title mb-1">Operator</h1>
          <p className="text-label text-text-secondary">
            System behavior explained — click a trade to inspect.
          </p>
        </header>

        {/* Phase 11Z — TradeTimeline below shows paper_trade_log
            (selector path). Account-path executed trades and any
            recovered replay rows are surfaced separately. */}
        <div
          data-test="paper-operator-data-streams"
          className="mb-6 rounded-md border border-surface-border bg-surface-card px-4 py-3 text-sm text-text-secondary"
        >
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
            <span>
              <strong className="text-text-primary">{liveTrades}</strong> live
              executed trades
            </span>
            <span>
              <strong className="text-text-primary">{replayTrades}</strong>{" "}
              recovered replay trades
            </span>
            <span>
              <strong className="text-text-primary">{replayPositions}</strong>{" "}
              recovered open positions
            </span>
            <a
              href="/portfolio"
              className="ml-auto text-xs underline text-text-primary"
            >
              Open Paper Trading Terminal →
            </a>
          </div>
          {hasReplay && (
            <div
              data-test="paper-operator-replay-note"
              className="mt-2 text-xs text-amber-300"
            >
              Recovered replay rows present — NOT live trading activity.
              Toggle "Show recovered replay data" on the Paper Trading
              Terminal to inspect. The timeline below shows the selector
              strategy log (paper_trade_log) which is independent.
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[400px_1fr] gap-8
                         h-[calc(100vh-200px)] min-h-[640px]">
          {/* LEFT — timeline */}
          <div className="overflow-hidden">
            <TradeTimeline selectedTradeId={selectedTrade?.trade_id ?? null}
                           onSelect={setSelectedTrade} />
          </div>

          {/* RIGHT — tabs + content */}
          <div className="flex flex-col overflow-hidden">
            <nav className="flex gap-0.5 mb-6 border-b border-surface-border/60">
              {TABS.map(([k, label]) => (
                <button key={k}
                  onClick={() => setTab(k)}
                  className={cn(
                    "text-label px-4 py-2.5 border-b-2 transition-all duration-150",
                    tab === k
                      ? "border-accent text-text-primary font-semibold"
                      : "border-transparent text-text-muted hover:text-text-primary"
                        + " hover:border-surface-border",
                  )}>
                  {label}
                </button>
              ))}
            </nav>

            <div className="flex-1 overflow-y-auto pr-1">
              {tab === "decision" && <DecisionDetail asOfDate={asOfDate} />}
              {tab === "anomalies" && <AnomalyPanel />}
              {tab === "shadow" && <ShadowPanel />}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
