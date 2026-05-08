// UX-5B Phase B-2 — Block 1: greeting + today line.
//
// Pure render. Receives the structured shape from
// deriveTodayLine() and surfaces it as one editorial header
// + one short paragraph (or the catching-up sentence when
// the daily-loop is in recovery mode).
//
// No borders, no boxes, no charts, no chips. Spacing +
// typography ONLY. The greeting reads like an editorial lede;
// the body sentence(s) read like the first paragraph of a
// daily letter.

import type { TodayLineOutput } from "@/lib/copilot/overview_derive";


export interface TodayLineProps {
  data: TodayLineOutput;
  className?: string;
}


export default function TodayLine({ data, className }: TodayLineProps) {
  // System-reviewed + market line are joined into a single
  // paragraph so the eye reads them as one continuous thought
  // rather than two stacked statements.
  const body = data.catchingUp
    ? data.catchingUp
    : [data.systemReviewed, data.marketLine]
        .filter(Boolean)
        .join(" ");

  return (
    <header
      className={className}
      data-test="copilot-today-line"
      data-source={data.dataSource}
    >
      <h1
        style={{
          fontSize: "var(--copilot-type-24)",
          fontWeight: 500,
          margin: 0,
          letterSpacing: "-0.01em",
          color: "inherit",
        }}
        data-test="copilot-today-greeting"
      >
        {data.greeting}
      </h1>
      {body && (
        <p
          style={{
            margin: "12px 0 0",
            fontSize: "var(--copilot-type-15)",
            lineHeight: "var(--copilot-prose-line-height)",
            opacity: 0.95,
            maxWidth: "var(--copilot-prose-max-width)",
            color: "inherit",
          }}
          data-test="copilot-today-body"
        >
          {body}
        </p>
      )}
    </header>
  );
}
