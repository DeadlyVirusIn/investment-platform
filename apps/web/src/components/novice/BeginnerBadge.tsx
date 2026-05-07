// Phase NOVICE-UX (Commit 1) — small "Beginner-friendly" pill.
//
// Used to mark pages or sections that have been simplified for
// non-trader readers. Purely decorative; never affects routing or
// data. Place near a page title or above an explanatory section.

import { cn } from "@/lib/cn";


export interface BeginnerBadgeProps {
  /** Optional override label. Default "Guided view".
   *  ("Plain-English view" is also acceptable for sections that
   *  emphasize copy clarity over progressive disclosure.) */
  label?: string;
  className?: string;
}


export default function BeginnerBadge({
  label = "Guided view",
  className,
}: BeginnerBadgeProps) {
  return (
    <span
      data-test="beginner-badge"
      className={cn(
        "inline-flex items-center gap-1 rounded border border-emerald-700/60 bg-emerald-900/20 px-2 py-0.5 text-[10px] uppercase tracking-wide text-emerald-300",
        className,
      )}
    >
      <span aria-hidden="true">🌱</span>
      <span>{label}</span>
    </span>
  );
}
