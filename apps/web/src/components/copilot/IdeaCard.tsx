// UX-5B Phase B-2 — IdeaCard primitive.
//
// One-shot observational card. Renders:
//   {Symbol}  · Today
//   {observation sentence}
//
// NO scores. NO confidence. NO conviction language. NO chart.
// NO chip. NO ranking. Per UX-5B refinement R-A — Block 3 stays
// observational always. The composer (deriveIdeaCard) physically
// cannot accept score / conviction inputs; this primitive
// renders only the structured output.
//
// Emotional rule: this card should feel like the second
// paragraph of an editorial daily letter, not a trading signal.

import type { IdeaCardOutput } from "@/lib/copilot/overview_derive";


export interface IdeaCardProps {
  data: IdeaCardOutput;
  className?: string;
}


export default function IdeaCard({ data, className }: IdeaCardProps) {
  return (
    <article
      className={className}
      data-test="copilot-idea-card"
      data-symbol={data.symbol}
      data-source={data.dataSource}
      style={{
        margin: 0,
        // Spacing-driven separation: each idea card sits on the
        // page rhythm, NOT inside a box. The parent <section>
        // controls inter-card vertical gap.
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          columnGap: 8,
          rowGap: 4,
          flexWrap: "wrap",
          fontSize: "var(--copilot-type-15)",
        }}
      >
        <span
          data-test="copilot-idea-symbol"
          style={{ fontWeight: 600, letterSpacing: 0 }}
        >
          {data.symbol}
        </span>
        <span
          data-test="copilot-idea-temporal"
          style={{
            fontSize: "var(--copilot-type-13)",
            opacity: 0.7,
            fontWeight: 400,
          }}
        >
          · {data.temporal}
        </span>
      </header>
      <p
        data-test="copilot-idea-observation"
        style={{
          margin: "4px 0 0",
          fontSize: "var(--copilot-type-15)",
          lineHeight: "var(--copilot-prose-line-height)",
          maxWidth: "var(--copilot-prose-max-width)",
          color: "inherit",
        }}
      >
        {data.observation}
      </p>
    </article>
  );
}
