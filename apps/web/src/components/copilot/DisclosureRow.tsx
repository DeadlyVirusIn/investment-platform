// UX-3D Phase A — Glance + Detail layered row.
//
// One of the 5 signature elements (UX-3C §3a). Always shows the
// Glance line by default; click reveals Detail inline. No modal,
// no nav, no animation longer than 180ms. Caret affordance ▸ / ▾.
//
// Used by IdeaCard, PositionStoryCard, OptionIdeaCard in later
// phases. Phase A only ships the primitive; nothing mounts it yet.

import { useState, type ReactNode } from "react";

import { DISCLOSURE } from "@/lib/copilot/copy";


export interface DisclosureRowProps {
  /** The Glance line — always visible. Should be ≤ ~80 chars. */
  glance: ReactNode;
  /** The Detail body — revealed on click. Caller composes the
   *  prose; this component only handles state + affordance. */
  detail: ReactNode;
  /** Default-open state. Defaults to false. The first PositionStoryCard
   *  on a fresh browser opens defaulted-open via the parent (per
   *  ux_seen_first_position onboarding). */
  defaultOpen?: boolean;
  /** Optional aria label override for the toggle. */
  ariaLabel?: string;
  className?: string;
}


export default function DisclosureRow({
  glance, detail, defaultOpen = false, ariaLabel, className,
}: DisclosureRowProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div
      data-test="copilot-disclosure-row"
      data-open={open ? "true" : "false"}
      className={className}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={ariaLabel
          ?? (open ? DISCLOSURE.collapseAria : DISCLOSURE.expandAria)}
        className="w-full flex items-center justify-between gap-3 text-left"
        style={{
          background: "transparent",
          border: "none",
          padding: 0,
          cursor: "pointer",
          color: "inherit",
          font: "inherit",
        }}
      >
        <span style={{ flex: 1, minWidth: 0 }}>{glance}</span>
        <span
          aria-hidden="true"
          data-test="copilot-disclosure-caret"
          style={{
            color: "var(--copilot-dot-calm)",
            fontSize: "var(--copilot-type-13)",
            lineHeight: 1,
            flexShrink: 0,
          }}
        >
          {open ? DISCLOSURE.caretOpen : DISCLOSURE.caretClosed}
        </span>
      </button>
      {open && (
        <div
          data-test="copilot-disclosure-detail"
          style={{
            marginTop: 12,
            transition: "opacity 180ms ease-out",
          }}
        >
          {detail}
        </div>
      )}
    </div>
  );
}
