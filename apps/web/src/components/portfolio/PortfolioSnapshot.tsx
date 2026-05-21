// PortfolioSnapshot — asymmetric hero composition.
// Replaces the flat KPI grid. Hero NAV + sparkline + secondary metrics
// + posture banner. Designed to break "card-grid repetition".

import { useEffect, useState } from "react";

import {
  fetchCommandBar, fetchEquityCurve, fetchLiveNav,
  fmtCurrency, fmtPct, fmtSigned,
  type CommandBarData, type EquityPoint, type LiveNavData,
} from "@/lib/portfolio/api";
// Phase 15h.2 — calm "as of" annotation + tier for freshness pill.
// Phase 15h.4 — staged-freshness pending-window detection.
import {
  freshnessFromTs, formatAsOf, isPaperRunPendingWindow,
  PAPER_REFRESH_HINT_ET, type FreshnessTier,
} from "@/lib/picks/freshness";

import EquitySparkline from "./EquitySparkline";


function tone(n: number | null): "good" | "bad" | "default" {
  if (n == null) return "default";
  return n > 0 ? "good" : n < 0 ? "bad" : "default";
}


// Returns true when the US regular session is currently open
// (Mon–Fri 09:30–16:00 America/New_York). Used to switch the live-NAV
// label from "prices delayed 15 min" to "last close (market closed)"
// during off-hours / weekends. TZ-correct via Intl.DateTimeFormat.
function isUsRegularSessionOpen(now: Date = new Date()): boolean {
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = fmt.formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  const wd = get("weekday");                  // "Mon"…"Sun"
  const h = parseInt(get("hour"), 10);
  const m = parseInt(get("minute"), 10);
  if (wd === "Sat" || wd === "Sun") return false;
  const mins = h * 60 + m;
  return mins >= (9 * 60 + 30) && mins < (16 * 60);
}


