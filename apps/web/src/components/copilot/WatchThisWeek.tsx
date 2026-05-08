// UX-5B Phase B-2 — Block 6: what to watch this week.
//
// Translated event list (R-D). Returns null when derive returned
// null (R-E). Never surfaces raw event codes (CPI, FOMC, NFP);
// the translation map in overview_copy.ts is the only legitimate
// source of rendered text.

import type { WatchOutput } from "@/lib/copilot/overview_derive";
import { WATCH } from "@/lib/copilot/overview_copy";


export interface WatchThisWeekProps {
  data: WatchOutput | null;
  className?: string;
}


export default function WatchThisWeek(
  { data, className }: WatchThisWeekProps,
) {
  if (!data) return null;
  return (
    <section
      className={className}
      data-test="copilot-watch-week"
      data-source={data.dataSource}
      aria-labelledby="copilot-watch-week-h"
    >
      <h2
        id="copilot-watch-week-h"
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
        {WATCH.header}
      </h2>
      <ul
        style={{
          listStyle: "none",
          padding: 0,
          margin: "8px 0 0",
          display: "flex",
          flexDirection: "column",
          gap: 6,
        }}
      >
        {data.lines.map((l, i) => (
          <li
            key={i}
            data-test="copilot-watch-week-line"
            style={{
              fontSize: "var(--copilot-type-15)",
              lineHeight: "var(--copilot-prose-line-height)",
              maxWidth: "var(--copilot-prose-max-width)",
              color: "inherit",
            }}
          >
            {l}
          </li>
        ))}
      </ul>
    </section>
  );
}
