// Phase C — Read-only Risk Dashboard.
//
// Aggregates the truth-aligned paper-trading risk surface from
// /api/performance/paper/risk-dashboard. NEVER fabricates a
// mark; if the server reports `mark_unavailable=true` the
// exposure cards explicitly say "mark unavailable" rather than
// showing a fake $0. NO execution controls anywhere on this page.

import { useState } from "react";
import { cn } from "@/lib/cn";
import { fmtUSD, fmtPct, toneForNumber } from "@/components/ui/primitives";
import {
  useRiskDashboard,
  type ConcentrationSymbolRow,
  type ConcentrationPortfolioRow,
} from "@/lib/operator/hooks";
import InsightDrawer from "@/components/insights/InsightDrawer";
import { useInsight } from "@/lib/insights/hooks";
// Commit 4 (Novice UX) — page-level intro card.
// UX-1 Commit G — focus guidance + collapsible advanced sections.
import { PageGuide, AdvancedDetails } from "@/components/novice";


export default function RiskDashboard() {
  const [includeReplay, setIncludeReplay] = useState(false);
  const q = useRiskDashboard(includeReplay);
  // F3: narrative drawer for the current risk surface. NEVER
  // auto-fetched — operator clicks the "Narrative" button.
  const insight = useInsight("risk_commentary");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const handleNarrative = () => {
    if (!q.data) return;
    setDrawerOpen(true);
    void insight.fetchInsight(q.data);
  };
  const handleCloseDrawer = () => {
    setDrawerOpen(false);
    insight.reset();
  };

  return (
    <div className="max-w-[1480px] mx-auto px-6 py-6 space-y-5">
      {/* Commit 4 (Novice UX) — plain-English page intro. The      */}
      {/* replay toggle and "Generate explanation" button stay      */}
      {/* visible on a separate row so first-time readers see the   */}
      {/* page purpose before the controls.                         */}
      <PageGuide
        eyebrow="Paper Account"
        title="Account risk view"
        subtitle={
          "How spread out your money is and how far you've drawn "
          + "down from a previous high. All numbers are simulated — "
          + "no real money is involved."
        }
        firstLook={
          <>
            Start with <strong>Account value</strong>, then{" "}
            <strong>Percent invested</strong>, then{" "}
            <strong>Biggest drop from peak</strong>.
          </>
        }
      />

      {/* UX-1 Commit G — Start-here focus card. Tells the operator   */}
      {/* what matters first and what they can defer.                 */}
      <section
        className="u-card-tight"
        data-test="risk-start-here"
        style={{ padding: "12px 16px" }}
      >
        <div className="u-caption-2 text-fg-3 uppercase tracking-wide mb-1">
          Focus today
        </div>
        <ol className="u-body text-fg space-y-1 list-decimal pl-5">
          <li>
            <strong>Account value</strong> and{" "}
            <strong>Percent invested</strong> — how much is at work
            in the market.
          </li>
          <li>
            <strong>Biggest drop from peak</strong> — temporary
            declines are normal; only a large drop warrants a deeper
            look.
          </li>
          <li>
            <strong>Largest holdings</strong> — whether one or two
            names are doing most of the work.
          </li>
        </ol>
        <p className="u-caption-2 text-fg-3 mt-2">
          Safe to ignore for now: the all-symbols breakdown,
          portfolio snapshot table, and engineering source lines
          below. They contain detail for advanced users — none
          require action.
        </p>
      </section>

      {/* UX-1 Commit G — engineering source + controls row demoted.  */}
      {/* Source paragraph is now collapsible (default closed); the   */}
      {/* replay toggle and Generate-explanation button stay visible  */}
      {/* but read as quieter secondary controls.                     */}
      <AdvancedDetails label="Where this data comes from">
        <p className="u-caption-2 text-fg-3 max-w-3xl">
          Source: <code>paper_equity_snapshot.positions_value</code>.
          We never recompute the mark off nullable selector-path
          fields, and we never substitute zero when a current price
          is missing.
        </p>
      </AdvancedDetails>
      <div className="flex flex-wrap items-center justify-end gap-3">
        <label className="flex items-center gap-2 u-caption-2 cursor-pointer">
          <input
            type="checkbox"
            checked={includeReplay}
            onChange={e => setIncludeReplay(e.target.checked)}
          />
          <span>Show recovered history</span>
        </label>
        <button
          type="button"
          onClick={handleNarrative}
          disabled={!q.data}
          data-test="risk-dashboard-narrative-btn"
          className="rounded border border-zinc-700 px-2 py-1 text-[11px] text-zinc-300 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Generate explanation
        </button>
      </div>

      {q.isLoading && (
        <div className="u-card-tight">
          <p className="u-caption italic">Loading risk dashboard…</p>
        </div>
      )}
      {q.error && (
        <div className="u-card-tight">
          <p className="u-caption text-danger">
            Risk dashboard unreachable. This page is read-only —
            execution is unaffected.
          </p>
        </div>
      )}
      {q.data && <Body data={q.data} />}
      <InsightDrawer
        open={drawerOpen}
        kind="risk_commentary"
        subjectLabel={
          q.data
            ? `NAV ${q.data.nav != null ? fmtUSD(q.data.nav) : "—"} · ${
                q.data.open_positions_count ?? 0
              } open`
            : undefined
        }
        status={insight.status}
        data={insight.data}
        error={insight.error}
        onClose={handleCloseDrawer}
      />
    </div>
  );
}


