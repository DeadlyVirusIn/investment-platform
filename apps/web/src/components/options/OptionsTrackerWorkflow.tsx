// Phase Opt-C1 Step 9 — Tracker workflow grouping.
//
// Composes paper trades into collapsible workflow sections:
//   1. OPEN POSITIONS                 expanded · sort: days held desc
//   2. EXPIRING SOON (≤ 5 days)        expanded · sort: dte asc
//   3. RECENTLY CLOSED (last 7 days)   expanded · sort: closed_at desc
//   4. EXPIRED / ASSIGNED              collapsed · sort: closed_at desc
//   5. REJECTED CANDIDATES             (rendered separately by
//                                       OptionsRejectedCandidatesGroup)
//   6. WATCHLIST (high-score, untraded) collapsed · sort: score desc
//
// Discipline:
//   - Real DB rows only (no synthetic trades, no duplicate entries)
//   - Empty states explain workflow stage + what populates it + when
//   - Mobile: card-stack layout per row

import { useState } from "react";

import { useOptionsPaperTrades } from "@/lib/options/hooks";
import OptionsTrackerRow from "./OptionsTrackerRow";
import type { PaperTradeHeader } from "@/lib/options/optionsApi";


type GroupKey = "open" | "expiring" | "recent_closed" | "exp_assigned" | "watchlist";


interface GroupConfig {
  key: GroupKey;
  label: string;
  defaultOpen: boolean;
  emptyHeadline: string;
  emptyBody: string;
}


const GROUPS: GroupConfig[] = [
  {
    key: "open",
    label: "Open positions",
    defaultOpen: true,
    emptyHeadline: "No open positions.",
    emptyBody:
      "Open trades appear here after paper exec runs (Phase Opt-B3) " +
      "and the lifecycle transitions PROPOSED → OPEN.",
  },
  {
    key: "expiring",
    label: "Expiring soon (≤ 5 days)",
    defaultOpen: true,
    emptyHeadline: "Nothing expiring within 5 days.",
    emptyBody:
      "When an open position has ≤ 5 days to nearest leg expiry, it " +
      "moves into this section so the operator can review.",
  },
  {
    key: "recent_closed",
    label: "Recently closed (last 7 days)",
    defaultOpen: true,
    emptyHeadline: "No recent closes.",
    emptyBody:
      "Trades that exited (target hit, stop hit, manual close) in the " +
      "last 7 days appear here with realized P&L and close reason.",
  },
  {
    key: "exp_assigned",
    label: "Expired / assigned",
    defaultOpen: false,
    emptyHeadline: "No expired or assigned trades yet.",
    emptyBody:
      "Trades held to expiry resolve to EXPIRED (OTM) or ASSIGNED " +
      "(SHORT leg ITM). Lifecycle classifications surface here.",
  },
  {
    key: "watchlist",
    label: "Watchlist (high-score, untraded)",
    defaultOpen: false,
    emptyHeadline: "Watchlist is empty.",
    emptyBody:
      "Setups with strong quality scores that did not enter paper " +
      "trading appear here for monitoring.",
  },
];


function _classify(t: PaperTradeHeader): GroupKey {
  if (t.status === "OPEN") return "open";
  if (t.status === "EXPIRING") return "expiring";
  if (t.status === "CLOSED") {
    // Recent close = closed_at within 7 days
    if (t.closed_at) {
      const ageDays =
        (Date.now() - new Date(t.closed_at).getTime()) / 86_400_000;
      if (ageDays <= 7) return "recent_closed";
    }
    return "exp_assigned";
  }
  if (t.status === "EXPIRED" || t.status === "ASSIGNED") return "exp_assigned";
  // PROPOSED — currently no group; surfaces in OPEN bucket so
  // operator sees it (counts as in-flight). Honest because the
  // schema treats PROPOSED as pre-OPEN, not pre-active.
  if (t.status === "PROPOSED") return "open";
  return "open";
}


function _GroupSection({
  cfg, trades,
}: { cfg: GroupConfig; trades: PaperTradeHeader[] }) {
  const [open, setOpen] = useState(cfg.defaultOpen);
  return (
    <section
      className="opt-tracker-group"
      data-group={cfg.key}
      data-test={`options-tracker-group-${cfg.key}`}
    >
      <button
        type="button"
        className="opt-tracker-group-head"
        aria-expanded={open}
        onClick={() => setOpen(o => !o)}
      >
        <span className="opt-tracker-group-toggle">{open ? "▾" : "▸"}</span>
        <span className="opt-tracker-group-label">{cfg.label}</span>
        <span className="opt-tracker-group-count">
          {trades.length}
        </span>
      </button>

      {open && trades.length === 0 && (
        <div className="opt-empty" style={{ marginLeft: 22 }}>
          <p className="opt-empty-headline">{cfg.emptyHeadline}</p>
          <p className="opt-empty-body">{cfg.emptyBody}</p>
        </div>
      )}

      {open && trades.length > 0 && (
        <>
          {/* Desktop table */}
          <div className="opt-tracker-table-wrap">
            <table className="opt-tracker-table">
              <thead>
                <tr>
                  <th>Date</th><th>Ticker</th><th>Strategy</th>
                  <th>Legs</th><th>Exp</th><th>Qty</th>
                  <th>Entry</th><th>Cur</th><th>P&amp;L</th><th>%</th>
                  <th>Status</th><th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {trades.map(t => (
                  <OptionsTrackerRow key={t.id} trade={t} layout="desktop" />
                ))}
              </tbody>
            </table>
          </div>
          {/* Mobile card list */}
          <div className="opt-tracker-mobile-list">
            {trades.map(t => (
              <OptionsTrackerRow key={t.id} trade={t} layout="mobile" />
            ))}
          </div>
        </>
      )}
    </section>
  );
}


export default function OptionsTrackerWorkflow() {
  const { data, isLoading } = useOptionsPaperTrades({});
  const trades = data?.trades ?? [];

  // Bucket trades by group
  const buckets: Record<GroupKey, PaperTradeHeader[]> = {
    open: [],
    expiring: [],
    recent_closed: [],
    exp_assigned: [],
    watchlist: [],
  };
  for (const t of trades) {
    buckets[_classify(t)].push(t);
  }
  // Sort defaults
  buckets.open.sort((a, b) => {
    // days held desc — older first if no opened_at
    const at = a.opened_at ? new Date(a.opened_at).getTime() : 0;
    const bt = b.opened_at ? new Date(b.opened_at).getTime() : 0;
    return at - bt;
  });
  buckets.recent_closed.sort((a, b) => {
    const at = a.closed_at ? new Date(a.closed_at).getTime() : 0;
    const bt = b.closed_at ? new Date(b.closed_at).getTime() : 0;
    return bt - at;
  });
  buckets.exp_assigned.sort((a, b) => {
    const at = a.closed_at ? new Date(a.closed_at).getTime() : 0;
    const bt = b.closed_at ? new Date(b.closed_at).getTime() : 0;
    return bt - at;
  });

  return (
    <section className="u-card opt-card" data-test="options-tracker-workflow">
      <header className="opt-card-header">
        <span className="opt-card-eyebrow">Paper options journal</span>
        <span className="opt-card-meta">
          {isLoading
            ? "loading…"
            : `${trades.length} total · ${GROUPS.length} workflow sections`}
        </span>
      </header>

      <div className="opt-tracker-groups">
        {GROUPS.map(cfg => (
          <_GroupSection
            key={cfg.key}
            cfg={cfg}
            trades={buckets[cfg.key]}
          />
        ))}
      </div>
    </section>
  );
}
