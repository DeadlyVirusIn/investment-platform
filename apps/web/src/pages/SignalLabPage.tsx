// SignalLabPage — model quality + signal validation.
// Phase 11B introduces the surface; deeper backed metrics come later.

import { useEffect, useMemo, useState } from "react";

import { fetchPicks, type Pick } from "@/lib/picks/api";
import {
  fetchEventFeatures, type EventFeaturesResponse,
} from "@/lib/portfolio/event_features";
import { RESEARCH_NOTE } from "@/lib/ui/disclaimers";


function actionDistribution(picks: Pick[]): Record<string, number> {
  const counts: Record<string, number> = { buy: 0, sell: 0, trim: 0, hold: 0 };
  for (const p of picks) {
    const a = p.adjusted_action ?? p.action;
    counts[a] = (counts[a] ?? 0) + 1;
  }
  return counts;
}


function freshnessBuckets(picks: Pick[]): { fresh: number; recent: number; stale: number; unknown: number } {
  const out = { fresh: 0, recent: 0, stale: 0, unknown: 0 };
  for (const p of picks) {
    if (!p.generated_at) { out.unknown += 1; continue; }
    const hours = (Date.now() - Date.parse(p.generated_at)) / 3_600_000;
    if (hours < 6) out.fresh += 1;
    else if (hours < 48) out.recent += 1;
    else out.stale += 1;
  }
  return out;
}


function readinessScore(picks: Pick[], featuresAvail: number, totalSyms: number): number {
  if (picks.length === 0) return 0;
  const avgConf = picks.reduce((s, p) => {
    const c = parseFloat(p.adjusted_confidence ?? p.confidence ?? "0");
    return s + (c > 1 ? c : c * 100);
  }, 0) / picks.length;
  const fresh = freshnessBuckets(picks);
  const freshRatio = (fresh.fresh + fresh.recent) / picks.length;
  const featCoverage = totalSyms > 0 ? featuresAvail / totalSyms : 0;
  // Composite — bounded 0..100
  const score = (avgConf * 0.5) + (freshRatio * 100 * 0.3) + (featCoverage * 100 * 0.2);
  return Math.round(Math.max(0, Math.min(100, score)));
}


export default function SignalLabPage() {
  const [picks, setPicks] = useState<Pick[]>([]);
  const [loading, setLoading] = useState(true);
  const [features, setFeatures] = useState<EventFeaturesResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchPicks(50).then(rows => {
      if (cancelled) return;
      setPicks(rows);
      setLoading(false);
      const syms = rows.map(r => r.symbol).filter((s): s is string => !!s);
      if (syms.length > 0) {
        fetchEventFeatures(syms).then(f => { if (!cancelled) setFeatures(f); });
      }
    }).catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const dist = useMemo(() => actionDistribution(picks), [picks]);
  const fresh = useMemo(() => freshnessBuckets(picks), [picks]);
  const featAvail = features
    ? Object.values(features.symbols).filter(f => f.available).length
    : 0;
  const totalSyms = features ? Object.keys(features.symbols).length : 0;
  const readiness = readinessScore(picks, featAvail, totalSyms);

  return (
    <div className="picks-root" data-test="signal-lab-page" data-density="cozy">
      <div className="picks-frame">
        <header className="picks-header">
          <div>
            <h1 className="picks-title">Signal Lab</h1>
            <p className="picks-subtitle">
              Model quality, signal freshness, and event-feature coverage
            </p>
          </div>
        </header>

        {loading && <div className="picks-loading">Loading…</div>}

        {!loading && (
          <>
            <section className="ps-snapshot">
              <div className="ps-hero">
                <div className="ps-hero-text">
                  <span className="ps-eyebrow">Model readiness</span>
                  <div className="ps-nav-row">
                    <h2 className="ps-nav-value">{readiness}</h2>
                    <span className="ps-nav-delta-pct">/ 100</span>
                  </div>
                  <p className="ps-posture-banner">
                    Composite of average confidence (50%) + freshness (30%) +
                    event-feature coverage (20%).
                  </p>
                </div>
              </div>
              <div className="ps-secondary">
                <div className="ps-metric ps-metric-wide">
                  <span className="ps-metric-label">Action distribution</span>
                  <span className="ps-metric-value">
                    {dist.buy}B · {dist.sell}S · {dist.trim}T · {dist.hold}H
                  </span>
                </div>
                <div className="ps-metric" data-tone="good">
                  <span className="ps-metric-label">Fresh (&lt;6h)</span>
                  <span className="ps-metric-value">{fresh.fresh}</span>
                </div>
                <div className="ps-metric">
                  <span className="ps-metric-label">Recent (&lt;48h)</span>
                  <span className="ps-metric-value">{fresh.recent}</span>
                </div>
                <div className="ps-metric" data-tone="warn">
                  <span className="ps-metric-label">Stale (&gt;48h)</span>
                  <span className="ps-metric-value">{fresh.stale}</span>
                </div>
                <div className="ps-metric">
                  <span className="ps-metric-label">Event coverage</span>
                  <span className="ps-metric-value">{featAvail}/{totalSyms || picks.length}</span>
                </div>
              </div>
            </section>

            <section className="pi-positions">
              <header className="pi-section-header">
                <h3>Backtest validation</h3>
                <span className="pi-section-sub">Not yet wired</span>
              </header>
              <div className="pi-empty-state">
                <h4>Historical hit rate, post-signal returns, regime performance</h4>
                <p>
                  Walk-forward results, IC decay curves, and feature contribution charts
                  appear here once /api/recommendations/diagnostics surfaces those metrics.
                  Until then the upper readiness score reflects live snapshot quality only.
                </p>
              </div>
            </section>
          </>
        )}

        <footer className="picks-disclaimer">{RESEARCH_NOTE}</footer>
      </div>
    </div>
  );
}
