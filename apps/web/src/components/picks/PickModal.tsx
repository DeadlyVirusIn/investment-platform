// PickModal — copilot-style research view.
//
// Beginner-friendly sections in plain English. Technical details
// hidden behind "Show technical details" toggle.

import { useEffect, useMemo, useRef, useState } from "react";

import type { Pick, LatestPrice } from "@/lib/picks/api";
import {
  confidenceLabel, fetchLatestPrice,
  actionTitle,
} from "@/lib/picks/api";
import { fetchSymbolEvents, type EventsState } from "@/lib/portfolio/events";
// Phase L UI-1 — deterministic reasoning card.
import ReasoningCard from "@/components/decisions/ReasoningCard";


export interface PickModalProps {
  pick: Pick | null;
  priceCache?: LatestPrice | null;
  onClose: () => void;
  // Phase 15f.1 — traversability. When provided, j / k / arrow keys
  // and the footer prev/next buttons walk through the parent's list
  // (filtered as appropriate). Position is rendered as "X of Y" in
  // the footer when both nav callbacks + position are passed.
  onPrev?: () => void;
  onNext?: () => void;
  position?: { current: number; total: number };
  /**
   * PR-2 visual consistency: opt-in calm variant. When set to "calm"
   * the modal renders inside `.today-root` token cascade (no glow,
   * no hover lift, no uppercase labels). Default "legacy" preserves
   * the existing /overview behavior byte-for-byte.
   */
  shellVariant?: "legacy" | "calm";
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


// Phase L UI-1 — the helpers plainWhatThisMeans, plainWhatCouldChange,
// riskLevelText, and buildPlainThesis were removed. They generated
// freeform explanatory prose in the frontend, which violates the
// constitutional guarantee that every visible explanation comes
// from the deterministic backend renderer. The "What this means"
// and "Plain-English thesis" sections now use <ReasoningCard/>
// instead, which sources its text from the backend envelope or
// renders the honest research-preview absence state when no
// decision has attached.


// Phase L UI-1 — riskLevel(pick) was used by the removed
// Risk/Invalidation section. The risk-level dot was a frontend-
// derived heuristic that we no longer present as a meaningful
// signal. The pick.risk.{entry,target,stop_loss} numbers are still
// rendered as Reference Price values — those are factual numbers,
// not interpretive prose.


export default function PickModal({
  pick, priceCache, onClose, onPrev, onNext, position,
  shellVariant = "legacy",
}: PickModalProps) {
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
      // Don't hijack typing into a form field if some embedded input
      // ever captures focus. Modal currently has no inputs but be
      // defensive for future content.
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;

      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      // Phase 15f.1 — traversal keys. Vim-style j/k + arrow keys.
      // No-op if the parent didn't pass nav callbacks (PicksPage's
      // priority-card single-pick context).
      if ((e.key === "j" || e.key === "ArrowRight" || e.key === "ArrowDown") && onNext) {
        e.preventDefault();
        onNext();
        return;
      }
      if ((e.key === "k" || e.key === "ArrowLeft" || e.key === "ArrowUp") && onPrev) {
        e.preventDefault();
        onPrev();
        return;
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [pick, onClose, onPrev, onNext]);

  const isOpen = pick !== null;
  const action = pick ? (pick.adjusted_action ?? pick.action) : "hold";
  const confidence = pick ? (pick.adjusted_confidence ?? pick.confidence) : null;
  // Phase L UI-1 — `risk` removed; no longer surfaced.

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
      data-shell={shellVariant}
      data-test="pick-overlay"
      onClick={onClose}
      aria-hidden={!isOpen}
    >
      {pick && (
        <div
          className="pick-modal"
          data-action={action}
          data-shell={shellVariant}
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

          {/* Signal — big colored badge.
              Phase L UI-1 N.2: confidence percentage rendering
              removed. The engine's conviction band (Low / Medium /
              High) is structured state we keep.
              Cohesion polish: header relabeled "Signal" — this is a
              research-stage row (no attached paper_trade) so calling
              it a "Recommendation" overstates what the system has
              committed to. */}
          <section className="pick-modal-section" data-test="pick-modal-recommendation">
            <h4>Signal</h4>
            <div className="pick-modal-action-row">
              <span className="pick-modal-action-badge">{action}</span>
              <span><strong>{actionTitle(action)}</strong></span>
              {confidenceLabel(confidence) && (
                <span>· {confidenceLabel(confidence)} conviction</span>
              )}
            </div>
          </section>

          {/* AI's reasoning — Phase L UI-1.
              Frontend-generated prose has been REMOVED. The
              ReasoningCard sources every visible word from the
              deterministic backend renderer. Picks are research-
              stage rows that have no attached paper_trade yet, so
              the card renders the honest research-preview state. */}
          <section className="pick-modal-section" data-test="pick-modal-reasoning">
            <h4>AI's reasoning</h4>
            <ReasoningCard
              paperTradeId={null}
              researchPreview
              variant="novice"
            />
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

          {/* Phase L UI-1 — REMOVED:
              "What could change the view" (used plainWhatCouldChange
              + engine.what_changed_text prose),
              "Risk / invalidation" (used riskLevelText prose +
              engine.invalidation_text prose).
              Invalidation now surfaces inside <ReasoningCard/> via
              the deterministic renderer's setup sentence. The
              risk-level dot was a frontend-derived heuristic that
              we no longer present as a meaningful signal. */}

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

          {/* Phase 15f.1 — Traversal nav.
              Renders only when the parent passed at least one of
              onPrev / onNext (PicksPage priority-card context = no
              nav; ActionQueue list context = both). Compact text
              affordance — no large new UI controls per discipline. */}
          {(onPrev || onNext) && (
            <nav
              className="pick-modal-nav"
              aria-label="Walk through review queue"
              data-test="pick-modal-nav"
            >
              <button
                type="button"
                className="pick-modal-nav-btn"
                onClick={onPrev}
                disabled={!onPrev}
                aria-label="Previous pick (k or arrow left)"
              >
                <span aria-hidden="true">←</span>
                <span>Prev</span>
              </button>
              {position && (
                <span className="pick-modal-nav-position" aria-live="polite">
                  {position.current} of {position.total}
                </span>
              )}
              <button
                type="button"
                className="pick-modal-nav-btn"
                onClick={onNext}
                disabled={!onNext}
                aria-label="Next pick (j or arrow right)"
              >
                <span>Next</span>
                <span aria-hidden="true">→</span>
              </button>
              <span className="pick-modal-nav-hint" aria-hidden="true">
                j / k or ← / →
              </span>
            </nav>
          )}

          {/* Footer */}
          <footer className="pick-modal-footer">
            AI-generated research signal · paper trading only · educational use only · not financial advice.
          </footer>
        </div>
      )}
    </div>
  );
}
