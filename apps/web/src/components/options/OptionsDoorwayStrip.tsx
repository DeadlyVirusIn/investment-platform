// Phase 6b-3-c — Editorial doorway strip on Overview.
//
// Three calm cells. Each cell is a labelled doorway into a deeper
// surface. NO metrics. NO bars. NO mini-dashboards. Numbers live
// on the destination page; the doorway carries narrative only.
//
// Per design amendment 4 (Phase 6b-3 architectural reset):
//   "doorways should feel editorial, not like tiny dashboards."
//
// Discipline:
//   * Pure-static React. Zero data fetch. Zero state.
//   * Read-only. No buttons with handlers. Anchors only.
//   * Color via var(--*) — dark/light theme-correct.

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
      data-test={`options-doorway-cell-${eyebrow.toLowerCase().replace(/\s+/g, "-")}`}
    >
      <div className="opt-doorway-cell-eyebrow">{eyebrow}</div>
      <div className="opt-doorway-cell-sentence">{sentence}</div>
      <div className="opt-doorway-cell-arrow">
        Open <span aria-hidden>→</span>
      </div>
    </Link>
  );
}


export default function OptionsDoorwayStrip() {
  return (
    <section
      className="opt-doorway-strip"
      data-test="options-doorway-strip"
      aria-label="Continue exploring"
    >
      <_Cell
        eyebrow="Filtered out"
        sentence="What the engine excluded today, and why."
        href="/options/research"
      />
      <_Cell
        eyebrow="Universe"
        sentence="The configured universe and provider context."
        href="/options/settings"
      />
      <_Cell
        eyebrow="Learning"
        sentence="The system is earning intelligence over time."
        href="/options/learning"
      />
    </section>
  );
}
