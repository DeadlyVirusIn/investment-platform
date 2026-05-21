// OptionsLiveStateChip — global "is the engine live?" chip.
//
// Single canonical source for engine-state framing across the Options
// Copilot. Renders one of:
//   * Shadow only           — OPTIONS_ENABLED=false, canary off
//   * Canary armed          — canary on, broad execution off
//   * Broad execution       — OPTIONS_ENABLED=true (theoretical)
//   * Engine state unknown  — endpoint failed
//
// Reads /api/options/health or /api/options/pipeline-status. Failure
// degrades quietly to "unknown" — never alarms the user. Subtle
// visual treatment so the chip informs without dominating.

import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";


export interface OptionsLiveStateChipProps {
  /** Force a specific state (useful for storybook / tests). */
  override?: LiveState;
  size?: "sm" | "md";
  className?: string;
}

type LiveState = "shadow" | "canary" | "live" | "unknown";


const COPY: Record<LiveState, { label: string; sub: string }> = {
  shadow:  { label: "Shadow only",        sub: "Engine observes; no paper or live execution" },
  canary:  { label: "Canary armed",       sub: "Single-portfolio paper canary active" },
  live:    { label: "Broad execution",    sub: "Full paper-execution gate is on" },
  unknown: { label: "Engine state unknown", sub: "Pipeline status endpoint unavailable" },
};


async function fetchLiveState(): Promise<LiveState> {
  try {
    const res = await fetch("/api/options/pipeline-status", {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return "unknown";
    const j = await res.json() as Record<string, unknown>;
    // Defensive read — endpoint shape can vary. Strict: only flip to
    // "live"/"canary" when the response explicitly says so.
    const optionsEnabled = j["options_enabled"] === true
      || (typeof j["options_enabled"] === "string"
          && (j["options_enabled"] as string).toLowerCase() === "true");
    const canaryEnabled = j["canary_enabled"] === true
      || (typeof j["canary_enabled"] === "string"
          && (j["canary_enabled"] as string).toLowerCase() === "true");
    if (optionsEnabled) return "live";
    if (canaryEnabled) return "canary";
    return "shadow";
  } catch {
    return "unknown";
  }
}


export default function OptionsLiveStateChip({
  override, size = "sm", className,
}: OptionsLiveStateChipProps) {
  const [state, setState] = useState<LiveState>(override ?? "unknown");

  useEffect(() => {
    if (override) { setState(override); return; }
    let cancelled = false;
    fetchLiveState().then(s => { if (!cancelled) setState(s); });
    return () => { cancelled = true; };
  }, [override]);

  const c = COPY[state];
  return (
    <span
      className={cn("opt-live-chip", `opt-live-${state}`,
                    `opt-live-${size}`, className)}
      title={c.sub}
      data-test={`opt-live-${state}`}
      aria-label={`${c.label}. ${c.sub}.`}
    >
      <span className="opt-live-dot" />
      {c.label}
    </span>
  );
}


/** Compact shadow-only watermark for individual cards. */
export function OptionsShadowWatermark({ className }: { className?: string }) {
  return (
    <span
      className={cn("opt-shadow-watermark", className)}
      data-test="opt-shadow-watermark"
      title="Shadow-only signal — not a live or paper execution."
      aria-label="Shadow signal · not executable"
    >
      shadow
    </span>
  );
}
