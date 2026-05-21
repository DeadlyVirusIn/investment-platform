// OptionsCatalystChip — small chip surfacing the earliest in-window
// macro event for an opportunity. Renders nothing when no event is
// in window — honest empty state. Tooltip carries the full title
// and explanation so the chip remains compact.

import { cn } from "@/lib/cn";


export interface OptionsCatalystChipProps {
  eventType?: string | null;
  eventDate?: string | null;
  daysAway?: number | null;
  importance?: string | null;
  title?: string | null;
  explanation?: string | null;
  className?: string;
}


export default function OptionsCatalystChip({
  eventType, eventDate, daysAway, importance,
  title, explanation, className,
}: OptionsCatalystChipProps) {
  if (!eventType || !eventDate || daysAway == null) {
    return null;
  }
  const imp = (importance ?? "medium").toLowerCase();
  const tooltip = [
    title || eventType,
    explanation,
    `T-${daysAway}d · ${eventDate}`,
  ].filter(Boolean).join(" · ");

  return (
    <span
      className={cn("opt-catalyst-chip", `opt-catalyst-${imp}`, className)}
      title={tooltip}
      data-test={`opt-catalyst-${eventType}`}
      aria-label={tooltip}
    >
      <span className="opt-catalyst-dot" />
      <span className="opt-catalyst-type">{eventType}</span>
      <span className="opt-catalyst-tminus">T-{daysAway}d</span>
    </span>
  );
}
