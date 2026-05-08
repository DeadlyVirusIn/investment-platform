// UX-5B Phase B-2 — Block 4: what changed.
//
// Tiny editorial deltas. Caps at 3 sentences (enforced by the
// composer). Returns null when derive returned null (R-E).

import type { WhatChangedOutput } from "@/lib/copilot/overview_derive";
import { WHAT_CHANGED } from "@/lib/copilot/overview_copy";


export interface WhatChangedBlockProps {
  data: WhatChangedOutput | null;
  className?: string;
}


export default function WhatChangedBlock(
  { data, className }: WhatChangedBlockProps,
) {
  if (!data) return null;
  return (
    <section
      className={className}
      data-test="copilot-what-changed"
      data-source={data.dataSource}
      aria-labelledby="copilot-what-changed-h"
    >
      <h2
        id="copilot-what-changed-h"
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
        {WHAT_CHANGED.header}
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
        {data.sentences.map((s, i) => (
          <li
            key={i}
            data-test="copilot-what-changed-item"
            style={{
              fontSize: "var(--copilot-type-15)",
              lineHeight: "var(--copilot-prose-line-height)",
              maxWidth: "var(--copilot-prose-max-width)",
              color: "inherit",
            }}
          >
            {s}
          </li>
        ))}
      </ul>
    </section>
  );
}
