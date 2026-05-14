// Phase 6b-3-h — Lab pathways.

import { Link } from "react-router-dom";


function _Cell({
  eyebrow, sentence, href,
}: { eyebrow: string; sentence: string; href: string }) {
  return (
    <Link
      to={href}
      className="opt-doorway-cell"
      data-test={`options-lab-pathway-${eyebrow.toLowerCase()}`}
    >
      <div className="opt-doorway-cell-eyebrow">{eyebrow}</div>
      <div className="opt-doorway-cell-sentence">{sentence}</div>
      <div className="opt-doorway-cell-arrow">
        Open <span aria-hidden>→</span>
      </div>
    </Link>
  );
}


export default function OptionsLabPathways() {
  return (
    <section
      className="opt-doorway-strip"
      data-test="options-lab-pathways"
      aria-label="Continue exploring"
    >
      <_Cell
        eyebrow="Research"
        sentence="The candidates produced by this evaluation pipeline today."
        href="/options/research"
      />
      <_Cell
        eyebrow="Learning"
        sentence="The readiness gates this evaluator must satisfy to claim insight."
        href="/options/learning"
      />
      <_Cell
        eyebrow="Settings"
        sentence="The thresholds and configuration that govern these strategies."
        href="/options/settings"
      />
    </section>
  );
}
