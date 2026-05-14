// Phase 6b-3-e — Journal pathways (3 doorways).

import { Link } from "react-router-dom";


function _Cell({
  eyebrow, sentence, href,
}: { eyebrow: string; sentence: string; href: string }) {
  return (
    <Link
      to={href}
      className="opt-doorway-cell"
      data-test={`options-journal-pathway-${eyebrow.toLowerCase()}`}
    >
      <div className="opt-doorway-cell-eyebrow">{eyebrow}</div>
      <div className="opt-doorway-cell-sentence">{sentence}</div>
      <div className="opt-doorway-cell-arrow">
        Open <span aria-hidden>→</span>
      </div>
    </Link>
  );
}


export default function OptionsJournalPathways() {
  return (
    <section
      className="opt-doorway-strip"
      data-test="options-journal-pathways"
      aria-label="Continue exploring"
    >
      <_Cell
        eyebrow="Research"
        sentence="See what is being observed today and why it matters."
        href="/options/research"
      />
      <_Cell
        eyebrow="Learning"
        sentence="Track how the system earns the right to claim insight."
        href="/options/learning"
      />
      <_Cell
        eyebrow="Ops"
        sentence="Pipeline health, scheduler state, and provider freshness."
        href="/options/ops"
      />
    </section>
  );
}
