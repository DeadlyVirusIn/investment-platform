// Phase 6b-3-e — Journal surface (the engine's memory).
//
// Composition (5 layers, calm temporal):
//   1. Pulse strip                  one line: real counts + "since" date
//   2. Active observations          OptionsTrackerWorkflow (existing,
//                                   the 6-group paper-trade tracker;
//                                   honestly empty groups carry their
//                                   own microcopy)
//   3. Lifecycle timeline           Per-trade chronology when a trade
//                                   is selected (URL hash deep-link
//                                   #lifecycle=N OR auto-select the
//                                   only trade if exactly one exists)
//   4. Evaluator history            NEW — per-day chronology, honestly
//                                   sparse
//   5. Pathways                     three editorial doorways
//
// Per the queued 6b-3-e direction:
//   "Real observational history. Real shadow decisions. Real
//    lifecycle events. Real outcome timelines. Even if tiny/sparse."
//   "The user should feel: 'This system has memory.'"
//
// Discipline:
//   * Read-only. No execution UI. No mutation paths.
//   * Honest scarcity — empty groups, empty timelines, sparse
//     evaluator history all rendered as-is, never inflated.
//   * The single existing paper trade (BULL_CALL_SPREAD on AMZN
//     opened 2026-05-04) renders truthfully — including the fact
//     that AMZN is no longer in the configured universe (a Phase B
//     artifact that the page acknowledges through real data).

import { useOptionsPaperTrades } from "@/lib/options/hooks";

import OptionsJournalPulse from
  "@/components/options/OptionsJournalPulse";
import OptionsTrackerWorkflow from
  "@/components/options/OptionsTrackerWorkflow";
import OptionsLifecycleTimeline from
  "@/components/options/OptionsLifecycleTimeline";
import OptionsJournalEvaluatorHistory from
  "@/components/options/OptionsJournalEvaluatorHistory";
import OptionsJournalPathways from
  "@/components/options/OptionsJournalPathways";


/** Auto-select trade for lifecycle display:
 *   1. URL hash override (#lifecycle=N) — operator's explicit choice
 *   2. Otherwise, when exactly one paper trade exists, show its
 *      lifecycle automatically (current real state has 1 trade)
 *   3. Otherwise, show no timeline (the tracker workflow above
 *      already lists trades; operator picks via deep-link)
 */
function _selectedTradeId(soleTradeId: number | null): number | null {
  if (typeof window !== "undefined") {
    const m = window.location.hash.match(/lifecycle=(\d+)/);
    if (m) return Number(m[1]);
  }
  return soleTradeId;
}


export default function OptionsJournalPage() {
  const { data: tradesData } = useOptionsPaperTrades({});
  const trades = tradesData?.trades ?? [];
  const soleTradeId = trades.length === 1 ? trades[0].id : null;
  const selectedTradeId = _selectedTradeId(soleTradeId);

  return (
    <div className="opt-journal" data-test="options-journal-page">
      {/* 1. Pulse — real counts, since-date */}
      <OptionsJournalPulse />

      {/* 2. Active observations — 6-group tracker (honest empty groups) */}
      <OptionsTrackerWorkflow />

      {/* 3. Lifecycle timeline for selected trade.
            With 1 PROPOSED trade today, this auto-selects + renders.
            Lifecycle is currently EMPTY (0 transitions) — the
            timeline component handles that honestly. */}
      {selectedTradeId !== null && (
        <OptionsLifecycleTimeline trade_id={selectedTradeId} />
      )}

      {/* 4. Evaluator history — per-day chronology */}
      <OptionsJournalEvaluatorHistory />

      {/* 5. Pathways — three editorial doorways */}
      <OptionsJournalPathways />
    </div>
  );
}
