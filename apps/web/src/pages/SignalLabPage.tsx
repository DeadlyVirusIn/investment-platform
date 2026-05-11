// SignalLabPage — model quality + signal validation.
// Phase 11B introduces the surface; deeper backed metrics come later.

import { useEffect, useMemo, useState } from "react";

import { fetchPicks, type Pick } from "@/lib/picks/api";
import {
  fetchEventFeatures, type EventFeaturesResponse,
} from "@/lib/portfolio/event_features";
import { RESEARCH_NOTE } from "@/lib/ui/disclaimers";
import PageChapter from "@/components/shell/PageChapter";
import NextStepCard from "@/components/shell/NextStepCard";
import FetchError from "@/components/shell/FetchError";
import ExpertDetails from "@/components/shell/ExpertDetails";
// Phase 15b3 — DensityToggle hidden on this page; only readInitialDensity
// + Density type still needed for the data-density cascade attr.
import { readInitialDensity, type Density } from "@/components/portfolio/DensityToggle";


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
  const [error, setError] = useState<Error | null>(null);
  const [features, setFeatures] = useState<EventFeaturesResponse | null>(null);
  const [density] = useState<Density>(() => readInitialDensity());

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
    }).catch((e: unknown) => {
      if (cancelled) return;
      setError(e instanceof Error ? e : new Error(String(e)));
      setLoading(false);
    });
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
    <div className="picks-root" data-test="signal-lab-page" data-density={density}>
      <div className="picks-frame">
        <header className="picks-header">
          <div>
            <h1 className="picks-title">Signal Lab</h1>
            <p className="picks-subtitle">
              Model quality, signal freshness, and event-feature coverage
            </p>
          </div>
          {/* Phase 15b3 — DensityToggle hidden on Signal Lab (audit P1.10).
              Inert here; state + data-density preserved for cascade. */}
        </header>

        <PageChapter
          pathname="/signal-lab"
          now={
            picks.length === 0
              ? undefined
              : `Readiness ${readiness}/100 · ${fresh.fresh + fresh.recent} fresh / ${fresh.stale} stale · event coverage ${featAvail}/${totalSyms || picks.length}.`
          }
        />

        {/* Phase 15c2 — Loading-state consistency.
            Was: <div className="picks-loading">Loading…</div> — plain
            centered text that caused content jump on resolve.
            Now: same .ps-snapshot-loading shimmer block PortfolioSnapshot
            uses on Overview. Layout-stable (matches the readiness hero
            container shape it's about to fill); same visual idiom across
            the two ps-snapshot pages so the loading rhythm is
            recognisably one product. */}
        {loading && (
          <section
            className="ps-snapshot ps-snapshot-loading"
            data-test="signal-lab-snapshot-loading"
            aria-busy="true"
            aria-live="polite"
            aria-label="Loading Signal Lab"
          />
        )}

        {error && (
          <FetchError
            title="Could not load Signal Lab data"
            message={error.message}
            onRetry={() => window.location.reload()}
          />
        )}

        {!loading && !error && (
          <>
            <section className="ps-snapshot">
              <div className="ps-hero">
                <div className="ps-hero-text">
                  <span className="ps-eyebrow">Model readiness</span>
                  <div className="ps-nav-row">
                    <h2 className="ps-nav-value">{readiness}</h2>
                    <span className="ps-nav-delta-pct">/ 100</span>
                  </div>
                  {/* Phase 15b3 — Readiness interpretation band (audit P1.13).
                      A 0-100 score has no meaning without a band. Three
                      tiers tied to the same composite number; honest
                      derivation, no calibration faked. */}
                  <ReadinessBand score={readiness} />
                  <ExpertDetails label="How readiness is computed">
                    <p style={{ margin: 0 }}>
                      Composite formula: <code>0.5 × avg_confidence + 0.3 × fresh_ratio × 100 + 0.2 × event_coverage × 100</code>.
                      Bounded 0–100. Average confidence is mean of
                      adjusted_confidence over all signals; fresh_ratio is
                      (fresh + recent) ÷ total; event_coverage is
                      symbols_with_features ÷ total_symbols.
                    </p>
                  </ExpertDetails>
                </div>
              </div>
              <div className="ps-secondary">
                <div className="ps-metric ps-metric-wide">
                  <span className="ps-metric-label">Action distribution</span>
                  <span className="ps-metric-value">
                    {dist.buy} buy · {dist.sell} sell · {dist.trim} trim · {dist.hold} hold
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

            {/* Phase 15a — Truth fix. Removed ~280px "Not yet wired"
                tombstone block that read as a developer backlog ticket
                on the credibility page. Status moved into a single
                ExpertDetails one-liner so operators can still see the
                pending validation channel without a vacancy sign in
                the primary view. */}
            <ExpertDetails label="Backtest validation status">
              <p>
                Backtest validation pending — see Ops &gt; ML pipeline.
                Walk-forward results, IC decay curves, and feature
                contribution charts appear here once
                <code> /api/recommendations/diagnostics </code>
                surfaces those metrics. Until then the readiness score
                above reflects live snapshot quality only.
              </p>
            </ExpertDetails>
          </>
        )}

        <NextStepCard pathname="/signal-lab" />

        <footer className="picks-disclaimer">{RESEARCH_NOTE}</footer>
      </div>
    </div>
  );
}


// Phase 15b3 — Readiness interpretation band.
// 0-40   = data incomplete / use caution
// 41-70  = acceptable / inspect signals
// 71-100 = strong / safe to inspect
// Honest tiering — same composite number, no calibration faked.
function ReadinessBand({ score }: { score: number }) {
  const tier = score >= 71 ? "strong" : score >= 41 ? "acceptable" : "caution";
  const label = tier === "strong"
    ? "Strong — safe to inspect signals"
    : tier === "acceptable"
      ? "Acceptable — inspect with care"
      : "Caution — data incomplete this cycle";
  return (
    <div
      className="readiness-band"
      data-tier={tier}
      role="note"
      aria-label="Readiness interpretation"
    >
      <span className="readiness-band-dot" aria-hidden="true" />
      <span className="readiness-band-label">{label}</span>
    </div>
  );
}
