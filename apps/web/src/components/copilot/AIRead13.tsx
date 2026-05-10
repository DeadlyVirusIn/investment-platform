// UX-13 — AIRead13 (operational pass).
//
// Header cluster: page-state + totals top-left, ambient + since-you-left
// top-right. Posture sentence below — smaller (clamp 28-44) than the
// editorial pass to make room for activity stream below.

import type { LivingPageData } from "@/lib/copilot/living_compose";


export interface AIRead13Props {
  data: LivingPageData;
}


export default function AIRead13({ data }: AIRead13Props) {
  const isField = data.room === "field";

  return (
    <>
      <header className="ux13-page-header">
        <div>
          <div className="ux13-page-state" data-test="ux13-page-state">
            {data.pageStateText}
          </div>
          <div className="ux13-totals" data-test="ux13-totals">
            <span>{data.totals.active}</span> active
            <span>·</span>
            <span>{data.totals.watch}</span> watch
            <span>·</span>
            <span>{data.totals.newToday}</span> new
          </div>
        </div>
        <div className="ux13-ambient-block" data-test="ux13-ambient">
          <div>{data.ambientTime}</div>
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
