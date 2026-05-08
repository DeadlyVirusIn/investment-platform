// UX-5B Phase B-2 — Block 5: risk line (conditional).
//
// Renders only when deriveRiskLine produced a non-null output —
// drawdown ≥ 5%, stress regime, or paused-strategy count > 0.
// On any other day this block is silent (R-E + Strategic lock A).
//
// No alarming colour. No bright red. The composition is
// editorial: a quiet header + 1–2 short sentences. The user
// reads it as observation, not warning.

import type { RiskLineOutput } from "@/lib/copilot/overview_derive";
import { RISK_LINE } from "@/lib/copilot/overview_copy";


export interface RiskLineProps {
  data: RiskLineOutput | null;
  className?: string;
}


export default function RiskLine({ data, className }: RiskLineProps) {
  if (!data) return null;
  return (
    <section
      className={className}
      data-test="copilot-risk-line"
      data-source={data.dataSource}
      aria-labelledby="copilot-risk-line-h"
    >
      <h2
        id="copilot-risk-line-h"
        style={{
          fontSize: "var(--copilot-type-12)",
          fontWeight: 500,
          letterSpacing: "0.04em",
          textTransform: "uppercase",
          opacity: 0.55,
          margin: 0,
          color: "inherit",
        }}
      >
        {RISK_LINE.header}
      </h2>
      <div
        style={{
          marginTop: 8,
          display: "flex",
          flexDirection: "column",
          gap: 6,
        }}
      >
        {data.sentences.map((s, i) => (
          <p
            key={i}
            data-test="copilot-risk-line-sentence"
            style={{
              margin: 0,
              fontSize: "var(--copilot-type-15)",
              lineHeight: "var(--copilot-prose-line-height)",
              maxWidth: "var(--copilot-prose-max-width)",
              color: "inherit",
            }}
          >
            {s}
          </p>
        ))}
      </div>
    </section>
  );
}
