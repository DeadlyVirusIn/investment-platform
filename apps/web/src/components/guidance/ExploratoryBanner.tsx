// Phase SYSTEM-ALPHA-5 — exploratory-mode marker.
// Rendered when backend reports latest decision was exploratory. Optional;
// caller passes the boolean derived from CurrentState or latest decision.

import { cn } from "@/lib/cn";

export default function ExploratoryBanner({
  active, lastExploratory,
}: { active: boolean; lastExploratory?: boolean }) {
  if (!active && !lastExploratory) return null;
  return (
    <div className={cn(
      "u-chip u-chip-warning inline-flex items-center gap-1",
    )}
         title={
           "Strict gates were not fully aligned. Paper-only learning "
           + "trades may run at reduced size. Live execution unaffected."
         }>
      <span>EXPLORATORY PAPER</span>
    </div>
  );
}
