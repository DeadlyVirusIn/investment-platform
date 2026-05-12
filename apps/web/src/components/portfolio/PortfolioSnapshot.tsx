// PortfolioSnapshot — asymmetric hero composition.
// Replaces the flat KPI grid. Hero NAV + sparkline + secondary metrics
// + posture banner. Designed to break "card-grid repetition".

import { useEffect, useState } from "react";

import {
  fetchCommandBar, fetchEquityCurve,
  fmtCurrency, fmtPct, fmtSigned,
  type CommandBarData, type EquityPoint,
} from "@/lib/portfolio/api";
// Phase 15h.2 — calm "as of" annotation + tier for freshness pill.
import {
  freshnessFromTs, formatAsOf, type FreshnessTier,
} from "@/lib/picks/freshness";

import EquitySparkline from "./EquitySparkline";


function tone(n: number | null): "good" | "bad" | "default" {
  if (n == null) return "default";
  return n > 0 ? "good" : n < 0 ? "bad" : "default";
}


export default function PortfolioSnapshot() {
  const [data, setData] = useState<CommandBarData | null>(null);
  const [equity, setEquity] = useState<EquityPoint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchCommandBar(), fetchEquityCurve()])
      .then(([d, e]) => {
        if (cancelled) return;
        setData(d); setEquity(e); setLoading(false);
      })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
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
            const label = tier === "fresh"
              ? `Account valued ${formatAsOf(data.freshAt)}`
              : tier === "degraded"
                ? `Account snapshot delayed · last update ${formatAsOf(data.freshAt)}`
                : `Reading the last completed cycle · ${formatAsOf(data.freshAt)}`;
            return (
              <span className="ps-asof" data-tier={tier}>
                {label}
              </span>
            );
          })()}
          <div className="ps-nav-row">
            {navAvail ? (
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

      {/* SECONDARY METRICS — asymmetric grid */}
      {/* Phase 13k — added Total Return %, Money Invested, Open
          positions, and Daily P&L. All sourced from canonical
          /api/paper/summary so this card now agrees with
          PortfolioTerminal byte-for-byte. */}
      <div className="ps-secondary"
           data-source={import.meta.env.DEV ? "paper-summary" : undefined}>
        {data.totalReturnPct != null && (
          <div className="ps-metric ps-metric-wide" data-tone={tone(data.totalReturnPct)}>
            <span className="ps-metric-label">Total return</span>
            <span className="ps-metric-value">{fmtPct(data.totalReturnPct)}</span>
          </div>
        )}
        {data.openPnl != null && (
          <div className="ps-metric" data-tone={tone(data.openPnl)}>
            <span className="ps-metric-label">Open P&L</span>
            <span className="ps-metric-value">{fmtSigned(data.openPnl)}</span>
          </div>
        )}
        {data.dailyPnl != null && data.dailyPnl !== 0 && (
          <div className="ps-metric" data-tone={tone(data.dailyPnl)}>
            <span className="ps-metric-label">Day P&L</span>
            <span className="ps-metric-value">{fmtSigned(data.dailyPnl)}</span>
          </div>
        )}
        {data.realizedPnl != null && (
          <div className="ps-metric" data-tone={tone(data.realizedPnl)}>
            <span className="ps-metric-label">Realized</span>
            <span className="ps-metric-value">{fmtSigned(data.realizedPnl)}</span>
          </div>
        )}
        {data.cashAvailable != null && (
          <div className="ps-metric">
            <span className="ps-metric-label">Cash</span>
            <span className="ps-metric-value">{fmtCurrency(data.cashAvailable, { compact: true })}</span>
          </div>
        )}
        {data.moneyInvested != null && (
          <div className="ps-metric">
            <span className="ps-metric-label">Money invested</span>
            <span className="ps-metric-value">{fmtCurrency(data.moneyInvested, { compact: true })}</span>
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
            <span className="ps-metric-value">{fmtCurrency(data.monthlyPremium, { compact: true })}</span>
          </div>
        )}
        {data.activeStrategies != null && data.activeStrategies > 0 && (
          <div className="ps-metric">
            <span className="ps-metric-label">Active strategies</span>
            <span className="ps-metric-value">{data.activeStrategies}</span>
          </div>
        )}
        {data.portfolioRiskLabel && (
          <div className="ps-metric" data-tone={data.portfolioRiskLabel === "high" ? "bad" : "default"}>
            <span className="ps-metric-label">Portfolio risk</span>
            <span className="ps-metric-value">{data.portfolioRiskLabel}</span>
          </div>
        )}
      </div>
    </section>
  );
}
