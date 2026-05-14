// Phase 6b-3-g — Ops pathways.

import { Link } from "react-router-dom";


function _Cell({
  eyebrow, sentence, href,
}: { eyebrow: string; sentence: string; href: string }) {
  return (
    <Link
      to={href}
      className="opt-doorway-cell"
      data-test={`options-ops-pathway-${eyebrow.toLowerCase()}`}
    >
      <div className="opt-doorway-cell-eyebrow">{eyebrow}</div>
      <div className="opt-doorway-cell-sentence">{sentence}</div>
      <div className="opt-doorway-cell-arrow">
        Open <span aria-hidden>→</span>
      </div>
    </Link>
  );
}


export default function OptionsOpsPathways() {
  return (
    <section
      className="opt-doorway-strip"
      data-test="options-ops-pathways"
      aria-label="Continue exploring"
    >
      <_Cell
        eyebrow="Research"
        sentence="The candidates this engine produced today."
        href="/options/research"
      />
      <_Cell
        eyebrow="Journal"
        sentence="The paper observations these jobs accumulate."
        href="/options/journal"
      />
      <_Cell
        eyebrow="Settings"
        sentence="Universe, provider, and threshold configuration."
        href="/options/settings"
      />
    </section>
  );
}
