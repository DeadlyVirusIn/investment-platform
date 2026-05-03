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
import EquityDrawdownChart from "@/components/operator/EquityDrawdownChart";
import Sparkline from "@/components/ui/Sparkline";
import { cn } from "@/lib/cn";

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
  const exposure = open.reduce(
    (s, t) => s + (summary?.equity ?? 0) * (t.position_size_pct / 100), 0,
  );
  const exposurePct = summary ? exposure / summary.equity : 0;

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-8 space-y-6">
      <header>
        <div className="u-label mb-1">Portfolio</div>
        <h1 className="u-title-lg">Paper Trading Terminal</h1>
        <p className="u-body mt-2">
          Live paper portfolio ·
          {" "}{execSummary?.trades_total ?? 0} executed trades ·
          {" "}{execSummary?.open_positions ?? 0} open positions ·
          {" "}{state?.as_of_date ?? "idle"}
        </p>
        {execSummary?.has_replay_recovered_rows && (
          <div
            className="u-card-tight mt-2 flex items-center justify-between"
            style={{ background: "var(--sunken)", padding: "8px 12px" }}
          >
            <div className="u-caption">
              <span className="u-chip u-chip-warning mr-2">
                Recovered replay
              </span>
              Some rows in this account were rebuilt from the
              2026-05-02 DB wipe via the execution-chain replay.
              They are tagged in <code>replay_recovery_manifest</code>
              and excluded by default.
            </div>
            <label className="u-caption flex items-center gap-2">
              <input
                type="checkbox"
                checked={includeReplay}
                onChange={e => setIncludeReplay(e.target.checked)}
              />
              <span>Include recovered rows</span>
            </label>
          </div>
        )}
      </header>

      {/* STRIP */}
      <div className="u-card">
        <div className="grid grid-cols-1 md:grid-cols-5 divide-x divide-b2">
          <Strip label="NAV"
            value={summary ? fmtUSD(summary.equity) : "—"}
            sub={`starting $100,000`}
            spark={
              <Sparkline values={equitySeries}
                          ariaLabel="NAV history" />
            } />
          <Strip label="Return"
            value={fmtPct(summary?.total_return_pct)}
            tone={toneForNumber(summary?.total_return_pct ?? 0)}
            sub={`inception-to-date`}
            spark={
              <Sparkline values={returnSeries}
                          ariaLabel="Cumulative return history" />
            } />
          <Strip label="Drawdown"
            value={fmtPct(summary?.max_drawdown_pct)}
            tone="neg"
            sub="peak-to-trough"
            spark={
              <Sparkline values={drawdownSeries}
                          tone="neg"
                          ariaLabel="Drawdown history" />
            } />
          <Strip label="Cash"
            value={summary ? fmtUSD(summary.cash) : "—"}
            sub={summary ? `${((summary.cash / summary.equity) * 100).toFixed(0)}% of NAV` : "—"} />
          <Strip label="Exposure"
            value={fmtUSD(exposure)}
            sub={`${(exposurePct * 100).toFixed(1)}% · ${open.length} open`} />
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

      {/* EXECUTED ACTIVITY (account/recommendation path) — Phase 11Z */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="u-card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="u-label">Open Positions</div>
              <div className="u-caption-2 mt-1">
                {openExecPositions.length > 0
                  ? "Account-path holdings (paper_position)"
                  : "No active executed positions"}
              </div>
            </div>
            <span className="u-pill u-pill-neutral">
              {openExecPositions.length} open
            </span>
          </div>
          {openExecPositions.length === 0 ? (
            <div className="u-card-tight"
                 style={{ background: "var(--sunken)" }}>
              <div className="u-body-fg font-medium mb-2">
                No open executed positions
              </div>
              <div className="u-caption">
                {execSummary?.has_replay_recovered_rows
                  ? "Recovered replay rows available — toggle 'Include recovered rows' above to view."
                  : "Account/recommendation path has no open positions. Run the recommendation engine to generate buy candidates."}
              </div>
            </div>
          ) : (
            <table className="u-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Portfolio</th>
                  <th className="text-right">Qty</th>
                  <th className="text-right">Avg Cost</th>
                  <th>Opened</th>
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
                        <span className="u-chip u-chip-warning">replay</span>
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
              <div className="u-label">Executed Trades</div>
              <div className="u-caption-2 mt-1">
                {executedTrades.length > 0
                  ? "Account-path fills (paper_trade)"
                  : "No executed trades yet"}
              </div>
            </div>
            <span className="u-pill u-pill-neutral">
              {executedTrades.length} fills
            </span>
          </div>
          {executedTrades.length === 0 ? (
            <div className="u-card-tight"
                 style={{ background: "var(--sunken)" }}>
              <div className="u-body-fg font-medium mb-2">No executed trades</div>
              <div className="u-caption">
                {execSummary?.has_replay_recovered_rows
                  ? "Recovered replay rows available — toggle 'Include recovered rows' above."
                  : "Account/recommendation path has no fills yet."}
              </div>
            </div>
          ) : (
            <table className="u-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th className="text-right">Qty</th>
                  <th className="text-right">Fill</th>
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
                        <span className="u-chip u-chip-warning">replay</span>
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
                      {t.position_size_pct.toFixed(1)}
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
              <div className="u-label">Realized History</div>
              <div className="u-caption-2 mt-1">
                {closed.length > 0
                  ? "Most recent closed trades"
                  : "No closed trades yet"}
              </div>
            </div>
            <span className="u-pill u-pill-neutral">{closed.length} closed</span>
          </div>
          {closed.length === 0 ? (
            <div className="u-card-tight"
                 style={{ background: "var(--sunken)" }}>
              <div className="u-body-fg font-medium mb-2">
                No realized history yet
              </div>
              <div className="u-caption">
                Engine A holds 10 bars; Engine B holds 1 bar. Closed trades
                will populate here with realized returns, slippage, and
                regime attribution.
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
    </div>
  );
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
