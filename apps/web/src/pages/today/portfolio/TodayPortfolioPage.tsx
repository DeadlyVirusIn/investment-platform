// TodayPortfolioPage — calm holdings view for /today/portfolio (PR-2).
//
// Parallel route. Legacy /portfolio is untouched. All data comes from
// existing endpoints; no new schemas, no new fetchers.
//
// Above the fold:
//   - Portfolio NAV (one number)
//   - Live estimate · prices delayed 15 min
//   - Official close · DATE
//   - Tiny sparkline
// Below the fold:
//   - Holdings list, calm rows, no glow, no lift
//   - "What does each row mean?" learning hint
//
// Hard locks honored:
//   - paper-only label stays
//   - Polygon "delayed 15 min" copy stays
//   - no operator chrome (no Shell wrapper)
//   - no glow / no lift / no uppercase
//   - losses styled equally weight as gains (terracotta, not red)

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  fetchCommandBar, fetchLiveNav, fetchEquityCurve,
  fmtCurrency, fmtPct, fmtSigned,
  type CommandBarData, type LiveNavData, type EquityPoint,
} from "@/lib/portfolio/api";
import EquitySparkline from "@/components/portfolio/EquitySparkline";

import TodayNav from "@/components/today/TodayNav";

import "../today.css";
import "@/styles/primitives.css";


interface OpenPosition {
  symbol: string | null;
  quantity: number | null;
  avg_cost: number | null;
  current_price?: number | null;
  market_value?: number | null;
  unrealized_pnl_dollars?: number | null;
  return_pct?: number | null;
  is_replay?: boolean | null;
}


export default function TodayPortfolioPage() {
  const [cmd, setCmd]   = useState<CommandBarData | null>(null);
  const [live, setLive] = useState<LiveNavData | null>(null);
  const [equity, setEquity] = useState<EquityPoint[]>([]);
  const [positions, setPositions] = useState<OpenPosition[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [c, l, e, p] = await Promise.all([
          fetchCommandBar(),
          fetchLiveNav(),
          fetchEquityCurve(),
          fetch("/api/paper/executed/positions?is_open=true")
            .then(r => r.ok ? r.json() : { positions: [] })
            .catch(() => ({ positions: [] })),
        ]);
        if (cancelled) return;
        setCmd(c);
        setLive(l);
        setEquity(e);
        setPositions(Array.isArray(p?.positions) ? p.positions : []);
      } catch {
        /* honest absence */
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    const interval = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      fetchLiveNav().then((l) => { if (!cancelled) setLive(l); });
    }, 30_000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  const liveNav = live?.liveEstimatedNav ?? null;
  const liveAsOf = live?.pricesAsOfEpoch != null
    ? new Date(live.pricesAsOfEpoch * 1000)
    : null;
  const officialNav = cmd?.totalNav ?? null;
  const officialAsOf = cmd?.freshAt ?? null;

  // Sort positions by absolute market value descending so largest
  // exposure floats to top. Calm, not a leaderboard.
  const sortedPositions = useMemo(() => {
    return [...positions]
      .filter(p => p.symbol && Number(p.quantity) > 0)
      .sort((a, b) => (Math.abs(b.market_value ?? 0) - Math.abs(a.market_value ?? 0)));
  }, [positions]);

  return (
    <div className="today-root">
      <TodayNav />

      <main className="today-page">
        {/* Hero */}
        <section className="today-section">
          <h1 className="today-greeting">Portfolio</h1>
          <p className="today-section-label">Your paper portfolio</p>
          <div className="today-portfolio">
            <h2 className="today-nav-value">
              {liveNav != null
                ? fmtCurrency(liveNav, { compact: true })
                : officialNav != null
                  ? fmtCurrency(officialNav, { compact: true })
                  : "—"}
            </h2>
            {equity.length >= 2 && (
              <div className="today-portfolio-spark">
                <EquitySparkline points={equity.slice(-30)} height={28} theme="neutral" />
              </div>
            )}
          </div>
          <div className="today-portfolio-lines">
            {liveNav != null && (
              <span className="today-portfolio-line">
                <strong>Live estimate:</strong>{" "}
                {fmtCurrency(liveNav)}
                {" · prices delayed 15 min"}
                {liveAsOf && (
                  <>
                    {" · as of "}
                    {liveAsOf.toLocaleTimeString([], {
                      hour: "2-digit", minute: "2-digit",
                    })}
                  </>
                )}
              </span>
            )}
            {officialNav != null && (
              <span className="today-portfolio-line">
                <strong>Official close:</strong>{" "}
                {fmtCurrency(officialNav)}
                {officialAsOf && (<>{" · "}{officialAsOf}</>)}
              </span>
            )}
          </div>
        </section>

        {/* Holdings list */}
        <section className="today-section">
          <p className="today-section-label">Holdings</p>
          {loading && (
            <p className="today-empty">Loading positions…</p>
          )}
          {!loading && sortedPositions.length === 0 && (
            <p className="today-empty">
              No open positions yet. Holdings will appear once trades open.
            </p>
          )}
          {sortedPositions.length > 0 && (
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {sortedPositions.map((p, i) => {
                const ret = p.return_pct;
                const tone = ret == null
                  ? "neutral"
                  : ret > 0 ? "up" : ret < 0 ? "down" : "neutral";
                return (
                  <li className="calm-row" key={`${p.symbol}-${i}`}>
                    <div>
                      <div className="calm-row-primary">{p.symbol ?? "—"}</div>
                      <div className="calm-row-secondary">
                        {Number(p.quantity).toLocaleString(undefined, {
                          maximumFractionDigits: 4,
                        })}
                        {" units"}
                        {p.avg_cost != null && (
                          <>{" · cost "}{fmtCurrency(p.avg_cost)}</>
                        )}
                      </div>
                    </div>
                    <div>
                      <div className="calm-row-value">
                        {p.market_value != null
                          ? fmtCurrency(p.market_value)
                          : "—"}
                      </div>
                      <div className="calm-row-meta">
                        <span className="calm-badge" data-tone={tone}>
                          <span className="calm-badge-dot" />
                          {ret != null ? fmtPct(ret) : "—"}
                          {p.unrealized_pnl_dollars != null && (
                            <>{" · "}{fmtSigned(p.unrealized_pnl_dollars)}</>
                          )}
                        </span>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* Learning hint */}
        <section className="today-section">
          <div className="today-learn">
            <h3 className="today-learn-term">Reading this page</h3>
            <p className="today-learn-def">
              Each row shows one open position with its current value,
              unrealized return, and dollar P&amp;L versus cost basis.
              Live estimate uses 15-minute delayed quotes; the official
              close is the nightly snapshot.
            </p>
            <Link to="/learn" className="today-learn-cta">
              More terms &rarr;
            </Link>
          </div>
        </section>

        {/* Browse footer */}
        <nav className="today-browse" aria-label="Browse more">
          <Link to="/today">Today</Link>
          <span>·</span>
          <Link to="/ideas">Ideas</Link>
          <span>·</span>
          <Link to="/learn">Learn</Link>
        </nav>

        <details className="today-advanced">
          <summary>Advanced</summary>
          <ul>
            <li><Link to="/portfolio">Operator portfolio terminal</Link></li>
            <li><Link to="/decisions">AI activity audit</Link></li>
            <li><Link to="/risk">Risk</Link></li>
          </ul>
        </details>
      </main>
    </div>
  );
}
