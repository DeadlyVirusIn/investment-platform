// Phase 6b-3-d — Pathways into depth.
//
// Four editorial doorways at the foot of Research, pointing to the
// sister surfaces. Same restraint as Overview's doorway strip: NO
// metrics, sentence + arrow only.

import { Link } from "react-router-dom";


interface CellProps {
  eyebrow:  string;
  sentence: string;
  href:     string;
}

function _Cell({ eyebrow, sentence, href }: CellProps) {
  return (
    <Link
      to={href}
      className="opt-doorway-cell"
      data-test={`options-pathway-cell-${eyebrow.toLowerCase()}`}
    >
      <div className="opt-doorway-cell-eyebrow">{eyebrow}</div>
      <div className="opt-doorway-cell-sentence">{sentence}</div>
      <div className="opt-doorway-cell-arrow">
        Open <span aria-hidden>→</span>
      </div>
    </Link>
  );
}


export default function OptionsResearchPathways() {
  return (
    <section
      className="opt-doorway-strip opt-doorway-strip-4"
      data-test="options-research-pathways"
      aria-label="Continue exploring"
    >
      <_Cell
        eyebrow="Journal"
        sentence="Track how paper observations evolve over time."
        href="/options/journal"
      />
      <_Cell
        eyebrow="Learning"
        sentence="See what the system is earning the right to claim."
        href="/options/learning"
      />
      <_Cell
        eyebrow="Lab"
        sentence="Inspect the strategies and pipeline behind these observations."
        href="/options/lab"
      />
      <_Cell
        eyebrow="Ops"
        sentence="Engine health, freshness, and infrastructure detail."
        href="/options/ops"
      />
    </section>
  );
}
