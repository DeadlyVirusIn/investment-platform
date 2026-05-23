// UX-11 Phase 11C — ReasoningDrawer component.
//
// Source of truth: docs/research/UX_11_INTERACTIVE_COPILOT.md
//   Section 6 (ReasoningDrawer spec)
//
// Modal sheet at 88vh desktop / 92vh mobile. 9 sections single
// continuous scroll. Invalidation moved one slot earlier (Codex
// R1 contribution). 220ms cubic-bezier(0.32, 0.72, 0, 1) iOS
// curve. 5 dismiss paths. URL state hook drives open/close.

import { useEffect, useRef } from "react";

import type { ActionCardData } from "@/lib/copilot/conviction_card_schema";
import { freshnessTimestamp } from "@/lib/copilot/conviction_card_schema";

import VerbPill from "./VerbPill";
import TierGlyph from "./TierGlyph";


export interface ReasoningDrawerProps {
  card: ActionCardData | null;     // null when no drawer open
  isOpen: boolean;
  onClose: () => void;
}


export default function ReasoningDrawer({ card, isOpen, onClose }: ReasoningDrawerProps) {
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  // ESC dismiss
  useEffect(() => {
    if (!isOpen) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  // Focus drawer close button on open; lock body scroll
  useEffect(() => {
    if (!isOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeBtnRef.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isOpen]);

  return (
    <>
      {/* Backdrop — visible whenever isOpen, fades via CSS */}
      <div
        className="ux11-drawer-backdrop"
        data-open={isOpen ? "true" : "false"}
        data-test="ux11-drawer-backdrop"
        onClick={onClose}
        aria-hidden="true"
      />

      <div
        ref={drawerRef}
        className="ux11-drawer"
        data-open={isOpen ? "true" : "false"}
        data-test="ux11-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ux11-drawer-title"
        aria-hidden={!isOpen}
      >
        <div className="ux11-drawer-handle" aria-hidden="true" />

        <header className="ux11-drawer-header">
          <h2
            id="ux11-drawer-title"
            style={{
              margin: 0,
              fontSize: "var(--ux10-fs-h2)",
              fontWeight: 500,
              color: "var(--ux10-fg-primary)",
            }}
          >
            {card ? `${card.ticker} · ${card.thesisName}` : ""}
          </h2>
          <button
            ref={closeBtnRef}
            type="button"
            className="ux11-drawer-close"
            onClick={onClose}
            data-test="ux11-drawer-close"
            aria-label="Close reasoning drawer"
          >
            ×
          </button>
        </header>

        <div className="ux11-drawer-content">
          {card && (
            <>
              {/* Section 1: Recap header */}
              <section className="ux11-drawer-section" data-test="ux11-section-recap">
                <h3>Recap</h3>
                <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 12 }}>
                  <VerbPill verb={card.verb} />
                  <TierGlyph tier={card.confidenceTier} />
                  <span style={{ fontSize: "var(--ux10-fs-meta)", color: "var(--ux10-fg-tertiary)", fontFamily: "var(--ux10-font-mono)" }}>
                    {card.freshnessState} · {freshnessTimestamp(card.lastReviewedAt)}
                  </span>
                </div>
                <p>{card.decisionSentence}</p>
              </section>

              {/* Section 2: Invalidation — moved earlier per Codex R1 */}
              <section className="ux11-drawer-section" data-test="ux11-section-invalidation">
                <h3>What would break this</h3>
                <div style={{
                  borderLeft: "2px solid var(--ux10-risk)",
                  padding: "6px 0 6px 12px",
                  background: "rgba(194, 74, 74, 0.04)",
                }}>
                  <p>{card.invalidation}</p>
                </div>
              </section>

              {/* Section 3: Driver / Counter / Catalyst */}
              <section className="ux11-drawer-section" data-test="ux11-section-thesis">
                <h3>Driver · Counter · Catalyst</h3>
                <div className="ux11-drawer-thesis-grid">
                  <div>
                    <h4 style={{ fontSize: "var(--ux10-fs-meta)", textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--ux10-fg-tertiary)", margin: "0 0 6px 0", fontWeight: 600 }}>
                      Driver (bull)
                    </h4>
                    <p>{card.thesis.driver}</p>
                  </div>
                  <div>
                    <h4 style={{ fontSize: "var(--ux10-fs-meta)", textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--ux10-fg-tertiary)", margin: "0 0 6px 0", fontWeight: 600 }}>
                      Counter (bear)
                    </h4>
                    <p>{card.thesis.counter}</p>
                  </div>
                </div>
                <p style={{ marginTop: 12, paddingTop: 12, borderTop: "1px dashed var(--ux10-border-card)", color: "var(--ux10-fg-secondary)" }}>
                  <strong style={{ letterSpacing: "0.04em", color: "var(--ux10-fg-tertiary)" }}>
                    Catalyst —{" "}
                  </strong>
                  {card.thesis.catalyst}
                </p>
              </section>

              {/* Section 4: Target / Horizon / Structure */}
              <section className="ux11-drawer-section" data-test="ux11-section-target">
                <h3>Target · Horizon · Structure</h3>
                <p style={{ fontFamily: "var(--ux10-font-mono)" }}>
                  Entry {card.target.entry}
                  {card.target.t1 && ` · T1 ${card.target.t1}`}
                  {card.target.t2 && ` · T2 ${card.target.t2}`}
                  {card.target.t3 && ` · T3 ${card.target.t3}`}
                </p>
                <p style={{ color: "var(--ux10-fg-secondary)" }}>
                  Horizon: {card.horizon}
                  {card.riskTags.length > 0 && ` · Risks: ${card.riskTags.join(", ")}`}
                </p>
                <p style={{ color: "var(--ux10-fg-tertiary)", fontSize: "var(--ux10-fs-meta)" }}>
                  Valid until {card.expiryCondition}
                </p>
              </section>

              {/* Section 5: What changed */}
              <section className="ux11-drawer-section" data-test="ux11-section-changed">
                <h3>What changed since last review</h3>
                <p style={{ color: "var(--ux10-fg-secondary)", fontStyle: "italic" }}>
                  Composer wires this section in Phase 11G with real
                  decision_log diff data. Today: no change since last review.
                </p>
              </section>

              {/* Section 6: Compared candidates */}
              <section className="ux11-drawer-section" data-test="ux11-section-compared">
                <h3>Compared candidates</h3>
                <p style={{ color: "var(--ux10-fg-secondary)", fontStyle: "italic" }}>
                  Composer wires this section in Phase 11G with
                  compared_candidates table. Today: placeholder.
                </p>
              </section>

              {/* Section 7: My pattern */}
              <section className="ux11-drawer-section" data-test="ux11-section-pattern">
                <h3>My pattern with this AI</h3>
                <p style={{ color: "var(--ux10-fg-secondary)", fontStyle: "italic" }}>
                  Composer wires this section in Phase 11G with user_pattern
                  view. Today: placeholder.
                </p>
              </section>

              {/* Section 8: Calibration */}
              <section className="ux11-drawer-section" data-test="ux11-section-calibration">
                <h3>Calibration</h3>
                <p style={{ color: "var(--ux10-fg-secondary)" }}>
                  Current{" "}
                  <strong style={{ color: "var(--ux10-fg-primary)" }}>
                    {card.confidenceTier}
                  </strong>{" "}
                  tier hit rate (rolling 90d): pending real data wiring.
                </p>
              </section>

              {/* Section 9: Engine version */}
              <footer className="ux11-drawer-section" data-test="ux11-section-footer">
                <p style={{ fontSize: "var(--ux10-fs-meta)", color: "var(--ux10-fg-tertiary)" }}>
                  Engine v0.x · last retrained pending Phase 11G wiring.
                  Automated research signal · paper trading only · educational use only · not financial advice.
                </p>
              </footer>
            </>
          )}
        </div>
      </div>
    </>
  );
}
