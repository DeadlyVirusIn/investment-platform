// Phase NOVICE-UX (Commit 1) — accessible help tooltip for metrics.
//
// Wraps a label with a small ⓘ icon. Tooltip body is sourced from
// the central glossary (lib/novice/glossary). Hover, focus, and
// keyboard activation all surface the description. The component
// never fetches anything and never renders rich HTML — body is
// plain text only.

import { useId, useState } from "react";
import { getGlossary } from "@/lib/novice/glossary";
import { cn } from "@/lib/cn";


export interface MetricHelpTooltipProps {
  /** Glossary key. When missing, we fall back to `inlineLabel` and
   *  hide the tooltip rather than crash. */
  term: string;
  /** Override the label without changing the glossary entry. */
  inlineLabel?: string;
  /** Override the description (rare — use sparingly). */
  inlineDescription?: string;
  className?: string;
}


export default function MetricHelpTooltip({
  term,
  inlineLabel,
  inlineDescription,
  className,
}: MetricHelpTooltipProps) {
  const entry = getGlossary(term);
  const label = inlineLabel ?? entry?.label ?? term;
  const description = inlineDescription ?? entry?.description ?? "";
  const id = useId();
  const [open, setOpen] = useState(false);

  // No glossary entry and no inline override: render the bare label
  // without the tooltip affordance so we never imply help that
  // doesn't exist.
  if (!description) {
    return (
      <span
        data-test="metric-help-no-tooltip"
        className={cn("u-caption-2 text-zinc-400", className)}
      >
        {label}
      </span>
    );
  }

  return (
    <span
      data-test="metric-help-tooltip"
      data-term={term}
      className={cn("inline-flex items-center gap-1", className)}
    >
      <span className="u-caption-2 text-zinc-400">{label}</span>
      <button
        type="button"
        aria-label={`Help: ${label}`}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen(o => !o)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
        }}
        className="relative inline-flex h-4 w-4 items-center justify-center rounded-full border border-zinc-600 text-[10px] leading-none text-zinc-400 hover:text-zinc-200 hover:border-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-400"
      >
        <span aria-hidden="true">i</span>
        {open && (
          <span
            id={id}
            role="tooltip"
            data-test="metric-help-tooltip-body"
            className="absolute left-1/2 top-full z-50 mt-1 w-64 -translate-x-1/2 rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-left text-[11px] leading-relaxed text-zinc-200 shadow-lg"
          >
            {description}
          </span>
        )}
      </button>
    </span>
  );
}
