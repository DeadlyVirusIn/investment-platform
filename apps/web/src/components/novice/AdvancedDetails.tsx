// Phase NOVICE-UX (Commit 1) — progressive-disclosure wrapper.
//
// Standard `<details>` element with a labeled summary. Used to hide
// pro-grade detail (raw enums, reason text, JSON dumps) behind a
// click while keeping it discoverable. NEVER hides safety-critical
// information — small-sample warnings, drawdown alerts, and
// transport errors must stay at the top level on their parent
// pages, not inside this disclosure.

import { ReactNode } from "react";
import { cn } from "@/lib/cn";


export interface AdvancedDetailsProps {
  /** Visible summary label. Default "Advanced details". */
  label?: string;
  /** When true, render expanded by default. */
  defaultOpen?: boolean;
  /** Pass-through className on the outer <details>. */
  className?: string;
  /** Children render inside the <details> body. */
  children: ReactNode;
}


export default function AdvancedDetails({
  label = "Advanced details",
  defaultOpen = false,
  className,
  children,
}: AdvancedDetailsProps) {
  return (
    <details
      data-test="advanced-details"
      open={defaultOpen}
      className={cn(
        "group rounded border border-zinc-800 bg-zinc-900/30 px-3 py-2",
        className,
      )}
    >
      <summary
        data-test="advanced-details-summary"
        className="cursor-pointer select-none text-[11px] uppercase tracking-wide text-zinc-400 outline-none focus:ring-1 focus:ring-zinc-500"
      >
        <span aria-hidden="true" className="mr-1">▾</span>
        {label}
      </summary>
      <div
        data-test="advanced-details-body"
        className="mt-2 text-[12px] leading-relaxed text-zinc-300"
      >
        {children}
      </div>
    </details>
  );
}
