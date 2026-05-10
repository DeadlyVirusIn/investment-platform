// PickModal — overlay showing full pick details.
//
// Sections:
//   - Symbol + ACTION badge + confidence
//   - Latest price (lazy-fetched on open)
//   - AI reasoning (thesis + evidence narratives)
//   - Generated metadata
//
// Dismiss: click overlay, ESC, close button.

import { useEffect, useRef, useState } from "react";

import type { Pick, LatestPrice } from "@/lib/picks/api";
import { confidenceLabel, fmtConfidencePct, fetchLatestPrice } from "@/lib/picks/api";


export interface PickModalProps {
  pick: Pick | null;
  onClose: () => void;
}


function fmtPrice(p: number | null): string {
  if (p == null) return "—";
  return `$${p.toFixed(2)}`;
}


export default function PickModal({ pick, onClose }: PickModalProps) {
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const [price, setPrice] = useState<LatestPrice | null>(null);
  const [priceLoading, setPriceLoading] = useState(false);

  // Fetch latest price when pick changes (modal opens for new symbol)
  useEffect(() => {
    if (!pick?.symbol) {
      setPrice(null);
      return;
    }
    setPriceLoading(true);
    setPrice(null);
    let cancelled = false;
    fetchLatestPrice(pick.symbol).then(p => {
      if (!cancelled) {
        setPrice(p);
        setPriceLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [pick?.symbol, pick?.id]);

  // ESC dismiss + body scroll lock + focus trap to close button
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
  const action = pick ? (pick.adjusted_action ?? pick.action) as "buy" | "sell" | "hold" : "hold";
  const confidence = pick ? (pick.adjusted_confidence ?? pick.confidence) : null;

  // Top 3 evidence items with narratives
  const topEvidence = pick?.evidence
    ?.filter(e => e.narrative && e.narrative.length > 0)
    .slice(0, 4) ?? [];

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
          <header className="pick-modal-header">
            <div>
              <h2 id="pick-modal-symbol" className="pick-modal-symbol">
                {pick.symbol ?? "—"}
              </h2>
              <div className="pick-modal-symbol-sub">
                {pick.engine_version ? `engine ${pick.engine_version}` : "AI suggestion"}
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

          <div className="pick-modal-action-row">
            <span className="pick-modal-action-badge">{action}</span>
            <span>{confidenceLabel(confidence)} confidence · {fmtConfidencePct(confidence)}</span>
          </div>

          {/* Latest price — lazy-loaded */}
          <section className="pick-modal-section">
            <h4>{action === "buy" ? "Buy reference price" : action === "sell" ? "Sell reference price" : "Reference price"}</h4>
            <div className="pick-price-line">
              {priceLoading && <span className="pick-price-loading">Loading latest…</span>}
              {!priceLoading && price && (
                <>
                  Latest close: {fmtPrice(price.close)}
                  <span style={{ color: "var(--picks-ink-meta)", marginLeft: 8 }}>
                    ({new Date(price.ts).toLocaleDateString()})
                  </span>
                </>
              )}
              {!priceLoading && !price && (
                <span className="pick-price-loading">Price unavailable for this symbol.</span>
              )}
            </div>
          </section>

          {/* AI reasoning — thesis */}
          <section className="pick-modal-section">
            <h4>Why the AI suggests this</h4>
            <p>{pick.thesis ?? "No thesis returned by the engine. See evidence factors below."}</p>
          </section>

          {/* Evidence factors */}
          {topEvidence.length > 0 && (
            <section className="pick-modal-section">
              <h4>Supporting factors</h4>
              <ul className="pick-evidence-list">
                {topEvidence.map((ev, i) => (
                  <li key={`${ev.factor_key}-${i}`} className="pick-evidence-item">
                    <div className="pick-evidence-factor">
                      {ev.family ? `${ev.family} · ` : ""}{ev.factor_key}
                    </div>
                    {ev.narrative}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <footer className="pick-modal-footer">
            Read-only research — paper trading. Not financial advice.
            {pick.generated_at && (
              <> Generated {new Date(pick.generated_at).toLocaleString()}.</>
            )}
          </footer>
        </div>
      )}
    </div>
  );
}
