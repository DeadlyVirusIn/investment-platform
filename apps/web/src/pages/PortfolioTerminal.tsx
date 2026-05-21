// PORTFOLIO — trading terminal. Data-first with meaningful fallbacks.
//
// Phase 11Z: this page surfaces TWO independent paper-trading
// streams:
//   * Executed trades + open positions (paper_trade + paper_position)
//     — read via the new /paper/executed/* endpoints. After the
//     2026-05-02 wipe + replay, these are the trades the user
//     actually wants to see.
//   * Strategy logs (paper_trade_log) — selector path. May be empty
//     even when executed trades exist; rendered separately so an
//     empty strategy log does NOT make the page look "0 trades".

import { useState } from "react";
import {
  usePaperSummary, usePaperTrades, usePerformance, useCurrentState,
  usePaperEquity, useExecutedSummary, useExecutedTrades,
  useExecutedPositions,
} from "@/lib/operator/hooks";
import {
  fmtUSD, fmtPct, toneForNumber,
} from "@/components/ui/primitives";
// Accounting truth primitive — locked terminology + identity-safe
// rendering. Trust-infrastructure: single source for portfolio numerics.
import AccountingStrip from "@/components/portfolio/AccountingStrip";
import EquityDrawdownChart from "@/components/operator/EquityDrawdownChart";
import Sparkline from "@/components/ui/Sparkline";
import { cn } from "@/lib/cn";
import type {
  PaperSummary, EquityPoint,
} from "@/lib/operator/types";
// Commit 3 (Novice UX) — page-level intro card.
// UX-1 Commit H — focus guidance + emotional interpretation.
import { PageGuide, AdvancedDetails } from "@/components/novice";

