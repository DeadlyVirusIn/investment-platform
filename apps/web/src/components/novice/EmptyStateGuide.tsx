// Phase NOVICE-UX (Commit 1) — standard empty-state component.
//
// Shape per spec:
//   🌱 Not enough data yet.
//   [2-sentence explanation of what produces this data + when to
//    expect it.]
//   [Optional: "What to do" — usually nothing.]
//
// NEVER fabricates a reason; the explanation is supplied by the
// caller. NEVER hides small-sample / missing-data caveats — those
// belong at the page level, not in this empty state.

import { ReactNode } from "react";
import { cn } from "@/lib/cn";


export interface EmptyStateGuideProps {
  /** Optional override headline. Default "Not enough data yet." */
  headline?: string;
  /** Body — short explanation of what produces this data. */
  children: ReactNode;
  /** Optional "what to do" line. */
  whatToDo?: ReactNode;
  className?: string;
  /** Hide the leading 🌱 icon (rare — disable when stacking). */
  hideIcon?: boolean;
}


export default function EmptyStateGuide({
  headline = "Not enough data yet.",
  children,
  whatToDo,
  className,
  hideIcon = false,
}: EmptyStateGuideProps) {
  return (
    <div
      data-test="empty-state-guide"
      className={cn(
        "rounded border border-zinc-800 bg-zinc-900/30 px-4 py-3 text-sm text-zinc-300",
        className,
      )}
    >
      <div className="flex items-start gap-2">
        {!hideIcon && (
          <span aria-hidden="true" className="text-emerald-300">🌱</span>
        )}
        <div className="flex-1">
          <div
            data-test="empty-state-guide-headline"
            className="font-semibold text-zinc-100"
          >
            {headline}
          </div>
          <div
            data-test="empty-state-guide-body"
            className="mt-1 text-zinc-400"
          >
            {children}
          </div>
          {whatToDo && (
            <div
              data-test="empty-state-guide-what-to-do"
              className="mt-2 text-zinc-500 text-[12px]"
            >
              <span className="text-zinc-400 uppercase tracking-wide">
                What to do:
              </span>{" "}
              {whatToDo}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
