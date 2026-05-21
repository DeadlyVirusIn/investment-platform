// EducationalDrawer — slide-over explainer for any Copilot card.
//
// Renders four canonical sections sourced from server-side templates
// (decision_framing / checklist / interpretation_guardrails). NEVER
// invents text at runtime — every block is either passed-in or
// rendered as an honest "not captured" empty state.
//
// Sections (locked order):
//   1. Why this strategy fits
//   2. Why this expiry
//   3. What invalidates this setup
//   4. How theta / IV affect this trade
//
// Open/close controlled by parent. Pure presentation. No fetches.

import { ReactNode, useEffect } from "react";

import { cn } from "@/lib/cn";


export interface EducationalDrawerProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  strategyName?: string | null;
  whyStrategy?: string | null;
  whyExpiry?: string | null;
  whatInvalidates?: ReadonlyArray<string> | null;
  thetaIvImpact?: string | null;
  /** Phase B7 — catalyst section. When `catalystTitle` is null the
   *  whole section renders as an honest "no catalyst in window"
   *  empty state. */
  catalystTitle?: string | null;
  catalystDate?: string | null;
  catalystDaysAway?: number | null;
  catalystImportance?: string | null;
  catalystExplanation?: string | null;
  /** Trailing footer node (e.g. links to research). */
  footer?: ReactNode;
}

function Section({
  heading, body,
}: { heading: string; body: ReactNode }) {
  return (
    <section className="opt-edu-section">
      <h4 className="opt-edu-heading">{heading}</h4>
      <div className="opt-edu-body">{body}</div>
    </section>
  );
}

function emptyText(s: string | null | undefined): ReactNode {
  if (!s) {
    return <span className="opt-caption-muted">
      Not captured for this setup yet.
    </span>;
  }
  return <p className="opt-edu-paragraph">{s}</p>;
}

export default function EducationalDrawer({
  open, onClose, title = "Why this setup",
  strategyName, whyStrategy, whyExpiry,
  whatInvalidates, thetaIvImpact,
  catalystTitle, catalystDate,
  catalystDaysAway, catalystImportance, catalystExplanation,
  footer,
}: EducationalDrawerProps) {
  // Close on Escape — minimal a11y. No focus trap (Phase A scope).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="opt-edu-overlay" data-test="opt-edu-overlay"
         onClick={onClose}>
      <aside
        className={cn("opt-edu-drawer")}
        data-test="opt-edu-drawer"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="opt-edu-header">
          <div>
            <div className="opt-edu-eyebrow">AI Strategist · explanation</div>
            <h3 className="opt-edu-title">{title}</h3>
            {strategyName && (
              <div className="opt-edu-strategy">{strategyName}</div>
            )}
          </div>
          <button type="button" className="opt-edu-close"
                  onClick={onClose}
                  data-test="opt-edu-close"
                  aria-label="Close explanation">×</button>
        </header>

        <Section heading="Why this strategy fits"
                 body={emptyText(whyStrategy)} />
        <Section heading="Why this expiry"
                 body={emptyText(whyExpiry)} />
        <Section heading="What invalidates this setup"
                 body={
                   !whatInvalidates || whatInvalidates.length === 0
                     ? emptyText(null)
                     : <ul className="opt-edu-list">
                         {whatInvalidates.map((p, i) => (
                           <li key={i}>{p}</li>
                         ))}
                       </ul>
                 } />
        <Section heading="Why this catalyst matters"
                 body={
                   !catalystTitle ? emptyText(null) : (
                     <>
                       <p className="opt-edu-paragraph opt-edu-catalyst-head">
                         <strong>{catalystTitle}</strong>
                         {catalystDate && (
                           <> · {catalystDate}{
                             catalystDaysAway != null
                               ? ` (T-${catalystDaysAway}d)` : ""
                           }</>
                         )}
                         {catalystImportance && (
                           <> · {catalystImportance} importance</>
                         )}
                       </p>
                       {catalystExplanation && (
                         <p className="opt-edu-paragraph">
                           {catalystExplanation}
                         </p>
                       )}
                     </>
                   )
                 } />
        <Section heading="How theta / IV affect this trade"
                 body={emptyText(thetaIvImpact)} />

        {footer && <footer className="opt-edu-footer">{footer}</footer>}
      </aside>
    </div>
  );
}