export default function PortfolioSnapshot() {
  const [data, setData] = useState<CommandBarData | null>(null);
  const [equity, setEquity] = useState<EquityPoint[]>([]);
  const [liveNav, setLiveNav] = useState<LiveNavData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchCommandBar(), fetchEquityCurve(), fetchLiveNav()])
      .then(([d, e, ln]) => {
        if (cancelled) return;
        setData(d); setEquity(e); setLiveNav(ln); setLoading(false);
      })
      .catch(() => { if (!cancelled) setLoading(false); });

    // Refresh live NAV every 30s, but ONLY when the tab is visible.
    // Hidden tabs do not poll — saves server cache misses on idle
    // sessions and respects Polygon call budget. Polling resumes
    // immediately on visibilitychange → visible (one extra fetch on
    // tab focus to refresh the value the user is about to see).
    const liveInterval = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      fetchLiveNav().then((ln) => {
        if (!cancelled) setLiveNav(ln);
      });
    }, 30_000);

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        fetchLiveNav().then((ln) => {
          if (!cancelled) setLiveNav(ln);
        });
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      window.clearInterval(liveInterval);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  if (loading) {
    return <section className="ps-snapshot ps-snapshot-loading" data-test="ps-snapshot" />;
  }

  if (!data) return null;

  const navAvail = data.totalNav != null;
  const hasEquity = equity.length >= 2;

  // Compute trailing change from equity curve when available
  let trailingChange: number | null = null;
  let trailingChangePct: number | null = null;
  if (hasEquity) {
    const first = equity[0].equity;
    const last = equity[equity.length - 1].equity;
    trailingChange = last - first;
    trailingChangePct = first !== 0 ? (last / first - 1) * 100 : null;
  }

  return (
    <section className="ps-snapshot" data-test="ps-snapshot">
      {/* HERO — NAV + sparkline */}
      <div className="ps-hero">
        <div className="ps-hero-text">
          <span className="ps-eyebrow">Portfolio</span>
          {/* Phase 15h.2 — calm "as of" annotation. Always renders
              when freshAt exists; tier-driven copy keeps the
              institutional-strategist tone (no panic, no alert
              colors). When stale, label hardens to acknowledge
              the gap honestly. */}
          {data.freshAt && (() => {
            const tier: FreshnessTier = freshnessFromTs(data.freshAt);
            // Phase 15h.4 — when stale AND inside the recurring
            // 22:00–23:30 ET Mon–Fri pending window, name the next
            // refresh time instead of leaving the user thinking the
            // pipeline has been silent for days.
            const pending = tier !== "fresh"
              && isPaperRunPendingWindow(data.freshAt);
            const label = tier === "fresh"
              ? `Account valued ${formatAsOf(data.freshAt)}`
              : pending
                ? `Last completed cycle ${formatAsOf(data.freshAt)} · ${PAPER_REFRESH_HINT_ET}`
                : tier === "degraded"
                  ? `Account snapshot delayed · last update ${formatAsOf(data.freshAt)}`
                  : `Reading the last completed cycle · ${formatAsOf(data.freshAt)}`;
            return (
              <span className="ps-asof" data-tier={tier} data-pending={pending ? "true" : undefined}>
                {label}
              </span>
            );
          })()}
          {/* Phase 1a/1b — DUAL DISPLAY:                                  */}
          {/*   Primary = Live estimate (Polygon delayed 15 min)            */}
          {/*   Secondary = Official close (paper_equity_snapshot anchor)   */}
          {/* Both honestly labelled. Live falls back to official when      */}
          {/* Polygon unavailable. Trailing change stays on official (it    */}
          {/* sources the historical equity curve).                         */}
          {(() => {
            const liveAvail = liveNav?.liveEstimatedNav != null
              && (liveNav.polygonStatus === "ok"
                  || liveNav.nSymbolsPricedFallbackEod > 0
                  || liveNav.nSymbolsPricedFallbackCost > 0);
            const liveValue = liveAvail ? liveNav!.liveEstimatedNav : null;
            const liveAsOf = liveNav?.pricesAsOfEpoch != null
              ? new Date(liveNav.pricesAsOfEpoch * 1000)
              : null;
            const sessionOpen = isUsRegularSessionOpen();
            const liveLabel = (() => {
              if (!liveNav) return null;
              // Off-hours: prices come from Polygon's `prev_day.c`.
              // Surface that explicitly rather than the misleading
              // "delayed 15 min" claim.
              if (!sessionOpen
                  && liveNav.polygonStatus === "ok"
                  && liveNav.nSymbolsPricedFallbackEod === 0
                  && liveNav.nSymbolsPricedFallbackCost === 0) {
                return "Live estimate · last close (market closed)";
              }
              if (liveNav.polygonStatus === "ok"
                  && liveNav.nSymbolsPricedFallbackEod === 0
                  && liveNav.nSymbolsPricedFallbackCost === 0) {
                return "Live estimate · prices delayed 15 min";
              }
              if (liveNav.polygonStatus === "ok"
                  && (liveNav.nSymbolsPricedFallbackEod > 0
                      || liveNav.nSymbolsPricedFallbackCost > 0)) {
                const fb = liveNav.nSymbolsPricedFallbackEod
                  + liveNav.nSymbolsPricedFallbackCost;
                return `Live estimate · ${fb} of ${liveNav.nSymbolsTotal} on fallback`;
              }
              if (liveNav.polygonStatus === "error"
                  || liveNav.polygonStatus === "unavailable") {
                // Cohesion polish: when Polygon is down, the eyebrow
                // claiming "Live estimate" contradicts the body saying
                // "Polygon unavailable". Swap to honest framing.
                return "Last close (Polygon unavailable)";
              }
              return "Live estimate · prices delayed 15 min";
            })();

            return (
              <>
                <div className="ps-nav-row">
                  {liveAvail ? (
                    <h2 className="ps-nav-value">{fmtCurrency(liveValue, { compact: true })}</h2>
                  ) : navAvail ? (
                    <h2 className="ps-nav-value">{fmtCurrency(data.totalNav, { compact: true })}</h2>
                  ) : (
                    <h2 className="ps-nav-value ps-nav-pending">NAV pending</h2>
                  )}
                  {trailingChange != null && (
                    <span className="ps-nav-delta" data-tone={tone(trailingChange)}>
                      {fmtSigned(trailingChange)}
                      {trailingChangePct != null && <span className="ps-nav-delta-pct"> · {fmtPct(trailingChangePct)}</span>}
                    </span>
                  )}
                </div>
                {liveAvail && liveLabel && (
                  <div className="ps-live-label" data-test="ps-live-label"
                       data-status={liveNav?.polygonStatus ?? "unknown"}>
                    {liveLabel}
                    {liveAsOf && (
                      <span className="ps-live-asof">
                        {" · prices as of "}
                        {liveAsOf.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    )}
                  </div>
                )}
                {navAvail && (
                  <div className="ps-official-line" data-test="ps-official-line">
                    Official close: {fmtCurrency(data.totalNav, { compact: true })}
                    {data.freshAt && (
                      <span className="ps-official-asof">
                        {" · "}{formatAsOf(data.freshAt)}
                      </span>
                    )}
                  </div>
                )}
              </>
            );
          })()}
          {data.posture && (
            <div className="ps-posture-banner">
              <span className="ps-posture-dot" data-posture={(data.posture ?? "").toLowerCase()} />
              AI posture: <strong>{data.posture}</strong>
              {data.freshAt && <span className="ps-posture-fresh"> · as of {data.freshAt}</span>}
            </div>
          )}
        </div>
        <div className="ps-hero-chart">
          {hasEquity ? (
            <EquitySparkline points={equity} height={72} />
          ) : (
            <div className="ps-spark-empty">Equity curve seeds after first portfolio snapshot</div>
          )}
        </div>
      </div>

      {/* SECONDARY METRICS — canonical accounting truth.                */}
      {/* All numerics sourced from /api/paper/summary via fetchCommandBar */}
      {/* so labels + values agree across every other surface.            */}
      {/* Canonical terminology lock — never relabel without updating     */}
      {/* AccountingStrip.tsx too.                                        */}
      <div className="ps-secondary"
           data-source={import.meta.env.DEV ? "paper-summary" : undefined}>
        {/* Aggregate framing chip — first row so the reader knows the
            scope before they read any dollar value. */}
        {data.portfolioCount != null && (
          <div className="ps-metric ps-metric-wide" data-tone="default">
            <span className="ps-metric-label">Scope</span>
            <span className="ps-metric-value">
              {(() => {
                // Cohesion polish: when demo (api-test, eq-curve-test)
                // portfolios exist alongside live ones, surface the
                // split so the user knows the headline numbers blend
                // both. If split fields are absent (older backend),
                // fall back to the legacy single-count phrasing.
                const live = data.portfolioCountLive;
                const demo = data.portfolioCountDemo;
                if (live != null && demo != null && demo > 0) {
                  return `Across ${live} live + ${demo} demo paper `
                    + `portfolio${(live + demo) === 1 ? "" : "s"}`;
                }
                return `Across ${data.portfolioCount} paper portfolio`
                  + `${data.portfolioCount === 1 ? "" : "s"}`;
              })()}
            </span>
          </div>
        )}
        {/* Total profit — the headline truth: NAV − starting capital. */}
        {data.startingCapitalTotal != null && data.totalNav != null && (() => {
          const profit = data.totalNav - data.startingCapitalTotal;
          return (
            <div className="ps-metric ps-metric-wide" data-tone={tone(profit)}>
              <span className="ps-metric-label">Total profit</span>
              <span className="ps-metric-value">
                {fmtSigned(profit)}
                {data.totalReturnPct != null && (
                  <span className="ps-metric-sub">
                    {" · "}{fmtPct(data.totalReturnPct)} since inception
                  </span>
                )}
              </span>
            </div>
          );
        })()}
        {/* Today P&L. */}
        {data.dailyPnl != null && (
          <div className="ps-metric" data-tone={tone(data.dailyPnl)}>
            <span className="ps-metric-label">Today P&L</span>
            <span className="ps-metric-value">{fmtSigned(data.dailyPnl)}</span>
          </div>
        )}
        {/* Realized + Unrealized split — anchors total profit to its
            two components (identity: profit = realized + unrealized). */}
        {data.unrealizedPnl != null && (
          <div className="ps-metric" data-tone={tone(data.unrealizedPnl)}>
            <span className="ps-metric-label">Unrealized P&L</span>
            <span className="ps-metric-value">{fmtSigned(data.unrealizedPnl)}</span>
          </div>
        )}
        {data.realizedPnlCumulative != null && (
          <div className="ps-metric" data-tone={tone(data.realizedPnlCumulative)}>
            <span className="ps-metric-label">Realized P&L</span>
            <span className="ps-metric-value">
              {fmtSigned(data.realizedPnlCumulative)}
            </span>
          </div>
        )}
        {/* Holdings value (MV) — explicitly NOT "Money invested" so the
            reader is not misled into thinking it equals deployed capital. */}
        {data.holdingsValue != null && (
          <div className="ps-metric">
            <span className="ps-metric-label">Holdings value</span>
            <span className="ps-metric-value">
              {fmtCurrency(data.holdingsValue, { compact: true })}
            </span>
          </div>
        )}
        {/* Cost basis — deployed capital at avg entry. New canonical tile. */}
        {data.costBasis != null && (
          <div className="ps-metric">
            <span className="ps-metric-label">Cost basis</span>
            <span className="ps-metric-value">
              {fmtCurrency(data.costBasis, { compact: true })}
            </span>
          </div>
        )}
        {data.cashAvailable != null && (
          <div className="ps-metric">
            <span className="ps-metric-label">Available cash</span>
            <span className="ps-metric-value">
              {fmtCurrency(data.cashAvailable, { compact: true })}
            </span>
          </div>
        )}
        {data.openPositionsCount != null && (
          <div className="ps-metric">
            <span className="ps-metric-label">Open positions</span>
            <span className="ps-metric-value">{data.openPositionsCount}</span>
          </div>
        )}
        {data.monthlyPremium != null && data.monthlyPremium > 0 && (
          <div className="ps-metric ps-metric-accent" data-tone="good">
            <span className="ps-metric-label">Premium MTD</span>
            <span className="ps-metric-value">
              {fmtCurrency(data.monthlyPremium, { compact: true })}
            </span>
          </div>
        )}
        {data.activeStrategies != null && data.activeStrategies > 0 && (
          <div className="ps-metric">
            <span className="ps-metric-label">Active strategies</span>
            <span className="ps-metric-value">{data.activeStrategies}</span>
          </div>
        )}
        {data.portfolioRiskLabel && (
          <div className="ps-metric"
               data-tone={data.portfolioRiskLabel === "high" ? "bad" : "default"}>
            <span className="ps-metric-label">Portfolio risk</span>
            <span className="ps-metric-value">{data.portfolioRiskLabel}</span>
          </div>
        )}
      </div>

      {/* Replay-recovered transparency footnote. Quantifies the dollar
          contribution from recovered positions to the NAV above. */}
      {data.replayPositionsMarketValue != null
        && data.replayPositionsMarketValue > 0 && (
        <div className="ps-replay-footnote"
             data-test="ps-replay-footnote">
          Recovered positions contribute{" "}
          <strong>
            {fmtCurrency(data.replayPositionsMarketValue, { compact: true })}
          </strong>{" "}
          to account value (post-2026-05-02 reset replay).
        </div>
      )}
    </section>
  );
}
