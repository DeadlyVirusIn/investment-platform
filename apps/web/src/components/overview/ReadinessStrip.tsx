// Phase UX-PHASE1 (CF-1) — single canonical readiness + countdown strip.
//
// Replaces TradeReadinessIndicator + NextRunCountdown. One state machine,
// one query, one chip, one countdown. No duplicate derivation.

import { useEffect, useState } from "react";
import {
  useSchedulerHealth, deriveReadiness,
  type ReadinessResult,
} from "@/lib/scheduler/hooks";
import { cn } from "@/lib/cn";


export default function ReadinessStrip() {
  const { data, isError, isLoading } = useSchedulerHealth();
  useTicker();

  if (isLoading || !data) {
    return (
      <Strip
        chipTone="neutral"
        chipLabel="checking…"
        primary="checking scheduler"
        secondary={null}
      />
    );
  }
  if (isError) {
    return (
      <Strip
        chipTone="danger"
        chipLabel="Scheduler error"
        primary="Last daily loop failed"
        secondary="Fix required before next run"
      />
    );
  }

  const r = deriveReadiness(data);
  const next = _parse(data.daily_loop.next_scheduled);
  const countdown = next ? _fmtCountdown(next.getTime() - Date.now()) : null;
  const whenET = next ? _fmtET(next) : null;

  return renderStrip(r, whenET, countdown);
}


// ---------------------------------------------------------------------------

function renderStrip(
  r: ReadinessResult,
  whenET: string | null,
  countdown: string | null,
) {
  switch (r.kind) {
    case "READY":
      return (
        <Strip
          chipTone="success"
          chipLabel="Ready to trade"
          primary={`Market data available for today (${r.barDate})`}
          secondary={
            whenET
              ? `Next paper run ${whenET}${countdown ? ` · in ${countdown}` : ""}`
              : "Next paper run scheduled"
          }
        />
      );
    case "WAITING":
      return (
        <Strip
          chipTone="warning"
          chipLabel="Waiting for market data"
          primary={
            <>
              Latest data: <span className="u-mono-sm">{r.barDate ?? "—"}</span>
              {" · "}
              <span className="u-mono-sm">{r.todayDate}</span> not ready
            </>
          }
          secondary={
            whenET
              ? `Ingest 22:00 ET → daily loop ${whenET}${
                  countdown ? ` · in ${countdown}` : ""
                }`
              : "Awaiting ingest, then daily loop"
          }
        />
      );
    case "DEGRADED":
      return (
        <Strip
          chipTone="warning"
          chipLabel="System degraded"
          primary={r.detail}
          secondary={
            whenET ? `Fix required before ${whenET}` : "Fix required"
          }
        />
      );
    case "ERROR":
      return (
        <Strip
          chipTone="danger"
          chipLabel="Scheduler error"
          primary={r.detail}
          secondary={
            whenET ? `Fix required before ${whenET}` : "Fix required"
          }
        />
      );
  }
}


function Strip({
  chipTone, chipLabel, primary, secondary,
}: {
  chipTone: "success" | "warning" | "danger" | "neutral";
  chipLabel: string;
  primary: React.ReactNode;
  secondary: React.ReactNode | null;
}) {
  const chipClass = chipTone === "success" ? "u-chip-success"
    : chipTone === "warning" ? "u-chip-warning"
    : chipTone === "danger" ? "u-chip-danger" : "u-chip-neutral";
  const dotClass = chipTone === "success" ? "u-dot-success"
    : chipTone === "warning" ? "u-dot-warning"
    : chipTone === "danger" ? "u-dot-danger" : "u-dot-neutral";
  return (
    <div className="flex items-center gap-3 min-w-0 flex-wrap"
         role="status"
         aria-live="polite"
         title={typeof primary === "string" ? primary : undefined}>
      <span className={cn("u-chip shrink-0", chipClass)}>
        <span className={cn("u-dot", dotClass)} />
        <span className="ml-1">{chipLabel}</span>
      </span>
      <div className="min-w-0 flex flex-col leading-tight">
        <span className="u-caption text-fg truncate">{primary}</span>
        {secondary && (
          <span className="u-caption-2 text-fg-3 truncate">{secondary}</span>
        )}
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

function useTicker(intervalMs = 30_000) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
}

function _parse(s: string | null | undefined): Date | null {
  if (!s) return null;
  try {
    const d = new Date(s);
    return isNaN(d.getTime()) ? null : d;
  } catch {
    return null;
  }
}

function _fmtET(d: Date): string {
  try {
    const fmt = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false,
    });
    const parts = fmt.formatToParts(d);
    const wk = parts.find(p => p.type === "weekday")?.value ?? "";
    const hh = parts.find(p => p.type === "hour")?.value ?? "";
    const mm = parts.find(p => p.type === "minute")?.value ?? "";
    return `${wk} ${hh}:${mm} ET`;
  } catch {
    return d.toISOString();
  }
}

function _fmtCountdown(ms: number): string {
  if (ms <= 0) return "now";
  const min = Math.floor(ms / 60_000);
  const days = Math.floor(min / 1440);
  const hours = Math.floor((min % 1440) / 60);
  const mins = min % 60;
  if (days > 0)  return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}


// Re-export deriveReadiness for tests / introspection (unchanged contract)
export { deriveReadiness } from "@/lib/scheduler/hooks";
export type { ReadinessResult, SchedulerHealth } from "@/lib/scheduler/hooks";
