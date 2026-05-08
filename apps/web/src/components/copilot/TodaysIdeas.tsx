// UX-5B Phase B-2 — Block 3: today's ideas.
//
// Composes IdeaCard primitives. Returns null when derive returned
// null (R-E — empty blocks collapse, never render header alone).
//
// The "ideas" link points at /ideas, the future canonical Layer-1
// route reserved by UX-5 §8 routing. Until UX-5D builds that page,
// the route falls through to NotFound — acceptable read-only
// behavior. App.tsx will add a friendly redirect in a later phase.

import { Link } from "react-router-dom";

import type { TodaysIdeasOutput } from "@/lib/copilot/overview_derive";
import { TODAYS_IDEAS } from "@/lib/copilot/overview_copy";

import IdeaCard from "./IdeaCard";


export interface TodaysIdeasProps {
  data: TodaysIdeasOutput | null;
  className?: string;
}


export default function TodaysIdeas(
  { data, className }: TodaysIdeasProps,
) {
  if (!data) return null;

  return (
    <section
      className={className}
      data-test="copilot-todays-ideas"
      aria-labelledby="copilot-todays-ideas-h"
    >
      <h2
        id="copilot-todays-ideas-h"
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
        {TODAYS_IDEAS.header}
      </h2>
      <div
        style={{
          marginTop: 16,
          display: "flex",
          flexDirection: "column",
          gap: 20,
        }}
      >
        {data.cards.map((c, i) => (
          <IdeaCard key={`${c.symbol}-${i}`} data={c} />
        ))}
      </div>
      <div style={{ marginTop: 16 }}>
        <Link
          to="/ideas"
          data-test="copilot-todays-ideas-link"
          style={{
            fontSize: "var(--copilot-type-13)",
            opacity: 0.7,
            color: "inherit",
            textDecoration: "underline",
          }}
        >
          {TODAYS_IDEAS.link} →
        </Link>
      </div>
    </section>
  );
}
