// OptionsRationale — bulleted rationale block.
//
// Renders the AI's reasoning behind a setup, sourced from:
//   * shadow_decision_log.diagnostics (gate-by-gate reasoning)
//   * decision_framing/narratives output (human-language paragraph)
//
// Both inputs are server-generated. This component renders the
// already-quoted text — it never composes new narrative. Stale
// values must remain visible rather than hidden.

import { cn } from "@/lib/cn";

export interface OptionsRationaleProps {
  /** Short headline summary — 1 sentence. */
  headline?: string | null;
  /** Bulleted points — typically 2-5 entries. */
  points?: ReadonlyArray<string>;
  /** Optional template name surfaced as eyebrow ("trend_continuation"). */
  templateName?: string | null;
  className?: string;
}

export default function OptionsRationale({
  headline, points, templateName, className,
}: OptionsRationaleProps) {
  const hasContent = !!headline || (points && points.length > 0);

  if (!hasContent) {
    return (
      <div className={cn("opt-rationale opt-rationale-empty", className)}>
        <span className="opt-caption-muted">No rationale captured.</span>
      </div>
    );
  }

  return (
    <div className={cn("opt-rationale", className)}
         data-test="opt-rationale">
      {templateName && (
        <div className="opt-rationale-eyebrow">
          Template · {templateName.replace(/_/g, " ")}
        </div>
      )}
      {headline && (
        <p className="opt-rationale-headline">{headline}</p>
      )}
      {points && points.length > 0 && (
        <ul className="opt-rationale-points">
          {points.map((p, i) => (
            <li key={i} className="opt-rationale-point">{p}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
