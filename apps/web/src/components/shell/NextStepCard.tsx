// NextStepCard — bottom CTA pointing to the next chapter in the OS flow.
// Renders nothing if the current page has no defined next step.

import { Link } from "react-router-dom";

import { nextStep, findStep } from "@/lib/ui/page_flow";


export interface NextStepCardProps {
  pathname: string;
  /**
   * Optional honest one-liner explaining WHY the next step matters
   * given the current data state (e.g., "3 trim signals are driven
   * by weak earnings revisions"). Absent = generic step copy.
   */
  rationale?: string;
}


export default function NextStepCard({ pathname, rationale }: NextStepCardProps) {
  const nxt = nextStep(pathname);
  const cur = findStep(pathname);
  if (!nxt) return null;

  return (
    <Link to={nxt.to} className="next-step-card" data-test="next-step-card">
      <div className="next-step-text">
        <span className="next-step-eyebrow">
          {cur ? `Continue from ${cur.label}` : "Next"}
        </span>
        <h4 className="next-step-title">{nxt.label}</h4>
        <p className="next-step-body">{rationale ?? nxt.why}</p>
      </div>
      <span className="next-step-arrow">→</span>
    </Link>
  );
}
