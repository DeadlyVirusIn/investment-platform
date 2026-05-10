// PickModal — copilot-style research view.
//
// Beginner-friendly sections in plain English. Technical details
// hidden behind "Show technical details" toggle.

import { useEffect, useMemo, useRef, useState } from "react";

import type { Pick, LatestPrice, PickAction } from "@/lib/picks/api";
import {
  confidenceLabel, fmtConfidencePct, fetchLatestPrice,
  actionTitle,
} from "@/lib/picks/api";
import { fetchSymbolEvents, type EventsState } from "@/lib/portfolio/events";


export interface PickModalProps {
  pick: Pick | null;
  priceCache?: LatestPrice | null;
  onClose: () => void;
}


function fmtPrice(p: number | null): string {
  if (p == null) return "—";
  if (p >= 1000) return `$${p.toFixed(0)}`;
  return `$${p.toFixed(2)}`;
}


function fmtRelTime(iso: string | null): string {
  if (!iso) return "—";
  const ms = Date.now() - Date.parse(iso);
  const hours = ms / 3_600_000;
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m ago`;
  if (hours < 24) return `${Math.round(hours)}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}


function plainWhatThisMeans(action: PickAction): string {
  switch (action) {
    case "buy":  return "AI sees an opportunity to enter or add to this position. Strength is building.";
    case "sell": return "AI suggests exiting this position. The downside risk is greater than the remaining upside.";
    case "trim": return "AI suggests reducing exposure but not fully exiting. Some upside may remain but risk has grown.";
    case "hold": return "Keep watching this name but don't take new action yet. The signals aren't strong enough either way.";
  }
}


function plainWhatCouldChange(action: PickAction): string {
  switch (action) {
    case "buy":  return "If price breaks key support or momentum reverses, the AI may downgrade to Hold or Trim.";
    case "sell": return "If price stabilizes above invalidation or fundamentals improve, the AI may upgrade to Hold.";
    case "trim": return "If momentum re-strengthens or risk metrics improve, the AI may move back to Hold or Buy.";
    case "hold": return "A clear breakout, flow signal, or earnings catalyst could shift the AI toward Buy or Trim.";
  }
}


function riskLevel(pick: Pick): "low" | "medium" | "high" {
  const conf = pick.adjusted_confidence ?? pick.confidence;
  const n = parseFloat(conf ?? "0");
  const pct = n > 1 ? n : n * 100;
  if (pick.stale_data || !pick.enough_data) return "high";
  if (pct < 50) return "high";
  if (pct < 70) return "medium";
  return "low";
}


function riskLevelText(level: "low" | "medium" | "high"): string {
  switch (level) {
    case "low":    return "Low — signals are clean and recent.";
    case "medium": return "Medium — partial signal strength or some uncertainty.";
    case "high":   return "High — thin data, stale signals, or low confidence.";
  }
}


function buildPlainThesis(pick: Pick): string {
  // Start with raw thesis, but drop "composite score" / "score:" jargon if present
  const t = pick.thesis ?? "";
  const cleaned = t
    .replace(/composite\s+score\s+[\-+]?[\d.]+\s*[→\-]+\s*\w+\.?\s*/gi, "")
    .replace(/(trend|momentum|volatility|risk|valuation|growth)\/?\w*\s+score[: ]\s*[\-+]?[\d.]+\s*\.?/gi, "")
    .replace(/\s{2,}/g, " ")
    .trim();
  if (cleaned.length > 12) return cleaned;

  // Fallback if thesis was almost entirely jargon
  const action = pick.adjusted_action ?? pick.action;
  switch (action) {
    case "buy":  return "Multiple factors point to upside; entry conditions look favorable.";
    case "sell": return "Risk metrics dominate; the AI's models suggest exiting.";
    case "trim": return "Momentum has weakened relative to entry conditions; AI suggests scaling back.";
    case "hold": return "Signals are mixed across momentum, valuation, and trend — no clear edge.";
  }
}


