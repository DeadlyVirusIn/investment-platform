// UX-5B Phase B-2 — Block 2: what's open.
//
// One observed sentence + a single "See my holdings" link.
// No counts as chips. No state-clause as a badge. The clause
// (when truthful) appends to the count sentence as inline prose.

import { Link } from "react-router-dom";

import type { HoldingsSummaryOutput } from "@/lib/copilot/overview_derive";


export interface HoldingsSummaryProps {
  data: HoldingsSummaryOutput;
  className?: string;
}


export default function HoldingsSummary(
  { data, className }: HoldingsSummaryProps,
) {
  // The state-clause is OPTIONAL. When present, it appends as
  // a second sentence: "3 paper positions. All quietly working."
  // When null (mark price not yet wired), only the count
  // sentence renders. No placeholder, no chip, no "—".
  const sentence = data.stateClause
    ? `${data.countSentence} ${data.stateClause}.`
    : data.countSentence;

  return (
    <section
      className={className}
      data-test="copilot-holdings-summary"
      data-source={data.dataSource}
      aria-labelledby="copilot-holdings-summary-h"
    >
      <h2
        id="copilot-holdings-summary-h"
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
        What's open
      </h2>
      <p
        style={{
          margin: "8px 0 0",
          fontSize: "var(--copilot-type-15)",
          lineHeight: "var(--copilot-prose-line-height)",
          maxWidth: "var(--copilot-prose-max-width)",
          color: "inherit",
        }}
        data-test="copilot-holdings-summary-body"
      >
        {sentence}
      </p>
      <div style={{ marginTop: 8 }}>
        <Link
          to={data.linkHref}
          data-test="copilot-holdings-summary-link"
          style={{
            fontSize: "var(--copilot-type-13)",
            opacity: 0.7,
            color: "inherit",
            textDecoration: "underline",
          }}
        >
          {data.linkText} →
        </Link>
      </div>
    </section>
  );
}
