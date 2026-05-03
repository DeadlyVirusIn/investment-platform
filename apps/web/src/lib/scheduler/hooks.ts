// Phase UX-PHASE1 — single source of truth for scheduler/health.
//
// Three components previously polled /api/scheduler/health and re-derived
// readiness independently:
//   - TradeReadinessIndicator (Overview)
//   - NextRunCountdown (Overview)
//   - DailyLoopHealthCard (Ops)
//
// They could disagree. This module owns the query + the readiness state
// machine. Consumers read derived results, never re-derive.

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";


// ---------------------------------------------------------------------------
// Wire types — match /api/scheduler/health exactly
// ---------------------------------------------------------------------------

export interface TickloopJob {
  name: string;
  cron_expr: string;
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  last_status: string | null;
  last_error: string | null;
}

export interface RecentRun {
  name: string;
  started_at: string;
  finished_at: string | null;
  status: string;
}

export interface SchedulerHealth {
  as_of: string;
  daily_loop: {
    last_success_at: string | null;
    last_failure_at: string | null;
    lock_present: boolean | null;
    next_scheduled: string | null;
    marker_dir?: string | null;
  };
  tickloop: {
    jobs: TickloopJob[];
    recent_runs: RecentRun[];
  };
}


// ---------------------------------------------------------------------------
// Single shared query — React Query dedupes across consumers
// ---------------------------------------------------------------------------

export function useSchedulerHealth() {
  return useQuery<SchedulerHealth>({
    queryKey: ["scheduler", "health"],
    queryFn: () => apiGet<SchedulerHealth>("/scheduler/health"),
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  });
}


// ---------------------------------------------------------------------------
// Readiness state machine — canonical derivation
// ---------------------------------------------------------------------------

export type ReadinessKind = "READY" | "WAITING" | "DEGRADED" | "ERROR";

export type ReadinessResult =
  | { kind: "READY";    barDate: string;        todayDate: string }
  | { kind: "WAITING";  barDate: string | null; todayDate: string }
  | { kind: "DEGRADED"; detail: string }
  | { kind: "ERROR";    detail: string };


export function deriveReadiness(h: SchedulerHealth): ReadinessResult {
  // 1. Scheduler-level failure short-circuits everything else
  const succ = _parse(h.daily_loop.last_success_at);
  const fail = _parse(h.daily_loop.last_failure_at);
  if (fail && (!succ || fail.getTime() > succ.getTime())) {
    return { kind: "ERROR", detail: "Last daily loop failed" };
  }

  const jobs = Array.isArray(h.tickloop.jobs) ? h.tickloop.jobs : [];

  // 2. Tickloop job health
  const errJob = jobs.find(
    j => j.enabled && j.last_status === "error",
  );
  if (errJob) {
    return {
      kind: "DEGRADED",
      detail: `Tickloop job failing: ${errJob.name}`,
    };
  }

  // 3. Market-data freshness via ingest_prices_daily.last_run_at
  const ingest = jobs.find(j => j.name === "ingest_prices_daily");
  const today = _fmtDate(_asLocalDate(new Date()));
  if (!ingest || !ingest.last_run_at) {
    return { kind: "WAITING", barDate: null, todayDate: today };
  }
  const bar = _asLocalDate(new Date(ingest.last_run_at));
  const expected = _mostRecentTradingDay(_asLocalDate(new Date()));
  const diff = _daysBetween(bar, expected);
  const barStr = _fmtDate(bar);

  if (diff <= 0) {
    return { kind: "READY", barDate: barStr, todayDate: today };
  }
  if (diff >= 2) {
    return {
      kind: "DEGRADED",
      detail: `Market data ${diff} trading-day(s) behind`,
    };
  }
  return {
    kind: "WAITING",
    barDate: barStr,
    todayDate: _fmtDate(expected),
  };
}


// ---------------------------------------------------------------------------
// Local date helpers
// ---------------------------------------------------------------------------

function _parse(s: string | null | undefined): Date | null {
  if (!s) return null;
  try {
    const d = new Date(s);
    return isNaN(d.getTime()) ? null : d;
  } catch {
    return null;
  }
}

function _asLocalDate(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function _fmtDate(d: Date): string {
  return d.toLocaleDateString(undefined, {
    month: "short", day: "numeric",
  });
}

function _daysBetween(a: Date, b: Date): number {
  return Math.round((b.getTime() - a.getTime()) / 86_400_000);
}

function _mostRecentTradingDay(today: Date): Date {
  const d = new Date(today);
  const dow = d.getDay();
  if (dow === 0) d.setDate(d.getDate() - 2);       // Sun → Fri
  else if (dow === 6) d.setDate(d.getDate() - 1);  // Sat → Fri
  return d;
}
