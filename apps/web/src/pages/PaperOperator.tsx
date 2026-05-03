// Phase UI3 — Operator (polished UI4).

import { useState } from "react";
import TradeTimeline from "@/components/operator/TradeTimeline";
import DecisionDetail from "@/components/operator/DecisionDetail";
import AnomalyPanel from "@/components/operator/AnomalyPanel";
import ShadowPanel from "@/components/operator/ShadowPanel";
import type { TradeRow } from "@/lib/operator/types";
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

  return (
    <div className="min-h-screen bg-surface">
      <div className="max-w-[1440px] mx-auto px-8 py-10">
        <header className="mb-8">
          <h1 className="page-title mb-1">Operator</h1>
          <p className="text-label text-text-secondary">
            System behavior explained — click a trade to inspect.
          </p>
        </header>

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