// UX-1 Commit G — derive a single calm interpretation sentence
// from the existing risk-dashboard payload. NO new hook, NO
// auto-fetch. Order: mark unavailable > drawdown >5% > exposure
// fully invested > exposure mostly cash > otherwise. Keeps every
// number truthful — interpretation only adds context, never
// substitutes a value.
function deriveRiskCalmState(
  data: NonNullable<ReturnType<typeof useRiskDashboard>["data"]>,
): {
  tone: "healthy" | "neutral" | "caution";
  headline: string;
  body: string;
} {
  const exposurePct = data.exposure_pct ?? null;
  const drawdownPct = data.max_drawdown_pct ?? null;
  if (data.mark_unavailable) {
    return {
      tone: "caution",
      headline: "A current price is missing.",
      body:
        "One or more open positions don't have a fresh price right "
        + "now. We never substitute a fake zero — exposure is shown "
        + "as 'Current price not available' until the next update. "
        + "Nothing requires action.",
    };
  }
  if (drawdownPct != null && drawdownPct < -0.10) {
    return {
      tone: "caution",
      headline: "Drawdown is larger than usual.",
      body:
        "The account has fallen more than 10% from a previous high. "
        + "Temporary declines are normal, but a deeper drop is worth "
        + "a closer look at the largest holdings below.",
    };
  }
  if (drawdownPct != null && drawdownPct < -0.05) {
    return {
      tone: "neutral",
      headline: "Account has drawn down from its high.",
      body:
        "This is expected to fluctuate over time. No action is "
        + "needed — the system continues to adjust exposure as "
        + "paper trades open and close.",
    };
  }
  if (exposurePct != null && exposurePct >= 0.95) {
    return {
      tone: "neutral",
      headline: "Most of the paper account is currently invested.",
      body:
        "This is normal during active trading periods. The system "
        + "will reduce exposure naturally as positions close. "
        + "Nothing requires action.",
    };
  }
  if (exposurePct != null && exposurePct < 0.30) {
    return {
      tone: "neutral",
      headline: "Most of the paper account is in cash right now.",
      body:
        "The system is being selective about new entries. This is "
        + "normal during quieter periods. No action is needed.",
    };
  }
  return {
    tone: "healthy",
    headline: "Account risk looks normal.",
    body:
      "Exposure and drawdown are both within their usual range. "
      + "The system continues to adjust positions as paper trades "
      + "open and close. No action is needed.",
  };
}


