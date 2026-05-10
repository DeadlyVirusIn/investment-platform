// PickModal — research cockpit overlay.
//
// Sections (rendered conditionally; missing data hides cleanly):
//   - Header: symbol + ACTION badge + close
//   - Action summary (confidence + freshness + engine)
//   - Reference price strip (latest close + entry/target/stop if present)
//   - AI thesis
//   - Risk / invalidation (callout if present)
//   - Supporting factors (top 4 from evidence with narratives)
//   - What changed (if rationale provides it)
//   - Next thing to watch (if rationale provides it)
//   - Paper trading disclaimer + generated_at

import { useEffect, useRef, useState } from "react";

import type { Pick, LatestPrice } from "@/lib/picks/api";
import {
  confidenceLabel, fmtConfidencePct, fetchLatestPrice,
} from "@/lib/picks/api";


export interface PickModalProps {
  pick: Pick | null;
  /** Optional cached price from the grid (avoids re-fetch). */
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


export default function PickModal({ pick, priceCache, onClose }: PickModalProps) {
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const [price, setPrice] = useState<LatestPrice | null | undefined>(undefined);

  // Use cached price if provided; otherwise lazy-fetch on open
  useEffect(() => {
    if (!pick?.symbol) {
      setPrice(undefined);
      return;
    }
    if (priceCache !== undefined) {
      setPrice(priceCache);
      return;
    }
    setPrice(undefined);
    let cancelled = false;
    fetchLatestPrice(pick.symbol).then(p => {
      if (!cancelled) setPrice(p);
    });
    return () => { cancelled = true; };
  }, [pick?.symbol, pick?.id, priceCache]);

  // ESC dismiss + body scroll lock + focus trap
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

  // Top 4 evidence items with narratives
  const topEvidence = pick?.evidence
    ?.filter(e => e.narrative && e.narrative.length > 0)
    .slice(0, 4) ?? [];

  // Conditional risk fields
  const hasRiskCallout = pick && (pick.risk.invalidation_text || pick.risk.risk_text);
  const hasPrices = pick && (
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

          {/* Action summary */}
          <div className="pick-modal-action-row">
            <span className="pick-modal-action-badge">{action}</span>
            <span><strong>{confidenceLabel(confidence)}</strong> confidence · {fmtConfidencePct(confidence)}</span>
            {pick.stale_data && <span style={{ color: "var(--picks-sell)" }}>· stale data</span>}
            {!pick.enough_data && <span style={{ color: "var(--picks-sell)" }}>· thin data</span>}
          </div>

          {/* Reference price strip — shown if any price field present */}
          {hasPrices && (
            <div className="pick-modal-prices" data-test="pick-modal-prices">
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
                  <span className="pick-modal-price-value">
                    {fmtPrice(pick.risk.entry_price)}
                  </span>
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
          )}

          {/* AI thesis */}
          {pick.thesis && (
            <section className="pick-modal-section" data-test="pick-modal-thesis">
              <h4>AI thesis</h4>
              <p>{pick.thesis}</p>
            </section>
          )}

          {/* Risk / invalidation callout */}
          {hasRiskCallout && (
            <section className="pick-modal-section pick-modal-section-risk" data-test="pick-modal-risk">
              <h4>Risk · invalidation</h4>
              {pick.risk.invalidation_text && <p>{pick.risk.invalidation_text}</p>}
              {pick.risk.risk_text && pick.risk.risk_text !== pick.risk.invalidation_text && (
                <p style={{ marginTop: 8 }}>{pick.risk.risk_text}</p>
              )}
            </section>
          )}

          {/* Supporting factors */}
          {topEvidence.length > 0 && (
            <section className="pick-modal-section" data-test="pick-modal-factors">
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

          {/* What changed */}
          {pick.risk.what_changed_text && (
            <section className="pick-modal-section" data-test="pick-modal-changed">
              <h4>What changed</h4>
              <p>{pick.risk.what_changed_text}</p>
            </section>
          )}

          {/* Next watch */}
          {pick.risk.next_watch_text && (
            <section className="pick-modal-section" data-test="pick-modal-next">
              <h4>Next thing to watch</h4>
              <p>{pick.risk.next_watch_text}</p>
            </section>
          )}

          {/* Footer */}
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
