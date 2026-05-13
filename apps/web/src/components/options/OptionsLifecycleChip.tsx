// Phase Opt-C1 Step 8 — Lifecycle chip + days-meta.
//
// Compact pill showing trade state + age. Visual language matches
// Opt-B2 lifecycle states (PROPOSED/OPEN/EXPIRING/CLOSED/EXPIRED/ASSIGNED).
//
// Calm tones — no saturated greens/reds. Days-meta inline below
// (3d held / 2d to exp / 5d → target_hit).

import { cn } from "@/lib/cn";


export type LifecycleStatus =
  | "PROPOSED" | "OPEN" | "EXPIRING"
  | "CLOSED" | "EXPIRED" | "ASSIGNED"
  | string;


export interface OptionsLifecycleChipProps {
  status: LifecycleStatus;
  opened_at?: string | null;     // ISO
  closed_at?: string | null;     // ISO (terminal states)
  expiry?: string | null;        // YYYY-MM-DD (earliest leg)
  close_reason?: string | null;  // target_hit / stop_hit / etc.
}


function _toneFor(status: string): string {
  switch (status) {
    case "OPEN":     return "is-open";
    case "EXPIRING": return "is-expiring";
    case "CLOSED":   return "is-closed";
    case "EXPIRED":  return "is-expired";
    case "ASSIGNED": return "is-assigned";
    case "PROPOSED": return "is-proposed";
    default:         return "is-neutral";
  }
}


function _labelFor(status: string): string {
  return status.toLowerCase();
}


function _daysBetween(a: string | Date, b: string | Date): number {
  const at = a instanceof Date ? a.getTime() : new Date(a).getTime();
  const bt = b instanceof Date ? b.getTime() : new Date(b).getTime();
  return Math.max(0, Math.floor((bt - at) / 86_400_000));
}


function _metaText(props: OptionsLifecycleChipProps): string | null {
  const { status, opened_at, closed_at, expiry, close_reason } = props;
  const now = new Date();

  if (status === "OPEN" && opened_at) {
    const days = _daysBetween(opened_at, now);
    return `${days}d held`;
  }
  if (status === "EXPIRING" && expiry) {
    const dte = _daysBetween(now, expiry + "T00:00:00Z");
    return `${dte}d to exp`;
  }
  if (status === "CLOSED" && opened_at && closed_at) {
    const days = _daysBetween(opened_at, closed_at);
    return close_reason
      ? `${days}d → ${close_reason}`
      : `${days}d held`;
  }
  if (status === "EXPIRED" && close_reason) {
    return close_reason; // OTM / PIN_RISK
  }
  if (status === "ASSIGNED" && close_reason) {
    return close_reason; // ITM
  }
  return null;
}


export default function OptionsLifecycleChip(props: OptionsLifecycleChipProps) {
  const tone = _toneFor(props.status);
  const label = _labelFor(props.status);
  const meta = _metaText(props);
  return (
    <span
      className={cn("opt-lifecycle-chip", tone)}
      data-status={props.status}
      title={`Lifecycle: ${label}`}
    >
      <span className="opt-lifecycle-dot" aria-hidden="true">●</span>
      <span className="opt-lifecycle-label">{label}</span>
      {meta && <span className="opt-lifecycle-meta">{meta}</span>}
    </span>
  );
}
