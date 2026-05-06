// Alpha Lab Pro — open + closed trade intelligence dashboard.
//
// Five tabs:
//   1. Overview          summary cards + best/worst open
//   2. Open Winners      paper_position joined to latest price_bar
//   3. Open Losers       same, sorted worst-first
//   4. Closed Outcomes   closed paper_trade rows
//   5. Patterns          age-bucket / portfolio / concentration cuts
//
// Read-only. Wires to /api/performance/paper/alpha-lab.

import { useMemo, useState } from "react";
import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import {
  useAlphaLab,
  type AlphaLabPosition,
  type AlphaLabClosedTrade,
} from "@/lib/alphaLab/hooks";
import TradeQualityCard from "@/components/alpha-lab/TradeQualityCard";


const TABS = [
  "overview",
  "open_winners",
  "open_losers",
  "closed",
  "patterns",
] as const;
type Tab = typeof TABS[number];


export default function AlphaLab() {
  const [tab, setTab] = useState<Tab>("overview");
  const q = useAlphaLab(25);

  if (q.isLoading) {
    return <Wrap title="Alpha Lab"><Loading /></Wrap>;
  }
  if (q.error || !q.data) {
    return <Wrap title="Alpha Lab"><ErrorBanner /></Wrap>;
  }
  const d = q.data;

  return (
    <Wrap title="Alpha Lab">
      <TabBar tab={tab} setTab={setTab} d={d} />
      {tab === "overview" && <Overview d={d} />}
      {tab === "open_winners" && (
        <OpenTable rows={d.open_winners} kind="winners" />
      )}
      {tab === "open_losers" && (
        <OpenTable rows={d.open_losers} kind="losers" />
      )}
      {tab === "closed" && <ClosedSection d={d} />}
      {tab === "patterns" && <PatternsSection d={d} />}
    </Wrap>
  );
}


// ---------------------------------------------------------------
// Layout primitives
// ---------------------------------------------------------------

function Wrap({ title, children }: {
  title: string; children: React.ReactNode;
}) {
  return (
    <div className="max-w-[1520px] mx-auto px-6 py-6 space-y-5">
      <header>
        <Label>{title}</Label>
        <h1 className="u-title-lg mt-1">
          Open + Closed Trade Intelligence
        </h1>
        <p className="u-body mt-2 max-w-3xl">
          Real paper-trading state from{" "}
          <code>paper_position</code>, <code>paper_trade</code>,
          and <code>paper_equity_snapshot</code>. Unrealized P&L
          marked from the latest <code>price_bar</code>.
          Closed-trade analytics activate after the exit-cycle
          runner closes eligible positions.
        </p>
      </header>
      {children}
    </div>
  );
}


type DType = NonNullable<ReturnType<typeof useAlphaLab>["data"]>;


