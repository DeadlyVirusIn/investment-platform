// AccountingStrip — single canonical portfolio-truth primitive.
//
// PURPOSE
// The investment-platform UI has historically rendered the same
// portfolio numerics with mismatched labels in ~8 different surfaces
// (PortfolioTerminal, PortfolioSnapshot, Overview, TopStrip,
// CommandBar, RiskDashboard, Dashboard, Briefing). This file is the
// ONE source of canonical accounting presentation.
//
// SOURCE OF TRUTH
// All numerics come from `/api/paper/summary` (aggregate across active
// paper portfolios). This component performs NO accounting math of
// its own — it is purely presentation. The backend identity:
//   equity − starting_capital_total ≡ unrealized + realized
// is enforced by the API; this component just renders it honestly.
//
// CANONICAL TERMINOLOGY (locked)
//   Starting capital      — Σ paper_portfolio.starting_cash
//   Account value (NAV)   — cash + market value of open positions
//   Total profit          — NAV − starting capital
//   Today P&L             — NAV(today) − NAV(yesterday's snapshot)
//   Unrealized P&L        — Σ qty * (last_price − avg_cost) (open)
//   Realized P&L          — Σ paper_trade.realized_pnl
//   Holdings value        — market value of open positions
//   Cost basis            — Σ qty * avg_cost (open)
//   Available cash        — paper_portfolio.cash
//
// VARIANTS
//   variant="full"      → 4 headline + 5 breakdown rows (default)
//   variant="headline"  → 4 headline tiles only
//   variant="compact"   → single 5-cell row for tight slots

import { ReactNode } from "react";

import { fmtUSD, fmtSignedUSD, fmtPct, toneForNumber } from
  "@/components/ui/primitives";
import { cn } from "@/lib/cn";


export interface AccountingTruthData {
  equity: number | null;
  cash: number | null;
  holdingsValue: number | null;        // = positions_value (MV)
  costBasis: number | null;
  unrealizedPnl: number | null;
  realizedPnl: number | null;
  totalReturnPct: number | null;
  dailyPnl: number | null;
  startingCapital: number | null;
  portfolioCount: number | null;
  openPositionsCount: number | null;
  replayPositionsMarketValue: number | null;
  /** Cohesion polish — replay share of cumulative realized P&L. Used to
      attribute headline "Total profit" honestly. Null when the manifest
      table is absent or no replay trades exist. */
  replayRealizedPnlCumulative?: number | null;
  /** ISO date or display string for "as of …" */
  asOf?: string | null;
}


export type AccountingStripVariant = "full" | "headline" | "compact";


export interface AccountingStripProps {
  data: AccountingTruthData;
  variant?: AccountingStripVariant;
  /** Framing override — when `data.portfolioCount` is null/single, this
   *  prop forces an explicit scope label (e.g. "Portfolio: Default Paper"). */
  scopeLabel?: string;
  /** Equity sparkline values for the NAV tile in `full`/`headline`. */
  equitySparkline?: ReactNode;
  /** Total-return sparkline values for the Total profit tile. */
  returnSparkline?: ReactNode;
  /** Render a replay banner below the strip when the manifest flags
   *  positions are contributing to NAV. Pass `false` to suppress. */
  showReplayBanner?: boolean;
}


function StripCell({
  label, value, sub, tone = "neutral", spark,
}: {
  label: string; value: string; sub?: string;
  tone?: "pos" | "neg" | "neutral";
  spark?: ReactNode;
}) {
  const cls = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger" : "text-fg";
  return (
    <div className="px-6 first:pl-0 last:pr-0">
      <div className="flex items-start justify-between gap-2">
        <div className="u-label mb-3">{label}</div>
        {spark && (
          <div className="opacity-90 shrink-0 mt-[-2px]">{spark}</div>
        )}
      </div>
      <div className={cn("u-num-lg", cls)}>{value}</div>
      {sub != null && <div className="u-caption-2 mt-1.5">{sub}</div>}
    </div>
  );
}


function scopeFraming(
  data: AccountingTruthData, override?: string,
): string {
  if (override) return override;
  const n = data.portfolioCount;
  if (n == null) return "Aggregate across active paper portfolios";
  return `Across ${n} paper portfolio${n === 1 ? "" : "s"}`;
}


