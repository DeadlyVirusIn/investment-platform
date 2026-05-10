// HealthRail — sticky portfolio-first contextual rail.
// Replaces the AI-centric Copilot sidebar. Real values only.

import { useEffect, useState } from "react";

import {
  fetchOpenPositions, fetchLifecycleTrades,
  deriveHealthRail, fmtCurrency, fmtSigned,
  type HealthRailData,
} from "@/lib/portfolio/api";


export interface HealthRailProps {
  staleCount: number;
  watchlistCount: number;
  riskCount: number;
  posture: string;
}


function Row({ label, value, tone, hint }: {
  label: string; value: string; tone?: "good" | "bad" | "warn" | "muted"; hint?: string;
}) {
  return (
    <div className="hr-row" data-tone={tone ?? "default"}>
      <span className="hr-row-label">{label}</span>
      <span className="hr-row-value">{value}</span>
      {hint && <span className="hr-row-hint">{hint}</span>}
    </div>
  );
}


export default function HealthRail({ staleCount, watchlistCount, riskCount, posture }: HealthRailProps) {
  const [data, setData] = useState<HealthRailData | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchOpenPositions(), fetchLifecycleTrades()])
      .then(([positions, trades]) => {
        if (cancelled) return;
        setData(deriveHealthRail(positions, trades));
      })
      .catch(() => { /* silent — rail just stays empty */ });
    return () => { cancelled = true; };
  }, []);

  return (
    <aside className="hr-rail" data-test="hr-rail">
      <header className="hr-header">
        <h3 className="hr-title">Portfolio Health</h3>
        <span className="hr-sub">{posture}</span>
      </header>

      <section className="hr-section">
        <h4 className="hr-section-title">Today</h4>
        {data?.premiumToday != null ? (
          <Row label="Premium collected" value={fmtCurrency(data.premiumToday)} tone="good" />
        ) : (
          <div className="hr-empty">No premium collected today</div>
        )}
      </section>

      <section className="hr-section">
        <h4 className="hr-section-title">Movers</h4>
        {data?.largestWinner ? (
          <Row label="Top winner" value={`${data.largestWinner.symbol} · ${fmtSigned(data.largestWinner.pnl)}`} tone="good" />
        ) : (
          <div className="hr-empty">No winners yet</div>
        )}
        {data?.largestLoser ? (
          <Row label="Top loser" value={`${data.largestLoser.symbol} · ${fmtSigned(data.largestLoser.pnl)}`} tone="bad" />
        ) : (
          <div className="hr-empty">No losers yet</div>
        )}
      </section>

      <section className="hr-section">
        <h4 className="hr-section-title">Concentration</h4>
        {data?.largestPosition ? (
          <Row
            label="Largest position"
            value={`${data.largestPosition.symbol} · ${fmtCurrency(data.largestPosition.mv, { compact: true })}`}
            hint={data.totalOpen > 0 ? `${data.totalOpen} open` : undefined}
          />
        ) : (
          <div className="hr-empty">Concentration data needs price marks</div>
        )}
      </section>

      <section className="hr-section">
        <h4 className="hr-section-title">Watchlist</h4>
        <Row label="Hold candidates" value={String(watchlistCount)} tone="muted" />
        <Row label="Risk-flagged signals" value={String(riskCount)} tone={riskCount > 0 ? "warn" : "muted"} />
        {staleCount > 0 && (
          <Row label="Stale signals" value={String(staleCount)} tone="warn" />
        )}
      </section>

      <section className="hr-section">
        <h4 className="hr-section-title">Calendar</h4>
        <div className="hr-empty">Earnings + expirations need a market-data provider (Polygon / Tradier).</div>
      </section>
    </aside>
  );
}
