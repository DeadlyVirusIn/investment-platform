// Phase OPS-LOOP-HEALTH — Daily Loop + tickloop visibility.
// CF-3 fix: now consumes shared `useSchedulerHealth` from
// `lib/scheduler/hooks.ts` so Ops and Overview never drift.

import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import {
  useSchedulerHealth, deriveReadiness,
  type TickloopJob, type RecentRun, type SchedulerHealth,
} from "@/lib/scheduler/hooks";


export default function DailyLoopHealthCard() {
  const { data, isLoading } = useSchedulerHealth();

  if (isLoading || !data) {
    return (
      <div className="u-card">
        <Label>Daily Loop Health</Label>
        <div className="u-caption-2 mt-2">loading…</div>
      </div>
    );
  }

  const dl = data.daily_loop;
  const jobs = data.tickloop.jobs;
  const runs = data.tickloop.recent_runs;

  // Shared canonical readiness — identical to Overview's ReadinessStrip.
  const canonical = deriveReadiness(data);
  const canonicalChipTone =
    canonical.kind === "READY"    ? "u-chip-success"
    : canonical.kind === "ERROR"  ? "u-chip-danger"
    :                               "u-chip-warning";
  const canonicalLabel = canonical.kind.toLowerCase();

  // Ops-specific richer state (for the in-card reason block only).
  const { loopTone, loopState, reason } = _deriveLoopState(dl, jobs);
  // Keep loopTone/loopState referenced to avoid unused-var TS6133;
  // they feed the detail panel below, not the header chip.
  void loopTone; void loopState;
  const lastSuccess = _fmtTs(dl.last_success_at);
  const lastFailure = _fmtTs(dl.last_failure_at);
  const nextRun = _fmtTs(dl.next_scheduled);

  // Latest paper_daily status = newest run of tickloop job name run_paper_trading
  // OR paper_run_log. For simplicity, read from recent_runs.
  const lastPaperRun = runs.find(r => r.name === "run_paper_trading");
  // Latest "market_data_readiness" is not a tickloop job; it's only
  // visible via daily loop markers. Surface based on loop outcome +
  // ingest_prices_daily freshness as a proxy.
  const ingest = jobs.find(j => j.name === "ingest_prices_daily");
  const mdReady = _marketDataReady(ingest);

  return (
    <div className="u-card">
      <div className="flex items-center justify-between mb-3">
        <div>
          <Label>Daily Loop Health</Label>
          <div className="u-caption-2 mt-0.5">
            last refresh {_fmtTs(data.as_of)}
          </div>
        </div>
        <span className={cn("u-chip", canonicalChipTone)}
              title="Canonical readiness — matches Overview ReadinessStrip">
          {canonicalLabel}
        </span>
      </div>

      {/* Key times */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 mb-3">
        <KV k="Last success" v={lastSuccess ?? "—"}
             tone={lastSuccess ? "pos" : "neutral"} />
        <KV k="Last failure" v={lastFailure ?? "—"}
             tone={lastFailure ? "neg" : "neutral"} />
        <KV k="Next scheduled" v={nextRun ?? "—"} />
        <KV k="Lock held"
             v={dl.lock_present === true ? "running"
                 : dl.lock_present === false ? "free" : "unknown"}
             tone={dl.lock_present ? "warn" : "neutral"} />
        <KV k="Paper daily"
             v={lastPaperRun
                ? `${lastPaperRun.status} · ${_fmtTs(lastPaperRun.started_at)}`
                : "—"}
             tone={lastPaperRun?.status === "success" ? "pos"
                     : lastPaperRun?.status === "error" ? "neg"
                     : "neutral"} />
        <KV k="Market data"
             v={mdReady.label}
             tone={mdReady.tone}
             title={mdReady.tooltip} />
      </div>

      {/* Reason block — only if loop is not clean */}
      {reason && (
        <div className="u-card-tight u-card-tight-warning mb-3">
          <div className="u-label-sm mb-1 text-warning">{reason.title}</div>
          <div className="u-caption text-fg leading-snug">
            {reason.detail}
          </div>
        </div>
      )}

      {/* Tickloop punch-card (Phase 2 HI-1) */}
      <TickloopPunchCard jobs={jobs} runs={runs} />

      {/* Recent runs */}
      {runs.length > 0 && (
        <div>
          <div className="u-label-sm mb-1.5">Recent Runs</div>
          <ul className="space-y-1">
            {runs.slice(0, 6).map((r, i) => (
              <li key={i} className="u-caption-2 flex gap-2">
                <span className="u-mono-sm text-fg-3 w-[140px] shrink-0">
                  {_fmtTs(r.started_at)}
                </span>
                <span className="u-mono-sm text-fg">{r.name}</span>
                <span className={cn(
                  "u-mono-sm ml-auto",
                  r.status === "success" ? "text-success"
                  : r.status === "error" ? "text-danger" : "text-fg-3",
                )}>
                  {r.status}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Tickloop Punch Card — compact recent-runs visualization per job.
// Pulls from `data.tickloop.recent_runs`. Each row = job; each cell = run.
// Detailed table preserved behind <details>.
// ---------------------------------------------------------------------------

function TickloopPunchCard({
  jobs, runs,
}: { jobs: TickloopJob[]; runs: RecentRun[] }) {
  // Group runs by job name → newest first → cap at 12 cells/job
  const PER_JOB = 12;
  const grouped = new Map<string, RecentRun[]>();
  for (const r of runs) {
    const arr = grouped.get(r.name) ?? [];
    arr.push(r);
    grouped.set(r.name, arr);
  }
  for (const [k, arr] of grouped) {
    arr.sort((a, b) =>
      new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
    );
    grouped.set(k, arr.slice(0, PER_JOB));
  }

  return (
    <div className="mb-3">
      <div className="flex items-center justify-between mb-1.5">
        <span className="u-label-sm">Tickloop jobs</span>
        <span className="u-caption-2 text-fg-3">
          last {PER_JOB} runs · click cell for detail
        </span>
      </div>
      <ul className="space-y-1">
        {jobs.map(j => {
          const cells = grouped.get(j.name) ?? [];
          return (
            <li key={j.name}
                className="grid grid-cols-[160px_1fr_auto] items-center gap-3">
              <div className="min-w-0 truncate">
                <span className="u-mono-sm text-fg">{j.name}</span>
                {!j.enabled && (
                  <span className="u-caption-2 text-fg-3 ml-2">
                    (disabled)
                  </span>
                )}
              </div>
              <PunchRow cells={cells} disabled={!j.enabled} />
              <span className={cn(
                "u-caption-2 u-mono-sm",
                j.last_status === "success" ? "text-success"
                : j.last_status === "error" ? "text-danger"
                : "text-fg-3",
              )}
              title={j.last_error ?? ""}>
                {j.enabled ? (j.last_status ?? "—") : "off"}
              </span>
            </li>
          );
        })}
      </ul>
      {/* Detail table preserved behind expand */}
      <details className="mt-2 group">
        <summary
          className="u-caption-2 text-fg-3 cursor-pointer
                       hover:text-fg select-none">
          Show full job table
        </summary>
        <div className="overflow-x-auto mt-2">
          <table className="w-full u-caption-2">
            <thead className="text-fg-3">
              <tr>
                <th className="text-left py-1">job</th>
                <th className="text-left py-1">cron</th>
                <th className="text-left py-1">last run</th>
                <th className="text-left py-1">status</th>
                <th className="text-left py-1">next</th>
              </tr>
            </thead>
            <tbody className="u-mono-sm">
              {jobs.map(j => (
                <tr key={j.name}>
                  <td className="py-1 text-fg">{j.name}</td>
                  <td className="text-fg-3">{j.cron_expr}</td>
                  <td className="text-fg-3">{_fmtTs(j.last_run_at) ?? "—"}</td>
                  <td className={cn(
                    j.last_status === "success" ? "text-success"
                    : j.last_status === "error" ? "text-danger"
                    : "text-fg-3",
                  )}>
                    {j.enabled ? (j.last_status ?? "—") : "disabled"}
                  </td>
                  <td className="text-fg-3">{_fmtTs(j.next_run_at) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}


function PunchRow({
  cells, disabled,
}: { cells: RecentRun[]; disabled: boolean }) {
  const PER_JOB = 12;
  // Reverse so oldest-on-left, newest-on-right (timeline reads l→r)
  const ordered = [...cells].reverse();
  const padded = Array.from({ length: PER_JOB }, (_, i) => {
    const idx = PER_JOB - cells.length + i;
    return idx >= 0 ? ordered[idx - (PER_JOB - cells.length)] : null;
  });
  return (
    <div className="flex gap-[3px] items-center"
         role="img"
         aria-label={
           disabled ? "Job disabled, no runs"
             : `${cells.length} recent run(s)`
         }>
      {padded.map((run, i) => (
        <PunchCell key={i} run={run} disabled={disabled} />
      ))}
    </div>
  );
}


function PunchCell({
  run, disabled,
}: { run: RecentRun | null; disabled: boolean }) {
  let cls = "u-punch-cell-empty";
  let title = "";
  if (disabled) {
    cls = "u-punch-cell-disabled";
    title = "disabled";
  } else if (run == null) {
    cls = "u-punch-cell-empty";
    title = "no run";
  } else {
    const dur = run.finished_at && run.started_at
      ? Math.round(
          (new Date(run.finished_at).getTime()
           - new Date(run.started_at).getTime()) / 1000,
        )
      : null;
    cls = run.status === "success" ? "u-punch-cell-success"
        : run.status === "error"   ? "u-punch-cell-danger"
        : run.status === "running" ? "u-punch-cell-accent"
        : "u-punch-cell-neutral";
    title = `${run.name}\n${run.status}\n${_fmtTs(run.started_at)}`
          + (dur != null ? `\n${dur}s` : "");
  }
  return <span className={cn("u-punch-cell", cls)} title={title} />;
}


// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

function KV({ k, v, tone = "neutral", title }: {
  k: string; v: string;
  tone?: "pos" | "neg" | "warn" | "neutral";
  title?: string;
}) {
  const cls = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger"
    : tone === "warn" ? "text-warning" : "text-fg";
  return (
    <div className="flex items-center justify-between" title={title}>
      <span className="u-caption text-fg-2">{k}</span>
      <span className={cn("u-mono-sm font-semibold", cls)}>{v}</span>
    </div>
  );
}


function _fmtTs(s: string | null | undefined): string | null {
  if (!s) return null;
  try {
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    return d.toLocaleString(undefined, {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return s;
  }
}


function _deriveLoopState(
  dl: SchedulerHealth["daily_loop"],
  jobs: TickloopJob[],
): { loopTone: string; loopState: string;
     reason: { title: string; detail: string } | null } {
  if (dl.lock_present === true) {
    return {
      loopTone: "u-chip-accent", loopState: "running",
      reason: null,
    };
  }
  const succ = dl.last_success_at ? new Date(dl.last_success_at).getTime() : 0;
  const fail = dl.last_failure_at ? new Date(dl.last_failure_at).getTime() : 0;
  if (fail && fail > succ) {
    return {
      loopTone: "u-chip-danger", loopState: "failed",
      reason: {
        title: "Last loop failed",
        detail: "A required job failed during the last run. Check "
                + "worker-cron logs for the failing step.",
      },
    };
  }
  // If ingest_prices_daily is stale OR last status is error → mark skipped
  const ingest = jobs.find(j => j.name === "ingest_prices_daily");
  const tickErr = jobs.some(
    j => j.enabled && j.last_status === "error",
  );
  if (tickErr) {
    const bad = jobs.find(j => j.enabled && j.last_status === "error");
    return {
      loopTone: "u-chip-warning", loopState: "tickloop degraded",
      reason: {
        title: `Tickloop job failing: ${bad?.name}`,
        detail: (bad?.last_error ?? "").slice(0, 240)
                 || "See job_run table for details.",
      },
    };
  }
  if (succ === 0) {
    return {
      loopTone: "u-chip-neutral", loopState: "no runs yet",
      reason: {
        title: "No successful loop recorded",
        detail: "Cron will fire at the next scheduled time, or trigger "
                + "manually via docker exec.",
      },
    };
  }
  // If ingest is fresh but paper_daily was skipped due to market data,
  // surface that distinctly.
  const ingestFresh = _marketDataReady(ingest);
  if (!ingestFresh.fresh) {
    return {
      loopTone: "u-chip-warning", loopState: "market data stale",
      reason: {
        title: "Market data not available",
        detail: "Prior-day bars have not been ingested. "
                + "paper_daily will skip until ingest_prices_daily "
                + "completes.",
      },
    };
  }
  return {
    loopTone: "u-chip-success", loopState: "healthy",
    reason: null,
  };
}


function _marketDataReady(
  ingest: TickloopJob | undefined,
): {
  label: string;
  tone: "pos" | "warn" | "neutral";
  fresh: boolean;
  tooltip: string;
} {
  if (!ingest || !ingest.last_run_at) {
    return {
      label: "unknown",
      tone: "neutral",
      fresh: false,
      tooltip: "ingest_prices_daily has never run.",
    };
  }
  // Latest bar date = date portion of ingest last_run_at (ingest stores
  // the bar for the same trading day at ~22:00 ET).
  const lastRun = new Date(ingest.last_run_at);
  const bar = _asLocalDate(lastRun);
  const today = _asLocalDate(new Date());
  const expected = _mostRecentTradingDay(today);   // skip Sat/Sun

  const barStr = _fmtDate(bar);
  const expectedStr = _fmtDate(expected);
  const ageDays = _daysBetween(bar, expected);
  const failed = ingest.last_status === "error";

  // Ready if bar covers the most recent trading day already finalized.
  if (!failed && ageDays <= 0) {
    return {
      label: `${barStr} · ready`,
      tone: "pos", fresh: true,
      tooltip: `Latest bar: ${barStr}. Expected trading date: `
                + `${expectedStr}. Up to date.`,
    };
  }
  // Same-day before ingest (e.g. mid-day, market still open).
  if (!failed && ageDays === 1) {
    return {
      label: `${barStr} · ${expectedStr} not ready`,
      tone: "warn", fresh: false,
      tooltip: `Latest bar: ${barStr}. ${expectedStr} bar not yet `
                + `ingested. paper_daily will skip until "
                + "ingest_prices_daily runs at 22:00 ET.`,
    };
  }
  if (failed) {
    return {
      label: `${barStr} · ingest failed`,
      tone: "warn", fresh: false,
      tooltip: `Last ingest run errored. Latest bar: ${barStr}. "
                + "Check tickloop logs.`,
    };
  }
  return {
    label: `${barStr} · stale (${ageDays}d)`,
    tone: "warn", fresh: false,
    tooltip: `Latest bar: ${barStr}. Expected trading date: `
              + `${expectedStr}. Ingest is ${ageDays} trading-day(s) `
              + `behind.`,
  };
}


// ---- local date helpers (no timezone lib needed) ----

function _asLocalDate(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function _fmtDate(d: Date): string {
  return d.toLocaleDateString(undefined, {
    month: "short", day: "numeric",
  });
}

function _daysBetween(a: Date, b: Date): number {
  const ms = b.getTime() - a.getTime();
  return Math.round(ms / 86_400_000);
}

function _mostRecentTradingDay(today: Date): Date {
  // Weekends → walk back to Friday. Doesn't know holidays (best-effort).
  const d = new Date(today);
  const dow = d.getDay();           // 0=Sun, 6=Sat
  if (dow === 0) d.setDate(d.getDate() - 2);         // Sun → Fri
  else if (dow === 6) d.setDate(d.getDate() - 1);    // Sat → Fri
  return d;
}