export default function AccountingStrip({
  data, variant = "full", scopeLabel,
  equitySparkline, returnSparkline,
  showReplayBanner = true,
}: AccountingStripProps) {
  const nav        = data.equity;
  const starting   = data.startingCapital;
  const unrealized = data.unrealizedPnl;
  const realized   = data.realizedPnl;
  const todayPnl   = data.dailyPnl;
  const cash       = data.cash;
  const holdings   = data.holdingsValue;
  const basis      = data.costBasis;

  // Total profit derived ONLY from canonical fields. If startingCapital
  // is unavailable we render "—" rather than guess.
  const totalProfit = (starting != null && nav != null)
    ? nav - starting : null;

  const headlineFraming = scopeFraming(data, scopeLabel);

  // ----- compact variant -----
  if (variant === "compact") {
    return (
      <div className="u-card">
        <div className="grid grid-cols-1 md:grid-cols-5 divide-x divide-b2">
          <StripCell
            label="Account value (NAV)"
            value={nav != null ? fmtUSD(nav) : "—"}
            sub={headlineFraming} />
          <StripCell
            label="Total profit"
            value={totalProfit != null ? fmtSignedUSD(totalProfit) : "—"}
            tone={toneForNumber(totalProfit ?? 0)}
            sub={data.totalReturnPct != null
              ? `${fmtPct(data.totalReturnPct)} since inception`
              : "Since inception"} />
          <StripCell
            label="Today P&L"
            value={todayPnl != null ? fmtSignedUSD(todayPnl) : "—"}
            tone={toneForNumber(todayPnl ?? 0)}
            sub={(nav != null && nav > 0 && todayPnl != null)
              ? `${fmtPct((todayPnl / nav) * 100)} today`
              : "vs previous snapshot"} />
          <StripCell
            label="Unrealized P&L"
            value={unrealized != null ? fmtSignedUSD(unrealized) : "—"}
            tone={toneForNumber(unrealized ?? 0)}
            sub={data.openPositionsCount != null
              ? `${data.openPositionsCount} open`
              : undefined} />
          <StripCell
            label="Realized P&L"
            value={realized != null ? fmtSignedUSD(realized) : "—"}
            tone={toneForNumber(realized ?? 0)}
            sub="Closed trades" />
        </div>
      </div>
    );
  }

  // ----- headline + (optionally) breakdown -----
  return (
    <>
      <div className="u-card">
        <div className="grid grid-cols-1 md:grid-cols-4 divide-x divide-b2">
          <StripCell
            label="Starting capital"
            value={starting != null ? fmtUSD(starting) : "—"}
            sub={headlineFraming} />
          <StripCell
            label="Account value (NAV)"
            value={nav != null ? fmtUSD(nav) : "—"}
            sub="cash + holdings, marked to latest close"
            spark={equitySparkline} />
          <StripCell
            label="Total profit"
            value={totalProfit != null ? fmtSignedUSD(totalProfit) : "—"}
            tone={toneForNumber(totalProfit ?? 0)}
            sub={data.totalReturnPct != null
              ? `${fmtPct(data.totalReturnPct)} since inception`
              : "Since inception"}
            spark={returnSparkline} />
          <StripCell
            label="Today P&L"
            value={todayPnl != null ? fmtSignedUSD(todayPnl) : "—"}
            tone={toneForNumber(todayPnl ?? 0)}
            sub={(nav != null && nav > 0 && todayPnl != null)
              ? `${fmtPct((todayPnl / nav) * 100)} today`
              : "vs previous snapshot"} />
        </div>
      </div>

      {variant === "full" && (
        <div className="u-card">
          <div className="grid grid-cols-1 md:grid-cols-5 divide-x divide-b2">
            <StripCell
              label="Unrealized P&L"
              value={unrealized != null ? fmtSignedUSD(unrealized) : "—"}
              tone={toneForNumber(unrealized ?? 0)}
              sub={data.openPositionsCount != null
                ? `${data.openPositionsCount} open position${data.openPositionsCount === 1 ? "" : "s"}`
                : "Mark-to-market on open positions"} />
            <StripCell
              label="Realized P&L"
              value={realized != null ? fmtSignedUSD(realized) : "—"}
              tone={toneForNumber(realized ?? 0)}
              sub="Cumulative across closed trades" />
            <StripCell
              label="Holdings value"
              value={holdings != null ? fmtUSD(holdings) : "—"}
              sub={data.openPositionsCount != null
                ? `Market value of ${data.openPositionsCount} open position${data.openPositionsCount === 1 ? "" : "s"}`
                : "Market value of open positions"} />
            <StripCell
              label="Cost basis"
              value={basis != null ? fmtUSD(basis) : "—"}
              sub="Capital deployed at avg entry" />
            <StripCell
              label="Available cash"
              value={cash != null ? fmtUSD(cash) : "—"}
              sub={(cash != null && nav != null && nav > 0)
                ? `${((cash / nav) * 100).toFixed(0)}% of NAV`
                : undefined} />
          </div>
        </div>
      )}

      {showReplayBanner
        && data.replayPositionsMarketValue != null
        && data.replayPositionsMarketValue > 0 && (
        <div
          className="u-card-tight"
          data-test="accounting-strip-replay-banner"
          style={{ background: "var(--sunken)", padding: "8px 12px" }}
        >
          <div className="u-caption">
            <span className="u-chip u-chip-warning mr-2">
              Recovered history
            </span>
            Recovered positions contribute{" "}
            <strong>{fmtUSD(data.replayPositionsMarketValue)}</strong>{" "}
            to account value
            {data.replayRealizedPnlCumulative != null
              && Math.abs(data.replayRealizedPnlCumulative) > 0 && (
              <>
                {" and "}
                <strong>{fmtUSD(data.replayRealizedPnlCumulative)}</strong>
                {" of cumulative realized P&L "}
                <span data-test="accounting-strip-replay-pnl">
                  (included in headline Total profit)
                </span>
              </>
            )}
            . Reconstructed from backup data after a 2026-05-02 reset;
            tagged in <code>replay_recovery_manifest</code>.
          </div>
        </div>
      )}
    </>
  );
}