function TabBar({ tab, setTab, d }: {
  tab: Tab; setTab: (t: Tab) => void; d: DType;
}) {
  const counts: Record<Tab, number> = {
    overview: 1,
    open_winners: d.open_winners.length,
    open_losers: d.open_losers.length,
    closed: d.closed_winners.length + d.closed_losers.length,
    patterns: d.patterns.by_age_bucket.length,
  };
  const labels: Record<Tab, string> = {
    overview: "Overview",
    open_winners: "Open Winners",
    open_losers: "Open Losers",
    closed: "Closed Outcomes",
    patterns: "Patterns",
  };
  return (
    <div className="flex gap-1 border-b border-zinc-800 text-sm">
      {TABS.map((t) => (
        <button
          key={t}
          data-test={`alpha-tab-${t}`}
          onClick={() => setTab(t)}
          className={cn(
            "px-4 py-2 transition-colors",
            tab === t
              ? "border-b-2 border-amber-400 text-zinc-100"
              : "text-zinc-400 hover:text-zinc-200",
          )}
        >
          <span>{labels[t]}</span>
          {t !== "overview" && (
            <span className="ml-2 text-xs text-zinc-500">
              {counts[t]}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}


// ---------------------------------------------------------------
// Overview tab
// ---------------------------------------------------------------

function Overview({ d }: { d: DType }) {
  const s = d.summary;
  const bestOpen = d.open_winners[0];
  const worstOpen = d.open_losers[0];
  return (
    <section className="space-y-4" data-test="alpha-overview">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <SummaryCard
          label="Open positions" value={String(s.open_positions)}
        />
        <SummaryCard
          label="Closed positions"
          value={String(s.closed_positions)}
        />
        <SummaryCard
          label="Open unrealized P&L"
          value={fmtUSD(s.open_unrealized_pnl)}
          tone={toneFromN(s.open_unrealized_pnl)}
        />
        <SummaryCard
          label="Closed realized P&L"
          value={fmtUSD(s.closed_realized_pnl)}
          tone={toneFromN(s.closed_realized_pnl)}
        />
        <SummaryCard
          label="Pending fills" value={String(s.pending_fills)}
        />
        <SummaryCard
          label="Live trades" value={String(s.live_trades)}
        />
        <SummaryCard
          label="Replay trades" value={String(s.replay_trades)}
        />
        <SummaryCard label="As of" value={s.as_of_date} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="u-card-tight">
          <Label>Best open winner</Label>
          {bestOpen ? <PositionLine row={bestOpen} /> : <Empty />}
        </div>
        <div className="u-card-tight">
          <Label>Worst open loser</Label>
          {worstOpen ? <PositionLine row={worstOpen} /> : <Empty />}
        </div>
      </div>

      {/* Phase B — pre-ML diagnostic. Read-only. NOT a trading
          signal. Each row's "why" expands to per-component
          reasons sourced from real DB rows. */}
      <TradeQualityCard />
    </section>
  );
}


function SummaryCard({ label, value, tone = "neutral" }: {
  label: string; value: string; tone?: "neutral" | "pos" | "neg";
}) {
  return (
    <div className="u-card-tight">
      <div className="u-caption-2 text-fg-3">{label}</div>
      <div className={cn(
        "u-mono-md font-semibold",
        tone === "pos" ? "text-success"
        : tone === "neg" ? "text-danger"
        : "text-fg",
      )}>
        {value}
      </div>
    </div>
  );
}


function PositionLine({ row }: { row: AlphaLabPosition }) {
  const pct = row.unrealized_pnl_pct;
  const tone = toneFromN(pct ?? 0);
  return (
    <div className="flex items-baseline justify-between mt-1">
      <div className="u-mono">{row.symbol}</div>
      <div className="u-caption-2 text-fg-3">
        {row.portfolio_name} · {row.held_days ?? "?"}d
      </div>
      <div className={cn(
        "u-mono-sm font-semibold",
        tone === "pos" ? "text-success"
        : tone === "neg" ? "text-danger" : "text-fg",
      )}>
        {pct != null ? fmtPct(pct) : "—"}
      </div>
    </div>
  );
}


// ---------------------------------------------------------------
// Open tables
// ---------------------------------------------------------------

function OpenTable({ rows, kind }: {
  rows: AlphaLabPosition[]; kind: "winners" | "losers";
}) {
  if (!rows.length) {
    return (
      <div
        className="u-card-tight"
        data-test={`alpha-open-${kind}-empty`}
      >
        <p className="u-caption">
          No open {kind} right now. Positions appear here as
          soon as their unrealized P&L turns
          {kind === "winners" ? " positive." : " negative."}
        </p>
      </div>
    );
  }
  return (
    <table
      className="u-table"
      data-test={`alpha-open-${kind}`}
    >
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Portfolio</th>
          <th className="text-right">Entry</th>
          <th className="text-right">Last</th>
          <th className="text-right">Unrealized $</th>
          <th className="text-right">Unrealized %</th>
          <th className="text-right">Held</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.position_id}>
            <td className="u-mono">{r.symbol}</td>
            <td className="u-caption-2 text-fg-3">
              {r.portfolio_name}
            </td>
            <td className="text-right u-mono">
              {fmtUSD(r.entry_price)}
            </td>
            <td className="text-right u-mono">
              {r.last_price != null ? fmtUSD(r.last_price) : "—"}
            </td>
            <td className={cn(
              "text-right u-mono",
              toneFromN(r.unrealized_pnl ?? 0) === "pos"
                ? "text-success"
                : toneFromN(r.unrealized_pnl ?? 0) === "neg"
                ? "text-danger" : "text-fg",
            )}>
              {r.unrealized_pnl != null
                ? fmtUSD(r.unrealized_pnl) : "—"}
            </td>
            <td className={cn(
              "text-right u-mono font-semibold",
              toneFromN(r.unrealized_pnl_pct ?? 0) === "pos"
                ? "text-success"
                : toneFromN(r.unrealized_pnl_pct ?? 0) === "neg"
                ? "text-danger" : "text-fg",
            )}>
              {r.unrealized_pnl_pct != null
                ? fmtPct(r.unrealized_pnl_pct) : "—"}
            </td>
            <td className="text-right u-caption-2 text-fg-3">
              {r.held_days != null ? `${r.held_days}d` : "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}


// ---------------------------------------------------------------
// Closed tab
// ---------------------------------------------------------------

function ClosedSection({ d }: { d: DType }) {
  const total = d.closed_winners.length + d.closed_losers.length;
  if (!total) {
    return (
      <div
        className="u-card-tight"
        data-test="alpha-closed-empty"
      >
        <p className="u-caption">
          Closed outcomes will appear after exit rules close
          positions. Open trade performance is available in the
          Open Winners / Open Losers tabs.
        </p>
        <p className="u-caption-2 text-fg-3 mt-1">
          Operator can trigger exits via{" "}
          <code>scripts.run_paper_exit_cycle</code>.
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-4" data-test="alpha-closed">
      <ClosedTable rows={d.closed_winners} kind="winners" />
      <ClosedTable rows={d.closed_losers} kind="losers" />
      <ExitReasonBreakdown
        rows={[...d.closed_winners, ...d.closed_losers]}
      />
    </div>
  );
}


function ClosedTable({ rows, kind }: {
  rows: AlphaLabClosedTrade[]; kind: "winners" | "losers";
}) {
  if (!rows.length) return null;
  return (
    <div>
      <Label>Top closed {kind}</Label>
      <table
        className="u-table mt-2"
        data-test={`alpha-closed-${kind}`}
      >
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Portfolio</th>
            <th className="text-right">Qty</th>
            <th className="text-right">Exit</th>
            <th className="text-right">Realized $</th>
            <th>Reason</th>
            <th>Tag</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.trade_id}>
              <td className="u-mono">{r.symbol}</td>
              <td className="u-caption-2 text-fg-3">
                {r.portfolio_name}
              </td>
              <td className="text-right u-mono">{r.quantity}</td>
              <td className="text-right u-mono">
                {fmtUSD(r.exit_price)}
              </td>
              <td className={cn(
                "text-right u-mono font-semibold",
                r.realized_pnl > 0
                  ? "text-success"
                  : r.realized_pnl < 0
                  ? "text-danger" : "text-fg",
              )}>
                {fmtUSD(r.realized_pnl)}
              </td>
              <td className="u-caption-2 text-fg-3">
                {r.reason ?? "—"}
              </td>
              <td>
                <span className={cn(
                  "u-chip",
                  r.is_replay
                    ? "u-chip-warning"
                    : "u-chip-success",
                )}>
                  {r.is_replay ? "REPLAY" : "LIVE"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


function ExitReasonBreakdown({ rows }: {
  rows: AlphaLabClosedTrade[];
}) {
  const counts = useMemo(() => {
    const m: Record<string, { n: number; pnl: number }> = {};
    for (const r of rows) {
      const reason = (r.reason ?? "—")
        .split(":")[0].trim()
        .replace("exit_cycle", "exit")
        .replace("auto_trader", "auto");
      m[reason] = m[reason] ?? { n: 0, pnl: 0 };
      m[reason].n += 1;
      m[reason].pnl += r.realized_pnl;
    }
    return Object.entries(m)
      .map(([reason, v]) => ({ reason, n: v.n, pnl: v.pnl }))
      .sort((a, b) => b.n - a.n);
  }, [rows]);
  if (!counts.length) return null;
  return (
    <div>
      <Label>Exit reason breakdown</Label>
      <table
        className="u-table mt-2"
        data-test="alpha-exit-reason"
      >
        <thead>
          <tr><th>Reason</th>
              <th className="text-right">Count</th>
              <th className="text-right">Net P&L</th></tr>
        </thead>
        <tbody>
          {counts.map(c => (
            <tr key={c.reason}>
              <td>{c.reason}</td>
              <td className="text-right u-mono">{c.n}</td>
              <td className={cn(
                "text-right u-mono",
                c.pnl > 0 ? "text-success"
                : c.pnl < 0 ? "text-danger" : "text-fg",
              )}>
                {fmtUSD(c.pnl)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


// ---------------------------------------------------------------
// Patterns
// ---------------------------------------------------------------

function PatternsSection({ d }: { d: DType }) {
  if (!d.patterns.by_age_bucket.length
      && !d.patterns.by_portfolio.length) {
    return (
      <div
        className="u-card-tight"
        data-test="alpha-patterns-empty"
      >
        <p>No open positions yet — patterns will appear here.</p>
      </div>
    );
  }
  const closedTotal = (
    d.closed_winners.length + d.closed_losers.length
  );
  return (
    <div className="space-y-4" data-test="alpha-patterns">
      {!closedTotal && (
        <div className="u-caption-2 text-fg-3 italic">
          Closed-trade patterns pending; showing open-position
          patterns instead.
        </div>
      )}

      <div>
        <Label>Open P&L by holding-age bucket</Label>
        <table className="u-table mt-2">
          <thead>
            <tr><th>Bucket</th>
                <th className="text-right">N open</th>
                <th className="text-right">Avg unrealized %</th>
            </tr>
          </thead>
          <tbody>
            {d.patterns.by_age_bucket
              .slice()
              .sort((a, b) => a.bucket.localeCompare(b.bucket))
              .map(b => (
                <tr key={b.bucket}>
                  <td>{b.bucket}</td>
                  <td className="text-right u-mono">{b.n}</td>
                  <td className={cn(
                    "text-right u-mono",
                    toneFromN(b.avg_upnl_pct) === "pos"
                      ? "text-success"
                      : toneFromN(b.avg_upnl_pct) === "neg"
                      ? "text-danger" : "text-fg",
                  )}>{fmtPct(b.avg_upnl_pct)}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      <div>
        <Label>Open P&L by portfolio</Label>
        <table className="u-table mt-2">
          <thead>
            <tr><th>Portfolio</th>
                <th className="text-right">N open</th>
                <th className="text-right">Sum unrealized $</th>
            </tr>
          </thead>
          <tbody>
            {d.patterns.by_portfolio.map(p => (
              <tr key={p.portfolio}>
                <td>{p.portfolio}</td>
                <td className="text-right u-mono">{p.n_open}</td>
                <td className={cn(
                  "text-right u-mono",
                  toneFromN(p.sum_unrealized) === "pos"
                    ? "text-success"
                    : toneFromN(p.sum_unrealized) === "neg"
                    ? "text-danger" : "text-fg",
                )}>{fmtUSD(p.sum_unrealized)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div>
        <Label>Concentration (top symbols by notional)</Label>
        <table className="u-table mt-2">
          <thead>
            <tr><th>Symbol</th>
                <th className="text-right">N positions</th>
                <th className="text-right">Total notional $</th>
            </tr>
          </thead>
          <tbody>
            {d.patterns.concentration.map(c => (
              <tr key={c.symbol}>
                <td className="u-mono">{c.symbol}</td>
                <td className="text-right u-mono">{c.n_open}</td>
                <td className="text-right u-mono">
                  {fmtUSD(c.total_notional)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------

function Loading() {
  return (
    <div className="u-card-tight" data-test="alpha-loading">
      <p className="u-caption">Loading…</p>
    </div>
  );
}


function ErrorBanner() {
  return (
    <div className="u-card-tight" data-test="alpha-error">
      <p className="u-caption text-danger">
        Alpha Lab data unavailable.
      </p>
    </div>
  );
}


function Empty() {
  return (
    <p className="u-caption-2 text-fg-3 italic mt-1">
      No data.
    </p>
  );
}


function fmtUSD(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const abs = Math.abs(n);
  const s = n < 0 ? "-" : "";
  return `${s}$${abs.toFixed(abs >= 1000 ? 0 : 2)}`;
}


function fmtPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(2)}%`;
}


function toneFromN(n: number): "pos" | "neg" | "neutral" {
  if (n > 0) return "pos";
  if (n < 0) return "neg";
  return "neutral";
}