export default function PortfolioTerminal() {
  const { data: summary } = usePaperSummary();
  const { data: trades } = usePaperTrades();
  const { data: perf } = usePerformance();
  const { data: state } = useCurrentState();
  const { data: equityHistory } = usePaperEquity();

  // Phase 11Z — toggle to include replay-recovered rows (default off
  // so live-only stays the headline; the toggle becomes visible only
  // when the manifest reports recovered rows exist).
  const [includeReplay, setIncludeReplay] = useState(false);
  const { data: execSummary } = useExecutedSummary(includeReplay);
  const { data: execTradesResp } = useExecutedTrades(includeReplay);
  const { data: execPositionsResp } = useExecutedPositions(
    includeReplay, true,
  );
  const executedTrades = execTradesResp?.trades ?? [];
  const openExecPositions = execPositionsResp?.positions ?? [];

  const equitySeries = (equityHistory ?? []).map(p => p.equity);
  const returnSeries = (equityHistory ?? []).map(p => p.cum_pct);
  const drawdownSeries = (() => {
    if (!equityHistory || equityHistory.length < 2) return [] as number[];
    let peak = equityHistory[0].equity;
    return equityHistory.map(p => {
      peak = Math.max(peak, p.equity);
      return ((p.equity - peak) / peak) * 100;
    });
  })();

  // Strategy-log derived (selector path) — kept for the dedicated
  // strategy-log card; NOT used for headline counts.
  const open = (trades ?? []).filter(t => t.status === "open");
  const closed = (trades ?? []).filter(t => t.status === "closed");

  // Exposure — mark-to-market value of open paper positions, sourced
  // from /paper/summary.positions_value (computed server-side off
  // paper_equity_snapshot which marks paper_position to the latest
  // price_bar). Falls back to summing open trade notional_usd
  // (cost basis) if positions_value is unavailable; never derives
  // from selector-path position_size_pct, which is null for the
  // recommendation/account path.
  const markUnavailable =
    summary != null && (summary.positions_value == null
                        || Number.isNaN(summary.positions_value));
  const exposureFromSummary = summary?.positions_value ?? null;
  const exposureFromNotional = (trades ?? [])
    .filter(t => t.status === "open" && t.notional_usd != null)
    .reduce((s, t) => s + Math.abs(t.notional_usd ?? 0), 0);
  const exposure = exposureFromSummary != null
    ? exposureFromSummary
    : exposureFromNotional;
  const openPositionsCount = summary?.open_positions_count
    ?? openExecPositions.length;

  // UX-1 Commit H — single calm interpretation sentence at top of
  // body. Derives a tone + headline + body from data already on
  // the page — no new hook, no auto-fetch. Light temporal framing
  // uses the last two equity points when present. Order matters:
  // markUnavailable > losing today + unrealized < 0 > unrealized
  // > 0 + up today > unrealized > 0 > unrealized < 0 > flat.
  const calm = derivePortfolioCalm({
    summary, markUnavailable, openPositionsCount,
    equityHistory: equityHistory ?? [],
  });

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-8 space-y-6">
      {/* Commit 3 (Novice UX) — plain-English page intro. The body */}
      {/* below shows two streams (account-path trades + selector   */}
      {/* strategy logs). Truth labels preserved.                    */}
      <PageGuide
        eyebrow="Paper Account"
        title="My Holdings"
        subtitle={
          "Every position you currently hold and every paper trade "
          + "the system has placed. All numbers are simulated — no "
          + "real money is involved."
        }
        firstLook={
          <>
            Top row shows your account at a glance. Open holdings are
            below the chart; trade history is below that.
          </>
        }
      />

      {/* UX-1 Commit H — Start-here focus card. Tells the operator  */}
      {/* what matters first and what they can defer.                */}
      <section
        className="u-card-tight"
        data-test="portfolio-start-here"
        style={{ padding: "12px 16px" }}
      >
        <div className="u-caption-2 text-fg-3 uppercase tracking-wide mb-1">
          Focus today
        </div>
        <ol className="u-body text-fg space-y-1 list-decimal pl-5">
          <li>
            <strong>Account value</strong> — total worth of your
            paper account today.
          </li>
          <li>
            <strong>Holdings (still open)</strong> — what the system
            is currently holding for you.
          </li>
          <li>
            <strong>If closed now</strong> — what the open holdings
            would be worth if every trade closed at today's price.
          </li>
        </ol>
        <p className="u-caption-2 text-fg-3 mt-2">
          Safe to ignore for now: strategy-log internals, engine
          attribution, and the closed-trade engineering breakdown
          further down. They're collapsed under "Advanced strategy
          detail" — none require action.
        </p>
      </section>
      <div className="u-caption-2 text-fg-3 -mt-2">
        {execSummary?.live_trades_count ?? 0} paper trades placed ·
        {" "}{execSummary?.live_open_positions_count ?? 0} open paper positions ·
        {" "}{state?.as_of_date ?? "idle"}
      </div>
      {execSummary?.has_replay_recovered_rows && (
        <div
          className="u-card-tight flex items-center justify-between"
          style={{ background: "var(--sunken)", padding: "8px 12px" }}
        >
          <div className="u-caption">
            <span className="u-chip u-chip-warning mr-2">
              Recovered history
            </span>
            <strong>{execSummary?.replay_trades_count ?? 0}</strong>{" "}
            recovered trades ·{" "}
            <strong>{execSummary?.replay_open_positions_count ?? 0}</strong>{" "}
            recovered open positions
            {summary?.replay_positions_market_value != null
             && summary.replay_positions_market_value > 0
              ? <>
                  {" "}contributing{" "}
                  <strong>
                    {fmtUSD(summary.replay_positions_market_value)}
                  </strong>{" "}
                  to account value
                </>
              : null}
            . Reconstructed from backup data after a 2026-05-02 reset
            and tagged in <code>replay_recovery_manifest</code>. They
            are NOT live trading activity and are hidden by default.
          </div>
          <label className="u-caption flex items-center gap-2">
            <input
              type="checkbox"
              checked={includeReplay}
              onChange={e => setIncludeReplay(e.target.checked)}
            />
            <span>Show recovered history</span>
          </label>
        </div>
      )}

      {/* UX-1 Commit H — calm interpretation card. Sits between    */}
      {/* the page intro and the strip so a beginner reads "is this */}
      {/* okay?" before they encounter five dollar values.          */}
      <section
        className="u-card-tight"
        data-test="portfolio-calm-state"
        style={{ padding: "14px 18px" }}
      >
        <div className="flex items-center gap-3 mb-1">
          <span className={`u-chip u-chip-${calm.chip}`}>
            <span className={`u-dot u-dot-${calm.chip}`} />
            {calm.tone}
          </span>
          <span
            className="u-body font-semibold text-fg"
            data-test="portfolio-calm-headline"
          >
            {calm.headline}
          </span>
        </div>
        <p
          className="u-caption text-fg-2 max-w-3xl"
          data-test="portfolio-calm-body"
        >
          {calm.body}
        </p>
      </section>

      {/* UX-1 Commit M — quiet section anchor between calm card    */}
      {/* and the numeric strip.                                     */}
      <div
        data-test="portfolio-section-anchor-numbers"
        className="u-caption-2 text-fg-3 uppercase tracking-wide pt-2"
      >
        Today's numbers
      </div>

      {/* HEADLINE + BREAKDOWN — canonical AccountingStrip primitive. */}
      {/* Single source of truth for accounting presentation. The     */}
      {/* underlying values are PaperSummary fields from              */}
      {/* /api/paper/summary; this component does no math.            */}
      <AccountingStrip
        data={{
          equity: summary?.equity ?? null,
          cash: summary?.cash ?? null,
          holdingsValue: markUnavailable ? null : exposure,
          costBasis: summary?.cost_basis ?? null,
          unrealizedPnl: summary?.unrealized_pnl ?? null,
          realizedPnl: summary?.realized_pnl_cumulative ?? null,
          totalReturnPct: summary?.total_return_pct ?? null,
          dailyPnl: summary?.daily_pnl ?? null,
          startingCapital: summary?.starting_capital_total ?? null,
          portfolioCount: summary?.portfolio_count ?? null,
          openPositionsCount,
          replayPositionsMarketValue:
            summary?.replay_positions_market_value ?? null,
          replayRealizedPnlCumulative:
            (summary as Record<string, unknown> | null)
              ?.replay_realized_pnl_cumulative as number | null
            ?? null,
          asOf: summary?.as_of_date ?? null,
        }}
        variant="full"
        equitySparkline={
          <Sparkline values={equitySeries}
                      ariaLabel="Account value history" />
        }
        returnSparkline={
          <Sparkline values={returnSeries}
                      ariaLabel="Total return history" />
        }
      />

      {/* Biggest drop from peak — kept as separate row so it does    */}
      {/* not compete with the truth grid above.                      */}
      <div className="u-card">
        <div className="grid grid-cols-1 md:grid-cols-1">
          <Strip label="Biggest drop from peak"
            value={fmtPct(summary?.max_drawdown_pct)}
            tone="neg"
            sub="Largest dip in account value"
            spark={
              <Sparkline values={drawdownSeries}
                          tone="neg"
                          ariaLabel="Drop-from-peak history" />
            } />
        </div>
      </div>

      {/* EQUITY */}
      <div className="u-card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="u-label">Equity Path</div>
            <div className="u-caption-2 mt-1">
              Cumulative NAV · drawdown overlay · multi-timeframe
            </div>
          </div>
        </div>
        <EquityDrawdownChart />
      </div>

      {/* UX-1 Commit M — quiet section anchor introduces the      */}
      {/* holdings + history pair.                                  */}
      <div
        data-test="portfolio-section-anchor-holdings"
        className="u-caption-2 text-fg-3 uppercase tracking-wide pt-2"
      >
        Holdings & trade history
      </div>

      {/* EXECUTED ACTIVITY (account/recommendation path) — Phase 11Z */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="u-card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="u-label">Holdings (still open)</div>
              <div className="u-caption-2 mt-1">
                {openExecPositions.length > 0
                  ? "Stocks you currently hold in your paper account"
                  : "No paper holdings yet"}
              </div>
            </div>
            <span className="u-pill u-pill-neutral">
              {openExecPositions.length} held
            </span>
          </div>
          {openExecPositions.length === 0 ? (
            <div className="u-card-tight"
                 style={{ background: "var(--sunken)" }}>
              <div className="u-body-fg font-medium mb-2">
                No open paper holdings
              </div>
              <div className="u-caption">
                {execSummary?.has_replay_recovered_rows
                  ? "Recovered history rows available — toggle 'Show recovered history' above to view them."
                  : "Nothing currently held. New holdings appear here once a paper trade fills."}
              </div>
            </div>
          ) : (
            <table className="u-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Portfolio</th>
                  <th className="text-right">Shares</th>
                  <th className="text-right">Average buy price</th>
                  <th>Bought on</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {openExecPositions.map(p => (
                  <tr key={p.position_id}>
                    <td className="u-mono">{p.symbol}</td>
                    <td className="u-caption-2">{p.portfolio_name}</td>
                    <td className="text-right u-mono">
                      {p.quantity?.toFixed(4) ?? "—"}
                    </td>
                    <td className="text-right u-mono">
                      {p.avg_cost?.toFixed(2) ?? "—"}
                    </td>
                    <td className="u-mono-sm">
                      {p.opened_at ? p.opened_at.slice(0, 10) : "—"}
                    </td>
                    <td>
                      {p.source === "replay" ? (
                        <span
                          className="u-chip u-chip-warning"
                          title="Recovered from backup data — not live trading activity."
                        >
                          recovered
                        </span>
                      ) : (
                        <span className="u-caption-2 text-fg-3">{p.source}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="u-card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="u-label">Trades placed (history)</div>
              <div className="u-caption-2 mt-1">
                {executedTrades.length > 0
                  ? "Buy and sell trades the system placed in your paper account"
                  : "No paper trades placed yet"}
              </div>
            </div>
            <span className="u-pill u-pill-neutral">
              {executedTrades.length} trades
            </span>
          </div>
          {executedTrades.length === 0 ? (
            <div className="u-card-tight"
                 style={{ background: "var(--sunken)" }}>
              <div className="u-body-fg font-medium mb-2">
                No paper trades placed yet
              </div>
              <div className="u-caption">
                {execSummary?.has_replay_recovered_rows
                  ? "Recovered history rows available — toggle 'Show recovered history' above to view them."
                  : "Buys and sells will appear here as they fill on the next price bar."}
              </div>
            </div>
          ) : (
            <table className="u-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Symbol</th>
                  <th>Trade type</th>
                  <th className="text-right">Shares</th>
                  <th className="text-right">Price</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {executedTrades.slice(0, 12).map(t => (
                  <tr key={t.trade_id}>
                    <td className="u-mono-sm">
                      {t.fill_ts ? t.fill_ts.slice(0, 10) : "—"}
                    </td>
                    <td className="u-mono">{t.symbol}</td>
                    <td className={cn("u-caption",
                      t.side === "buy" ? "text-success" : "text-danger")}>
                      {t.side}
                    </td>
                    <td className="text-right u-mono">
                      {t.quantity?.toFixed(4) ?? "—"}
                    </td>
                    <td className="text-right u-mono">
                      {t.fill_price?.toFixed(2) ?? "—"}
                    </td>
                    <td>
                      {t.source === "replay" ? (
                        <span
                          className="u-chip u-chip-warning"
                          title="Recovered from backup data — not live trading activity."
                        >
                          recovered
                        </span>
                      ) : (
                        <span className="u-caption-2 text-fg-3">{t.source}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* UX-1 Commit H — Advanced strategy detail block.            */}
      {/* Wraps the selector-path Strategy Logs + Realized History  */}
      {/* (Engine A / Engine B internals) and the Engine            */}
      {/* Attribution breakdown so the page presents a calm primary */}
      {/* surface above the fold and only reveals deeper detail     */}
      {/* when the operator asks for it.                            */}
      <AdvancedDetails label="Advanced strategy detail">
      {/* SELECTOR STRATEGY LOGS (Engine A/B path) — separate stream */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="u-card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="u-label">Strategy Logs (Engine A/B)</div>
              <div className="u-caption-2 mt-1">
                {open.length > 0
                  ? "Currently holding; marked-to-market daily"
                  : "Selector path — paper_trade_log"}
              </div>
            </div>
            <span className="u-pill u-pill-neutral">{open.length} active</span>
          </div>
          {open.length === 0 ? (
            <div className="u-card-tight"
                 style={{ background: "var(--sunken)" }}>
              <div className="u-body-fg font-medium mb-2">
                No strategy logs yet
              </div>
              <div className="u-caption">
                {state?.fire
                  ? "Pipeline just fired — selector log will appear on next refresh."
                  : state?.directional_regime
                    ? "Directional regime active — Engine B watching credit + rates alignment for next entry."
                    : state?.stress_regime
                      ? "Stress regime active — Engine A watching P15 conditions for next entry."
                      : "Both engines standing by. Next evaluation at end of trading day."}
              </div>
            </div>
          ) : (
            <table className="u-table">
              <thead>
                <tr>
                  <th>Engine</th>
                  <th>Symbol</th>
                  <th>Entry</th>
                  <th className="text-right">Size%</th>
                  <th className="text-right">Unrealized</th>
                </tr>
              </thead>
              <tbody>
                {open.map(t => (
                  <tr key={t.trade_id}>
                    <td>Engine {t.engine}</td>
                    <td className="u-mono">{t.instrument}</td>
                    <td className="u-mono-sm">{t.entry_date}</td>
                    <td className="text-right u-mono">
                      {t.position_size_pct != null
                        ? t.position_size_pct.toFixed(1)
                        : "—"}
                    </td>
                    <td className={cn("text-right u-mono",
                      toneForNumber(t.net_ret_pct ?? 0) === "pos" ? "text-success"
                      : toneForNumber(t.net_ret_pct ?? 0) === "neg" ? "text-danger"
                      : "text-fg-2")}>
                      {fmtPct(t.net_ret_pct)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="u-card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="u-label">Closed trades (history)</div>
              <div className="u-caption-2 mt-1">
                {closed.length > 0
                  ? "Most recent closed paper trades from the strategy log"
                  : "No closed trades yet"}
              </div>
            </div>
            <span className="u-pill u-pill-neutral">{closed.length} closed</span>
          </div>
          {closed.length === 0 ? (
            <div className="u-card-tight"
                 style={{ background: "var(--sunken)" }}>
              <div className="u-body-fg font-medium mb-2">
                No closed trades yet
              </div>
              <div className="u-caption">
                Trades close once the strategy hits its take-profit,
                stop-loss, or time-limit rule. Engine A holds for up
                to 10 trading days; Engine B holds for 1.
              </div>
            </div>
          ) : (
            <table className="u-table">
              <thead>
                <tr>
                  <th>Exit</th>
                  <th>Engine</th>
                  <th>Regime</th>
                  <th className="text-right">Net%</th>
                  <th className="text-right">Days</th>
                </tr>
              </thead>
              <tbody>
                {closed.slice(0, 10).map(t => (
                  <tr key={t.trade_id}>
                    <td className="u-mono-sm">{t.exit_date}</td>
                    <td>Engine {t.engine}</td>
                    <td className="u-caption-2 uppercase">{t.regime_at_entry}</td>
                    <td className={cn("text-right u-mono",
                      toneForNumber(t.net_ret_pct ?? 0) === "pos" ? "text-success"
                      : "text-danger")}>
                      {fmtPct(t.net_ret_pct)}
                    </td>
                    <td className="text-right text-fg-2">{t.days_held ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* ATTRIBUTION */}
      <div className="u-card">
        <div className="flex items-center justify-between mb-5">
          <div>
            <div className="u-label">Engine Attribution</div>
            <div className="u-caption-2 mt-1">
              Performance breakdown by engine (backtested baselines + live)
            </div>
          </div>
        </div>
        {perf ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <EngineBlock title="Engine A — Mean Reversion"
                         badge="stress regime" s={perf.engine_a} />
            <EngineBlock title="Engine B — Credit + Rates"
                         badge="directional regime" s={perf.engine_b} />
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <AttributionFallback title="Engine A — Mean Reversion"
              hint="38 backtested trades · stress regime · 10-bar hold · Sharpe 2.53 OOS" />
            <AttributionFallback title="Engine B — Credit + Rates"
              hint="262 backtested trades · directional regime · 1-bar hold · credit_stable + rates_calm agreement" />
          </div>
        )}
      </div>
      </AdvancedDetails>
    </div>
  );
}


// UX-1 Commit H — derive calm portfolio interpretation. Pure
// function. No I/O. Inputs are the values already loaded on the
// page. Tone branches: caution > neutral > healthy. Light
// temporal context uses the last two equity points when present;
// when the history is sparse we fall back to "today" framing.
function derivePortfolioCalm({
  summary, markUnavailable, openPositionsCount, equityHistory,
}: {
  summary: PaperSummary | undefined;
  markUnavailable: boolean;
  openPositionsCount: number;
  equityHistory: EquityPoint[];
}): {
  tone: string;
  chip: "success" | "neutral" | "warning";
  headline: string;
  body: string;
} {
  if (!summary) {
    return {
      tone: "Warming up",
      chip: "neutral",
      headline: "Account summary is loading.",
      body:
        "Once the daily run finishes, your holdings, gains, and "
        + "losses will appear here. No action is needed.",
    };
  }
  if (markUnavailable) {
    return {
      tone: "Worth a closer look",
      chip: "warning",
      headline: "A current price is missing.",
      body:
        "One or more open holdings don't have a fresh price right "
        + "now. We never substitute a fake zero — we show the "
        + "missing-price flag honestly. Nothing requires action.",
    };
  }
  if (openPositionsCount === 0) {
    return {
      tone: "Quiet",
      chip: "neutral",
      headline: "No open holdings right now.",
      body:
        "The paper account is fully in cash. Once a trade fills, "
        + "it will appear in the holdings table below. No action "
        + "is needed.",
    };
  }

  // Light temporal storytelling — compare today's equity vs the
  // previous snapshot. Used to choose the trailing sentence.
  let temporal = "Most holdings are moving within their normal "
    + "range today.";
  if (equityHistory.length >= 2) {
    const today = equityHistory[equityHistory.length - 1].equity;
    const prior = equityHistory[equityHistory.length - 2].equity;
    if (prior > 0) {
      const dayPct = (today - prior) / prior;
      if (dayPct >= 0.005) {
        temporal = "The account is up versus the previous session.";
      } else if (dayPct <= -0.005) {
        temporal = "The account is down versus the previous "
          + "session — temporary while trades remain open.";
      }
    }
  }
  const closeFootnote =
    "The system will close trades automatically when strategy "
    + "rules trigger. Until then, gains and losses are temporary.";

  const u = summary.unrealized_pnl ?? 0;
  if (u > 0) {
    return {
      tone: "Open positions ahead",
      chip: "success",
      headline:
        "Several holdings are currently above their entry price.",
      body: `${temporal} ${closeFootnote}`,
    };
  }
  if (u < 0) {
    return {
      tone: "Open positions behind",
      chip: "neutral",
      headline:
        "Open holdings would be down if closed right now.",
      body:
        "This fluctuates naturally while trades remain open. "
        + `${temporal} ${closeFootnote}`,
    };
  }
  return {
    tone: "Flat",
    chip: "neutral",
    headline:
      "Holdings are roughly flat against their entry prices.",
    body: `${temporal} ${closeFootnote}`,
  };
}

function Strip({
  label, value, sub, tone = "neutral", spark,
}: {
  label: string; value: string; sub: string;
  tone?: "pos" | "neg" | "neutral";
  spark?: React.ReactNode;
}) {
  const cls = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger" : "text-fg";
  return (
    <div className="px-6 first:pl-0 last:pr-0">
      <div className="flex items-start justify-between gap-2">
        <div className="u-label mb-3">{label}</div>
        {spark && (
          <div className="opacity-90 shrink-0 mt-[-2px]">
            {spark}
          </div>
        )}
      </div>
      <div className={cn("u-num-lg", cls)}>{value}</div>
      <div className="u-caption-2 mt-1.5">{sub}</div>
    </div>
  );
}

function EngineBlock({ title, badge, s }: {
  title: string; badge: string;
  s: { n_trades: number; win_rate: number; avg_return_pct: number;
       avg_duration_bars: number; total_pnl_pct: number; sharpe_proxy: number };
}) {
  return (
    <div className="u-card-tight" style={{ background: "var(--sunken)" }}>
      <div className="flex items-center justify-between mb-4">
        <span className="u-body-fg font-medium">{title}</span>
        <span className="u-pill u-pill-accent">{badge}</span>
      </div>
      <div className="grid grid-cols-3 gap-4">
        <InnerStat label="Trades" value={String(s.n_trades)} />
        <InnerStat label="Win rate" value={`${(s.win_rate * 100).toFixed(1)}%`} />
        <InnerStat label="Avg return"
          value={fmtPct(s.avg_return_pct, 3)}
          tone={toneForNumber(s.avg_return_pct)} />
        <InnerStat label="Duration" value={`${s.avg_duration_bars.toFixed(1)}d`} />
        <InnerStat label="Sharpe" value={s.sharpe_proxy.toFixed(2)}
                   tone={toneForNumber(s.sharpe_proxy - 1)} />
        <InnerStat label="Total P&L"
          value={fmtPct(s.total_pnl_pct)}
          tone={toneForNumber(s.total_pnl_pct)} />
      </div>
    </div>
  );
}

function AttributionFallback({ title, hint }: {
  title: string; hint: string;
}) {
  return (
    <div className="u-card-tight" style={{ background: "var(--sunken)" }}>
      <div className="u-body-fg font-medium mb-2">{title}</div>
      <div className="u-caption">{hint}</div>
      <div className="u-zero-state mt-3" />
    </div>
  );
}

function InnerStat({ label, value, tone = "neutral" }: {
  label: string; value: string;
  tone?: "pos" | "neg" | "neutral";
}) {
  const cls = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger" : "text-fg";
  return (
    <div>
      <div className="u-label-sm mb-1.5">{label}</div>
      <div className={cn("u-num-sm font-semibold", cls)}>{value}</div>
    </div>
  );
}
