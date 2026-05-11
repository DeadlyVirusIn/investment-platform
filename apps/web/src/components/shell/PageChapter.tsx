// PageChapter — narrative rail with NOW as hero text.
//
// Layout:
//   ┌────────────────────────────────────────────────┐
//   │ section › page                                 │
//   │ NOW (hero — large, dominant)                   │
//   ├──────────────────────┬─────────────────────────┤
//   │ Why this matters     │ Next chapter →          │
//   └──────────────────────┴─────────────────────────┘
//
// All copy must come from real props — no lorem ipsum, no synthesized
// claims. `now` is rendered only when supplied (typically derived from
// honest portfolio/event data on that specific page).

import { Link } from "react-router-dom";

import { findStep, nextStep, SECTIONS } from "@/lib/ui/page_flow";


export interface PageChapterProps {
  pathname: string;
  /**
   * Optional honest "now" sentence derived from real data on the
   * current page. If absent, the rail renders only WHY + NEXT.
   */
  now?: string;
}


export default function PageChapter({ pathname, now }: PageChapterProps) {
  const cur = findStep(pathname);
  const nxt = nextStep(pathname);
  if (!cur) return null;

  const sectionLabel = SECTIONS.find(s => s.key === cur.section)?.label ?? "";

  return (
    <section className="page-chapter" data-test="page-chapter">
      <div className="page-chapter-crumb">
        <span className="page-chapter-section">{sectionLabel}</span>
        <span className="page-chapter-sep">›</span>
        <span className="page-chapter-page">{cur.label}</span>
      </div>

      {now && (
        <div className="page-chapter-now">
          <span className="page-chapter-eyebrow">Now</span>
          <p className="page-chapter-now-text">{now}</p>
        </div>
      )}

      <div className="page-chapter-grid">
        <div className="page-chapter-cell">
          <span className="page-chapter-eyebrow">Why this matters</span>
          <p className="page-chapter-text">{cur.why}</p>
          <p className="page-chapter-text page-chapter-sub">{cur.what}</p>
        </div>

        {nxt && (
          <Link to={nxt.to} className="page-chapter-cell page-chapter-next">
            <span className="page-chapter-eyebrow">Next chapter</span>
            <p className="page-chapter-text">{nxt.label}</p>
            <span className="page-chapter-cta">{nxt.why} →</span>
          </Link>
        )}
      </div>
    </section>
  );
}
