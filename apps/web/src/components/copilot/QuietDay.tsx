// UX-3D Phase A — Quiet Day component.
//
// One of the 5 signature elements (UX-3C §3a). Closed component.
// NO additions allowed (no "tip of the day", no callouts, no
// illustration, no extra slot). The page being confidently empty
// is the brand.
//
// Renders the first-time onboarding clause inline ONCE, suppressed
// thereafter via the ux_seen_quiet_day flag.

import { useEffect, useState } from "react";

import { ONBOARDING_CLAUSES, QUIET_DAY_COPY } from "@/lib/copilot/copy";
import { hasSeen, markSeen } from "@/lib/copilot/onboarding";


export interface QuietDayProps {
  /** Optional className passthrough. */
  className?: string;
}


export default function QuietDay({ className }: QuietDayProps) {
  // The onboarding clause is rendered only on the first encounter.
  // We resolve `seen` after mount so SSR / SSG doesn't fix the value
  // before localStorage is available.
  const [seen, setSeen] = useState(true);
  useEffect(() => {
    if (!hasSeen("ux_seen_quiet_day")) {
      setSeen(false);
      // Mark as seen at mount time so a refresh during the same
      // session doesn't double-render the clause.
      markSeen("ux_seen_quiet_day");
    }
  }, []);

  return (
    <section
      data-test="copilot-quiet-day"
      className={className}
      style={{
        textAlign: "center",
        padding: "48px 24px",
        maxWidth: "var(--copilot-prose-max-width)",
        margin: "0 auto",
      }}
    >
      <span
        aria-hidden="true"
        style={{
          display: "inline-block",
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: "var(--copilot-dot-calm)",
          marginBottom: 16,
        }}
      />
      <h2
        data-test="copilot-quiet-day-headline"
        style={{
          fontSize: "var(--copilot-type-24)",
          fontWeight: 500,
          margin: "0 0 12px",
          color: "inherit",
          lineHeight: 1.3,
        }}
      >
        {QUIET_DAY_COPY.headline}
      </h2>
      <p
        data-test="copilot-quiet-day-body"
        style={{
          fontSize: "var(--copilot-type-15)",
          lineHeight: "var(--copilot-prose-line-height)",
          margin: 0,
          opacity: 0.85,
        }}
      >
        {QUIET_DAY_COPY.body}
      </p>
      {!seen && (
        <p
          data-test="copilot-quiet-day-onboarding"
          style={{
            marginTop: 20,
            fontSize: "var(--copilot-type-13)",
            opacity: 0.6,
            lineHeight: 1.55,
          }}
        >
          {ONBOARDING_CLAUSES.ux_seen_quiet_day}
        </p>
      )}
    </section>
  );
}