function Body({
  data,
}: { data: NonNullable<ReturnType<typeof useRiskDashboard>["data"]> }) {
  const calm = deriveRiskCalmState(data);
  const calmChipCls = calm.tone === "caution"
    ? "u-chip u-chip-warning"
    : calm.tone === "healthy"
      ? "u-chip u-chip-success"
      : "u-chip u-chip-neutral";
  const calmDotCls = calm.tone === "caution"
    ? "u-dot u-dot-warning"
    : calm.tone === "healthy"
      ? "u-dot u-dot-success"
      : "u-dot u-dot-neutral";
  return (
    <>
      {/* UX-1 Commit G — single calm interpretation sentence at    */}
      {/* the top of the body. Answers "should I worry?" /          */}
      {/* "what happens next?" before any number is shown.          */}
      <section
        className="u-card-tight"
        data-test="risk-calm-state"
        style={{ padding: "14px 18px" }}
      >
        <div className="flex items-center gap-3 mb-1">
          <span className={calmChipCls}>
            <span className={calmDotCls} />
            {calm.tone === "caution"
              ? "Worth a closer look"
              : calm.tone === "healthy"
                ? "Normal"
                : "Within normal range"}
          </span>
          <span
            className="u-body font-semibold text-fg"
            data-test="risk-calm-headline"
          >
            {calm.headline}
          </span>
        </div>
        <p
          className="u-caption text-fg-2 max-w-3xl"
          data-test="risk-calm-body"
        >
          {calm.body}
        </p>
      </section>

      {/* UX-1 Commit N — quiet section anchor introducing the    */}
      {/* numeric posture group (headline strip + P&L strip).      */}
      <div
        data-test="risk-section-anchor-posture"
        className="u-caption-2 text-fg-3 uppercase tracking-wide pt-2"
      >
        Current risk posture
      </div>

      {/* Top strip: account value / cash / money invested / drop */}
      {/* Commit 4 (Novice UX) — labels/sub-text in plain English. */}
      <section
        className="grid grid-cols-2 md:grid-cols-4 gap-3"
        data-test="risk-headline-strip"
      >
        <Cell
          label="Account value"
          value={data.nav != null ? fmtUSD(data.nav) : "—"}
          sub={data.snapshot_date
            ? `As of ${data.snapshot_date.slice(0, 10)}`
            : "No snapshot yet"}
        />
        <Cell
          label="Available cash"
          value={data.cash != null ? fmtUSD(data.cash) : "—"}
          sub={(data.cash != null && data.nav)
            ? `${((data.cash / data.nav) * 100).toFixed(1)}% of account value`
            : "—"}
        />
        <Cell
          label="Money invested"
          value={data.mark_unavailable
            ? "Current price not available"
            : (data.exposure_value != null
                ? fmtUSD(data.exposure_value)
                : "—")}
          sub={data.mark_unavailable
            ? `${data.open_positions_count} open · `
              + `waiting for fresh price data`
            : (data.exposure_pct != null
                ? `${(data.exposure_pct * 100).toFixed(1)}% invested · `
                  + `${data.open_positions_count} open`
                : `${data.open_positions_count} open`)}
          warn={data.mark_unavailable}
        />
        <Cell
          label="Biggest drop from peak"
          value={data.max_drawdown_pct != null
            ? fmtPct(data.max_drawdown_pct)
            : "—"}
          tone={data.max_drawdown_pct != null
            && data.max_drawdown_pct < 0
            ? "neg"
            : "neutral"}
          sub="From daily account snapshots"
        />
      </section>

      {/* PnL strip — plain-English labels.                         */}
      <section
        className="grid grid-cols-2 md:grid-cols-4 gap-3"
        data-test="risk-pnl-strip"
      >
        <Cell
          label="Profit/loss if you closed now"
          value={data.unrealized_pnl != null
            ? fmtUSD(data.unrealized_pnl) : "—"}
          tone={toneForNumber(data.unrealized_pnl ?? 0)}
          sub="Open positions, marked at the latest price"
        />
        <Cell
          label="Profit/loss from closed trades"
          value={data.realized_pnl_total != null
            ? fmtUSD(data.realized_pnl_total) : "—"}
          tone={toneForNumber(data.realized_pnl_total ?? 0)}
          sub="Across every closed sell so far"
        />
        <Cell
          label="Trades waiting for next price"
          value={String(data.pending_next_bar_count)}
          sub={data.pending_next_bar_note
            ?? "Held by the next-bar fill rule (intentional)"}
          warn={data.pending_next_bar_count > 0}
        />
        <Cell
          label="Current vs recovered history"
          value={`${data.live_trades_count} / ${data.replay_trades_count}`}
          sub={data.include_replay
            ? "Recovered history included in totals above"
            : "Recovered history excluded from totals above"}
        />
      </section>

      {/* UX-1 Commit N — quiet section anchor introducing the    */}
      {/* concentration group.                                      */}
      <div
        data-test="risk-section-anchor-concentration"
        className="u-caption-2 text-fg-3 uppercase tracking-wide pt-2"
      >
        Concentration
      </div>

      {/* Concentration tables — plain-English titles. Source     */}
      {/* attribution preserved for transparency.                  */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Card title="Largest holdings"
              source="concentration_by_symbol[:5]">
          <SymbolTable rows={data.top_5_notional} />
        </Card>

        <Card title="By portfolio"
              source="concentration_by_portfolio">
          <PortfolioTable rows={data.concentration_by_portfolio} />
        </Card>
      </section>

      {/* UX-1 Commit G — advanced tables collapsed under one      */}
      {/* progressive-disclosure block so the page presents a      */}
      {/* simple primary surface above the fold and only reveals   */}
      {/* deeper detail when the operator asks for it.             */}
      {(data.concentration_by_symbol.length > 5
        || (data.portfolios && data.portfolios.length > 0)) && (
        <AdvancedDetails label="Advanced detail (full breakdowns)">
          <div className="space-y-5 mt-1">
            {data.concentration_by_symbol.length > 5 && (
              <Card title="All symbols (full breakdown)"
                    source="concentration_by_symbol">
                <SymbolTable rows={data.concentration_by_symbol} />
              </Card>
            )}
            <Card title="Portfolios" source="paper_equity_snapshot">
              <PortfolioSnapshotTable rows={data.portfolios} />
            </Card>
          </div>
        </AdvancedDetails>
      )}

      <p className="u-caption-2 mt-1">
        {data.notice}
      </p>
    </>
  );
}


function Cell({
  label, value, sub, tone = "neutral", warn = false,
}: {
  label: string; value: string; sub?: string;
  tone?: "pos" | "neg" | "neutral";
  warn?: boolean;
}) {
  const cls = warn
    ? "text-warning"
    : tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger" : "text-fg";
  return (
    <div className="u-card-tight">
      <div className="u-caption-2 text-fg-3">{label}</div>
      <div className={cn("u-mono-md font-semibold mt-0.5", cls)}>
        {value}
      </div>
      {sub && (
        <div className="u-caption-2 text-fg-3 mt-1">{sub}</div>
      )}
    </div>
  );
}


function Card({
  title, source, children,
}: {
  title: string; source: string; children: React.ReactNode;
}) {
  return (
    <section className="u-card">
      <header className="mb-3">
        <h2 className="u-label">{title}</h2>
        <div className="u-caption-2 text-fg-3 mt-0.5">
          source: <code>{source}</code>
        </div>
      </header>
      {children}
    </section>
  );
}


function SymbolTable({ rows }: { rows: ConcentrationSymbolRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="u-caption italic">No open positions.</p>
    );
  }
  return (
    <div className="u-table-wrap"><table className="u-table">
      <thead>
        <tr>
          <th>Symbol</th>
          <th className="text-right">N open</th>
          <th className="text-right">Qty</th>
          <th className="text-right">Notional</th>
          <th className="text-right">Unrealized</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.symbol}>
            <td className="u-mono">{r.symbol}</td>
            <td className="text-right u-mono">{r.n_open}</td>
            <td className="text-right u-mono">
              {r.total_qty != null ? r.total_qty.toFixed(4) : "—"}
            </td>
            <td className={cn(
              "text-right u-mono",
              r.mark_unavailable ? "text-warning" : "",
            )}>
              {r.notional_usd != null ? fmtUSD(r.notional_usd) : "—"}
              {r.mark_unavailable && (
                <span className="ml-1 u-caption-2">
                  (cost basis)
                </span>
              )}
            </td>
            <td className={cn(
              "text-right u-mono",
              toneForNumber(r.unrealized_pnl ?? 0) === "pos"
                ? "text-success"
                : toneForNumber(r.unrealized_pnl ?? 0) === "neg"
                ? "text-danger" : "text-fg",
            )}>
              {r.unrealized_pnl != null
                ? fmtUSD(r.unrealized_pnl) : "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table></div>
  );
}


