// Phase NOVICE-UX (Commit 1) — colored status chip with tooltip.
//
// Standard status vocabulary used across the app:
//   * healthy           → green, "normal operation"
//   * waiting           → amber, "pending next bar / queued"
//   * needs_attention   → red,   "drawdown crossed / stale data"
//   * not_enough_data   → gray,  "below small-sample threshold"
//   * disabled          → gray,  "feature flag off"
//   * read_only         → blue,  "research / insight surface"
//
// NEVER implies that the operator should take a trading action.
// NEVER fabricates a status — caller supplies the kind explicitly.

import { useId, useState } from "react";
import { cn } from "@/lib/cn";


export type StatusKind =
  | "healthy"
  | "waiting"
  | "needs_attention"
  | "not_enough_data"
  | "disabled"
  | "read_only";


export interface StatusExplainerProps {
  /** Discrete status. Drives both color and default label. */
  status: StatusKind;
  /** Optional override label (e.g., "Holding for next bar" instead
   *  of the default "Waiting"). The tooltip body still describes
   *  what the underlying status means. */
  label?: string;
  /** Optional tooltip body override. When omitted, the default
   *  vocabulary description is used. */
  description?: string;
  className?: string;
}


const DEFAULTS: Record<
  StatusKind,
  { label: string; description: string; chip: string; dot: string }
> = {
  healthy: {
    label: "Healthy",
    description: "Normal operation. Metrics are within expected range.",
    chip: "border-emerald-700/60 bg-emerald-900/20 text-emerald-300",
    dot: "bg-emerald-400",
  },
  waiting: {
    label: "Waiting",
    description:
      "Pending the next market price. The system holds orders for " +
      "the next bar by design — this is intentional, not an error.",
    chip: "border-amber-700/60 bg-amber-900/20 text-amber-300",
    dot: "bg-amber-400",
  },
  needs_attention: {
    label: "Needs attention",
    description:
      "A metric crossed a threshold or data is stale. Review the " +
      "page below to see the specific reason.",
    chip: "border-red-700/60 bg-red-900/20 text-red-300",
    dot: "bg-red-400",
  },
  not_enough_data: {
    label: "Not enough data",
    description:
      "Below the small-sample threshold. Treat numbers as " +
      "directional only until enough trades have closed.",
    chip: "border-zinc-700 bg-zinc-900/40 text-zinc-300",
    dot: "bg-zinc-400",
  },
  disabled: {
    label: "Disabled",
    description:
      "This feature is turned off. Enable the matching environment " +
      "flag to use it.",
    chip: "border-zinc-700 bg-zinc-900/40 text-zinc-300",
    dot: "bg-zinc-500",
  },
  read_only: {
    label: "Read-only insight",
    description:
      "Plain-English summary for review. Read-only — never trades " +
      "on your behalf. Not financial advice.",
    chip: "border-sky-700/60 bg-sky-900/20 text-sky-300",
    dot: "bg-sky-400",
  },
};


export default function StatusExplainer({
  status,
  label,
  description,
  className,
}: StatusExplainerProps) {
  const def = DEFAULTS[status];
  const text = label ?? def.label;
  const body = description ?? def.description;
  const id = useId();
  const [open, setOpen] = useState(false);

  return (
    <span
      data-test="status-explainer"
      data-status={status}
      className={cn("inline-flex relative", className)}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen(o => !o)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
        }}
        className={cn(
          "inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[10px] uppercase tracking-wide focus:outline-none focus:ring-1 focus:ring-zinc-400",
          def.chip,
        )}
      >
        <span aria-hidden="true" className={cn("h-2 w-2 rounded-full", def.dot)} />
        <span>{text}</span>
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          data-test="status-explainer-body"
          className="absolute left-0 top-full z-50 mt-1 w-64 rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-left text-[11px] leading-relaxed text-zinc-200 shadow-lg"
        >
          {body}
        </span>
      )}
    </span>
  );
}
