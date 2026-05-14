// Phase 6b-3-i — Settings pathways (2 doorways; deliberately fewer).

import { Link } from "react-router-dom";


function _Cell({
  eyebrow, sentence, href,
}: { eyebrow: string; sentence: string; href: string }) {
  return (
    <Link
      to={href}
      className="opt-doorway-cell"
      data-test={`options-settings-pathway-${eyebrow.toLowerCase()}`}
    >
      <div className="opt-doorway-cell-eyebrow">{eyebrow}</div>
      <div className="opt-doorway-cell-sentence">{sentence}</div>
      <div className="opt-doorway-cell-arrow">
        Open <span aria-hidden>→</span>
      </div>
    </Link>
  );
}


export default function OptionsSettingsPathways() {
  return (
    <section
      className="opt-doorway-strip"
      data-test="options-settings-pathways"
      aria-label="Continue exploring"
    >
      <_Cell
        eyebrow="Ops"
        sentence="The pipeline that operates within these boundaries."
        href="/options/ops"
      />
      <_Cell
        eyebrow="Lab"
        sentence="The strategy templates these thresholds govern."
        href="/options/lab"
      />
    </section>
  );
}