function PortfolioTable({
  rows,
}: { rows: ConcentrationPortfolioRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="u-caption italic">No active portfolios.</p>
    );
  }
  return (
    <div className="u-table-wrap"><table className="u-table">
      <thead>
        <tr>
          <th>Portfolio</th>
          <th className="text-right">N open</th>
          <th className="text-right">Notional</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.portfolio_id}>
            <td>{r.portfolio_name}</td>
            <td className="text-right u-mono">{r.n_open}</td>
            <td className="text-right u-mono">
              {r.notional_usd != null
                ? fmtUSD(r.notional_usd) : "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table></div>
  );
}


function PortfolioSnapshotTable({
  rows,
}: {
  rows: NonNullable<
    ReturnType<typeof useRiskDashboard>["data"]
  >["portfolios"];
}) {
  if (rows.length === 0) {
    return (
      <p className="u-caption italic">No active portfolios.</p>
    );
  }
  return (
    <div className="u-table-wrap"><table className="u-table">
      <thead>
        <tr>
          <th>Portfolio</th>
          <th>As of</th>
          <th className="text-right">NAV</th>
          <th className="text-right">Cash</th>
          <th className="text-right">Positions</th>
          <th className="text-right">Unrealized</th>
          <th className="text-right">Realized cum.</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.portfolio_id}>
            <td>{r.portfolio_name}</td>
            <td className="u-caption-2">
              {r.snapshot_date.slice(0, 10)}
            </td>
            <td className="text-right u-mono">
              {r.nav != null ? fmtUSD(r.nav) : "—"}
            </td>
            <td className="text-right u-mono">
              {r.cash != null ? fmtUSD(r.cash) : "—"}
            </td>
            <td className="text-right u-mono">
              {r.positions_value != null
                ? fmtUSD(r.positions_value) : "—"}
            </td>
            <td className={cn(
              "text-right u-mono",
              toneForNumber(r.unrealized_pnl ?? 0) === "pos"
                ? "text-success"
                : toneForNumber(r.unrealized_pnl ?? 0) === "neg"
                ? "text-danger" : "text-fg",
            )}>
              {r.unrealized_pnl != null
                ? fmtUSD(r.unrealized_pnl) : "—"}
            </td>
            <td className={cn(
              "text-right u-mono",
              toneForNumber(r.realized_pnl_cumulative ?? 0) === "pos"
                ? "text-success"
                : toneForNumber(r.realized_pnl_cumulative ?? 0) === "neg"
                ? "text-danger" : "text-fg",
            )}>
              {r.realized_pnl_cumulative != null
                ? fmtUSD(r.realized_pnl_cumulative) : "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table></div>
  );
}