export default function PickModal({ pick, priceCache, onClose }: PickModalProps) {
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const [price, setPrice] = useState<LatestPrice | null | undefined>(undefined);
  const [techOpen, setTechOpen] = useState(false);
  const [events, setEvents] = useState<EventsState>({ status: "loading" });

  useEffect(() => {
    if (!pick?.symbol) {
      setPrice(undefined);
      setTechOpen(false);
      setEvents({ status: "loading" });
      return;
    }
    setTechOpen(false);
    if (priceCache !== undefined) {
      setPrice(priceCache);
    } else {
      setPrice(undefined);
    }
    let cancelled = false;
    if (priceCache === undefined) {
      fetchLatestPrice(pick.symbol).then(p => {
        if (!cancelled) setPrice(p);
      });
    }
    setEvents({ status: "loading" });
    fetchSymbolEvents(pick.symbol).then(s => {
      if (!cancelled) setEvents(s);
    });
    return () => { cancelled = true; };
  }, [pick?.symbol, pick?.id, priceCache]);

  useEffect(() => {
    if (!pick) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeBtnRef.current?.focus();

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [pick, onClose]);

  const isOpen = pick !== null;
  const action = pick ? (pick.adjusted_action ?? pick.action) : "hold";
  const confidence = pick ? (pick.adjusted_confidence ?? pick.confidence) : null;
  const risk = pick ? riskLevel(pick) : "medium";

  // Top 4 evidence items with narratives
  const topEvidence = useMemo(
    () => pick?.evidence?.filter(e => e.narrative && e.narrative.length > 0).slice(0, 4) ?? [],
    [pick],
  );

  const hasPriceStrip = pick && (
    pick.risk.entry_price != null ||
    pick.risk.target_price != null ||
    pick.risk.stop_loss != null ||
    price !== undefined
  );

  return (
    <div
      className="pick-overlay"
      data-open={isOpen ? "true" : "false"}
      data-test="pick-overlay"
      onClick={onClose}
      aria-hidden={!isOpen}
    >
      {pick && (
        <div
          className="pick-modal"
          data-action={action}
          data-test="pick-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="pick-modal-symbol"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <header className="pick-modal-header">
            <div>
              <span className="pick-modal-eyebrow">AI Research Cockpit</span>
              <h2 id="pick-modal-symbol" className="pick-modal-symbol">
                {pick.symbol ?? "—"}
              </h2>
              <div className="pick-modal-symbol-sub">
                {pick.engine_version ? `engine ${pick.engine_version}` : "AI suggestion"}
                {pick.generated_at && ` · ${fmtRelTime(pick.generated_at)}`}
              </div>
            </div>
            <button
              ref={closeBtnRef}
              type="button"
              className="pick-modal-close"
              onClick={onClose}
              aria-label="Close details"
            >
              ×
            </button>
          </header>

          {/* Recommendation — big colored badge */}
          <section className="pick-modal-section" data-test="pick-modal-recommendation">
            <h4>Recommendation</h4>
            <div className="pick-modal-action-row">
              <span className="pick-modal-action-badge">{action}</span>
              <span><strong>{actionTitle(action)}</strong></span>
              <span>· {confidenceLabel(confidence)} confidence ({fmtConfidencePct(confidence)})</span>
            </div>
          </section>

          {/* What this means */}
          <section className="pick-modal-section" data-test="pick-modal-meaning">
            <h4>What this means</h4>
            <div className="pick-modal-callout">
              {plainWhatThisMeans(action)}
            </div>
          </section>

          {/* Plain-English thesis */}
          <section className="pick-modal-section" data-test="pick-modal-thesis">
            <h4>Plain-English thesis</h4>
            <p>{buildPlainThesis(pick)}</p>
          </section>

          {/* Reference price */}
          {hasPriceStrip && (
            <section className="pick-modal-section" data-test="pick-modal-prices">
              <h4>Reference price</h4>
              <div className="pick-modal-prices">
                {price !== undefined && (
                  <div className="pick-modal-price-cell">
                    <span className="pick-modal-price-label">Latest close</span>
                    <span className="pick-modal-price-value">
                      {price ? fmtPrice(price.close) : "—"}
                    </span>
                  </div>
                )}
                {pick.risk.entry_price != null && (
                  <div className="pick-modal-price-cell">
                    <span className="pick-modal-price-label">Entry</span>
                    <span className="pick-modal-price-value">{fmtPrice(pick.risk.entry_price)}</span>
                  </div>
                )}
                {pick.risk.target_price != null && (
                  <div className="pick-modal-price-cell">
                    <span className="pick-modal-price-label">Target</span>
                    <span className="pick-modal-price-value pick-modal-price-value-target">
                      {fmtPrice(pick.risk.target_price)}
                    </span>
                  </div>
                )}
                {pick.risk.stop_loss != null && (
                  <div className="pick-modal-price-cell">
                    <span className="pick-modal-price-label">Stop loss</span>
                    <span className="pick-modal-price-value pick-modal-price-value-stop">
                      {fmtPrice(pick.risk.stop_loss)}
                    </span>
                  </div>
                )}
              </div>
            </section>
          )}

          {/* What could change the view */}
          <section className="pick-modal-section" data-test="pick-modal-could-change">
            <h4>What could change the view</h4>
            <p>{pick.risk.what_changed_text ?? plainWhatCouldChange(action)}</p>
          </section>

          {/* Risk / invalidation */}
          <section className="pick-modal-section" data-test="pick-modal-risk-level">
            <h4>Risk / invalidation</h4>
            <div className="pick-modal-risk-level">
              <span className="pick-modal-risk-dot" data-level={risk} />
              <span>{riskLevelText(risk)}</span>
            </div>
            {pick.risk.invalidation_text && (
              <p style={{ marginTop: 12 }}>
                <strong>Invalidation:</strong> {pick.risk.invalidation_text}
              </p>
            )}
          </section>

          {/* Catalysts & filings */}
          <section className="pick-modal-section" data-test="pick-modal-catalysts">
            <h4>Catalysts &amp; filings</h4>
            {events.status === "loading" && <p style={{ color: "var(--pi-ink-faint)" }}>Loading…</p>}
            {events.status === "not-connected" && (
              <p style={{ color: "var(--pi-ink-muted)" }}>
                Catalyst feed not connected yet. Wire a Polygon, Benzinga, or
                SEC EDGAR provider through <code>/api/asset/{pick.symbol}/events</code>.
              </p>
            )}
            {events.status === "empty" && (
              <p style={{ color: "var(--pi-ink-muted)" }}>No fresh catalysts for {pick.symbol}.</p>
            )}
            {events.status === "ready" && pick.symbol && (() => {
              const ev = events.data.symbols[pick.symbol];
              if (!ev) return <p style={{ color: "var(--pi-ink-muted)" }}>No catalysts for {pick.symbol}.</p>;
              const earnUp = ev.earnings.find(e => e.status === "upcoming");
              return (
                <div>
                  {earnUp && (
                    <p><strong>Next earnings:</strong> {earnUp.date} ({earnUp.type})</p>
                  )}
                  {ev.filings.length > 0 && (
                    <>
                      <p style={{ marginTop: 12 }}><strong>Recent filings</strong></p>
                      <ul>
                        {ev.filings.slice(0, 3).map((f, i) => (
                          <li key={i}>
                            <a href={f.url} target="_blank" rel="noopener noreferrer">{f.form}</a> · {f.filed_at.slice(0, 10)}
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                  {ev.news.length > 0 && (
                    <>
                      <p style={{ marginTop: 12 }}><strong>Recent news</strong></p>
                      <ul>
                        {ev.news.slice(0, 4).map((n, i) => (
                          <li key={i}>
                            <a href={n.url} target="_blank" rel="noopener noreferrer">{n.title}</a>
                            <div style={{ fontSize: 11, color: "var(--pi-ink-faint)" }}>{n.source}</div>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              );
            })()}
          </section>

          {/* Technical details — collapsed */}
          <section className="pick-modal-section" data-test="pick-modal-technical">
            <div className="pick-modal-tech">
              <button
                type="button"
                className="pick-modal-tech-toggle"
                onClick={() => setTechOpen(o => !o)}
                aria-expanded={techOpen}
              >
                <span>Technical details</span>
                <span>{techOpen ? "−" : "+"}</span>
              </button>

              {techOpen && (
                <div className="pick-modal-tech-body">
                  <dl>
                    <dt>Raw action</dt>
                    <dd>{pick.raw_action || "—"}</dd>
                    {pick.raw_adjusted_action && (
                      <>
                        <dt>Adjusted action</dt>
                        <dd>{pick.raw_adjusted_action}</dd>
                      </>
                    )}
                    <dt>Confidence</dt>
                    <dd>{pick.confidence ?? "—"}</dd>
                    {pick.composite_score != null && (
                      <>
                        <dt>Composite score</dt>
                        <dd>{String(pick.composite_score)}</dd>
                      </>
                    )}
                    {pick.engine_version && (
                      <>
                        <dt>Engine version</dt>
                        <dd>{pick.engine_version}</dd>
                      </>
                    )}
                    {pick.generated_at && (
                      <>
                        <dt>Generated at</dt>
                        <dd>{new Date(pick.generated_at).toLocaleString()}</dd>
                      </>
                    )}
                    {Object.keys(pick.family_scores ?? {}).length > 0 && (
                      <>
                        <dt>Family scores</dt>
                        <dd>
                          {Object.entries(pick.family_scores).map(([k, v]) => (
                            <div key={k}>{k}: {String(v)}</div>
                          ))}
                        </dd>
                      </>
                    )}
                  </dl>

                  {topEvidence.length > 0 && (
                    <>
                      <h4 style={{ marginTop: 16 }}>Supporting factors</h4>
                      <ul className="pick-evidence-list" style={{ marginTop: 8 }}>
                        {topEvidence.map((ev, i) => (
                          <li key={`${ev.factor_key}-${i}`} className="pick-evidence-item">
                            <div className="pick-evidence-factor">
                              {ev.family ? `${ev.family} · ` : ""}{ev.factor_key}
                            </div>
                            {ev.narrative}
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              )}
            </div>
          </section>

          {/* Footer */}
          <footer className="pick-modal-footer">
            Read-only research — paper trading only. Not financial advice.
          </footer>
        </div>
      )}
    </div>
  );
}
