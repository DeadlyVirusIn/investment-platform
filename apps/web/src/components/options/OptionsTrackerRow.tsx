// Phase Opt-C1 Step 10 — Refined tracker row.
//
// Desktop: 12-column tabular row with lifecycle chip + dot quality.
// Mobile (<640): card-stack render in OptionsTrackerWorkflow.
//
// Discipline:
//   - Calm tabular tone, no flashing P&L
//   - tabular-nums for all numerics
//   - lifecycle chip color-coded per Opt-B2 state
//   - Notes pill is reserved (count=0 always; Opt-C3 placeholder)

import OptionsLifecycleChip, {
  type LifecycleStatus,
} from "./OptionsLifecycleChip";
import { cn } from "@/lib/cn";
import type { PaperTradeHeader } from "@/lib/options/optionsApi";


function _fmtMoney(v: string | number | null | undefined): string {
  if (v == null || v === "") return "—";
  const n = typeof v === "number" ? v : parseFloat(v);
  if (Number.isNaN(n)) return String(v);
  return `${n >= 0 ? "" : "-"}$${Math.abs(n).toFixed(2)}`;
}


function _fmtPct(v: string | number | null | undefined): string {
  if (v == null || v === "") return "—";
  const n = typeof v === "number" ? v : parseFloat(v);
  if (Number.isNaN(n)) return String(v);
  return `${n >= 0 ? "+" : ""}${n.toFixed(0)}%`;
}


function _fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${m}/${day}`;
}


function _toneForPnL(v: string | number | null | undefined): string {
  if (v == null || v === "") return "";
  const n = typeof v === "number" ? v : parseFloat(v);
  if (Number.isNaN(n) || n === 0) return "";
  return n > 0 ? "is-pos" : "is-neg";
}


export interface OptionsTrackerRowProps {
  trade: PaperTradeHeader;
  /** Display layout mode. Workflow group passes "desktop" or "mobile"
   *  based on viewport. Defaults to desktop. */
  layout?: "desktop" | "mobile";
}


export default function OptionsTrackerRow({ trade, layout = "desktop" }: OptionsTrackerRowProps) {
  const status = trade.status as LifecycleStatus;
  const pnl = trade.realized_pnl_dollars;
  const tone = _toneForPnL(pnl);

  // Rough % P&L — server doesn't expose %, derive from
  // realized / max_loss when both present (positions not yet showing
  // real-time P&L until live). Show "—" otherwise.
  const pctRaw = (() => {
    if (pnl == null || pnl === "") return null;
    if (trade.max_loss_dollars == null || trade.max_loss_dollars === "") return null;
    const p = parseFloat(pnl);
    const ml = parseFloat(trade.max_loss_dollars);
    if (Number.isNaN(p) || Number.isNaN(ml) || ml === 0) return null;
    return (p / Math.abs(ml)) * 100;
  })();

  if (layout === "mobile") {
    // Card-stack mobile render
    return (
      <div
        className="opt-tracker-row-mobile"
        data-status={trade.status}
        data-test="options-tracker-row"
      >
        <div className="opt-tracker-row-mobile-head">
          <span className="opt-tracker-mobile-ticker">
            {trade.underlying}
          </span>
          <OptionsLifecycleChip
            status={status}
            opened_at={trade.opened_at}
            closed_at={trade.closed_at}
          />
        </div>
        <div className="opt-tracker-row-mobile-body">
          <span>{trade.strategy_name}</span>
        </div>
        <div className="opt-tracker-row-mobile-foot">
          <span>Entry {_fmtMoney(trade.entry_credit_dollars)}</span>
          <span className={cn("opt-tracker-pnl", tone)}>
            {_fmtMoney(pnl)}
            {pctRaw !== null && (
              <span className="opt-tracker-pct">{` ${_fmtPct(pctRaw)}`}</span>
            )}
          </span>
        </div>
      </div>
    );
  }

  // Desktop tabular row (12 columns)
  return (
    <tr
      className="opt-tracker-row"
      data-status={trade.status}
      data-test="options-tracker-row"
    >
      <td className="opt-tracker-cell-date">{_fmtDate(trade.opened_at)}</td>
      <td className="opt-tracker-cell-ticker">{trade.underlying}</td>
      <td className="opt-tracker-cell-strategy">{trade.strategy_name}</td>
      <td className="opt-tracker-cell-legs">—</td>
      <td className="opt-tracker-cell-exp">—</td>
      <td className="opt-tracker-cell-num">1</td>
      <td className="opt-tracker-cell-num">{_fmtMoney(trade.entry_credit_dollars)}</td>
      <td className="opt-tracker-cell-num">—</td>
      <td className={cn("opt-tracker-cell-num", tone)}>
        {_fmtMoney(pnl)}
      </td>
      <td className={cn("opt-tracker-cell-num", tone)}>
        {pctRaw !== null ? _fmtPct(pctRaw) : "—"}
      </td>
      <td className="opt-tracker-cell-status">
        <OptionsLifecycleChip
          status={status}
          opened_at={trade.opened_at}
          closed_at={trade.closed_at}
        />
      </td>
      <td className="opt-tracker-cell-notes">
        <span className="opt-tracker-notes-pill" title="Research notes — Phase Opt-C3">
          Notes (0)
        </span>
      </td>
    </tr>
  );
}
