// Phase 6b-3-f — Learning pathways (3 doorways).

import { Link } from "react-router-dom";


function _Cell({
  eyebrow, sentence, href,
}: { eyebrow: string; sentence: string; href: string }) {
  return (
    <Link
      to={href}
      className="opt-doorway-cell"
      data-test={`options-learning-pathway-${eyebrow.toLowerCase()}`}
    >
      <div className="opt-doorway-cell-eyebrow">{eyebrow}</div>
      <div className="opt-doorway-cell-sentence">{sentence}</div>
      <div className="opt-doorway-cell-arrow">
        Open <span aria-hidden>→</span>
      </div>
    </Link>
  );
}


export default function OptionsLearningPathways() {
  return (
    <section
      className="opt-doorway-strip"
      data-test="options-learning-pathways"
      aria-label="Continue exploring"
    >
      <_Cell
        eyebrow="Journal"
        sentence="The paper-trade evidence that gates depend on."
        href="/options/journal"
      />
      <_Cell
        eyebrow="Research"
        sentence="The candidates the system observes day by day."
        href="/options/research"
      />
      <_Cell
        eyebrow="Ops"
        sentence="The pipeline state that produces qualifying days."
        href="/options/ops"
      />
    </section>
  );
}
