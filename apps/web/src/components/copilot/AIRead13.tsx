// UX-13 — AIRead13 component (visual hypothesis).
//
// Renders the page-state line + ambient timestamp + posture sentence
// + "since you left" delta. Source Serif 4 hero. Mode signature
// implicit in posture text.

import type { LivingPageData } from "@/lib/copilot/living_compose";


export interface AIRead13Props {
  data: LivingPageData;
}


export default function AIRead13({ data }: AIRead13Props) {
  const isField = data.room === "field";

  return (
    <>
      <header className="ux13-page-header">
        <div className="ux13-page-state" data-test="ux13-page-state">
          {data.pageStateText}
        </div>
        <div className="ux13-ambient-block" data-test="ux13-ambient">
          <div className="ux13-ambient-time">{data.ambientTime}</div>
          {data.sinceYouLeftText && (
            <div className="ux13-since-line" data-test="ux13-since-line">
              {data.sinceYouLeftText}
            </div>
          )}
        </div>
      </header>

      <p
        className={`ux13-posture${isField ? " ux13-posture-field" : ""}`}
        data-test="ux13-posture"
      >
        {data.postureText}
      </p>
    </>
  );
}
