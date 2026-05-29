// Admin Observability — read-only Ops pane for cron/job + data freshness.
//
// Single backend source: GET /api/admin/observability. No "run job"
// affordances — this surface only observes. Five sections:
//   A. Top status cards     B. Job timeline table
//   C. Freshness matrix     D. Alerts        E. Read-only footer note
//
// Honest by contract: null/unknown render as "—" / "Unknown", never
// fabricated. Errors are shown in full (no truncation).

import { useEffect, useState } from 'react';
import { ArthosPage } from '../chrome/ArthosChrome';
import { PageHeader } from '../components/ui/PageHeader';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import {
  useObservability,
  type ObsAlert,
  type Observability as ObservabilityData,
} from '../lib/observability';

// ── status → color mapping (theme-aware via tokens + mid-tone amber) ──
type Tone = 'good' | 'warn' | 'bad' | 'muted';

const TONE_FOR: Record<string, Tone> = {
  healthy: 'good', fresh: 'good', dormant: 'good', ok: 'good',
  degraded: 'warn', stale: 'warn', warning: 'warn',
  failed: 'bad', active: 'bad', error: 'bad',
  unknown: 'muted',
};

const AMBER = 'oklch(0.70 0.14 75)';

function toneColor(tone: Tone): string {
  if (tone === 'good') return 'var(--brand)';
  if (tone === 'warn') return AMBER;
  if (tone === 'bad') return 'var(--destructive)';
  return 'var(--muted-foreground)';
}

function StatusPill({ status }: { status: string | null | undefined }) {
  const key = (status ?? 'unknown').toLowerCase();
  const tone = TONE_FOR[key] ?? 'muted';
  const color = toneColor(tone);
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full"
      style={{
        fontSize: 11,
        fontWeight: 600,
        textTransform: 'capitalize',
        color,
        backgroundColor: `color-mix(in oklch, ${color} 14%, transparent)`,
        border: `1px solid color-mix(in oklch, ${color} 28%, transparent)`,
      }}
    >
      <span
        aria-hidden
        className="inline-block rounded-full"
        style={{ width: 6, height: 6, backgroundColor: color }}
      />
      {status ?? 'unknown'}
    </span>
  );
}

// ── time helpers ──
function relAge(iso: string | null): string {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 48) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function absTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function fmtUptime(seconds: number | null): string {
  if (seconds == null) return 'Unknown';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h < 1) return `${m}m`;
  if (h < 48) return `${h}h ${m}m`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}

// ── small presentational helpers ──
function StatCard({
  label, value, sub, tone,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: Tone;
}) {
  return (
    <SurfaceCard variant="default" className="p-4">
      <p
        className="font-semibold uppercase mb-1.5"
        style={{ fontSize: 10, letterSpacing: '0.14em', color: 'var(--muted-foreground)' }}
      >
        {label}
      </p>
      <p
        className="font-display ink-primary leading-none"
        style={{ fontSize: 22, color: tone ? toneColor(tone) : undefined }}
      >
        {value}
      </p>
      {sub != null && (
        <p className="ink-muted mt-1.5" style={{ fontSize: 12 }}>{sub}</p>
      )}
    </SurfaceCard>
  );
}

function SectionTitle({ n, title }: { n: string; title: string }) {
  return (
    <div className="flex items-baseline gap-3 mb-4 mt-10">
      <span className="font-mono ink-muted" style={{ fontSize: 12 }}>{n}</span>
      <h2
        className="font-display ink-primary"
        style={{ fontSize: 22, lineHeight: 1.2 }}
      >
        {title}
      </h2>
    </div>
  );
}

const ALERT_ORDER: Record<ObsAlert['severity'], number> = {
  failed: 0, stale: 1, warning: 2,
};

// ── pipeline health score (0–100, derived only from real fields) ──
function pipelineHealth(d: ObservabilityData): {
  score: number; label: string; tone: Tone;
} {
  const known = d.freshness.matrix.filter((m) => m.status !== 'unknown');
  const freshFrac = known.length
    ? known.filter((m) => m.status === 'fresh').length / known.length
    : 1;
  const jobFrac = d.jobs.length
    ? 1 - d.failed_jobs_count / d.jobs.length
    : 1;
  const dbOk = d.db.head_matches ? 1 : 0;
  const workerOk =
    d.workers.tickloop_alive === true ? 1
      : d.workers.tickloop_alive === null ? 0.5 : 0;
  const canaryOk = d.canary.status === 'dormant' ? 1
    : d.canary.status === 'unknown' ? 0.5 : 0;
  const score = Math.round(
    100 * (0.4 * freshFrac + 0.25 * jobFrac + 0.15 * dbOk
      + 0.1 * workerOk + 0.1 * canaryOk),
  );
  const tone: Tone = score >= 85 ? 'good' : score >= 60 ? 'warn' : 'bad';
  const label = score >= 85 ? 'Healthy' : score >= 60 ? 'Degraded' : 'At risk';
  return { score, label, tone };
}

// ── overdue detection (5-min grace past next_run_at, enabled jobs only) ──
function isOverdue(nextRunIso: string | null, enabled: boolean): boolean {
  if (!enabled || !nextRunIso) return false;
  const next = new Date(nextRunIso).getTime();
  if (Number.isNaN(next)) return false;
  return Date.now() - next > 5 * 60_000;
}

// ── session sparkline buffer (localStorage; real observed samples only) ──
const SPARK_KEY = 'arthos.obs.health.spark';
const SPARK_MAX = 60;

function pushSpark(score: number): number[] {
  let buf: number[] = [];
  try {
    buf = JSON.parse(localStorage.getItem(SPARK_KEY) ?? '[]');
    if (!Array.isArray(buf)) buf = [];
  } catch {
    buf = [];
  }
  buf.push(score);
  if (buf.length > SPARK_MAX) buf = buf.slice(buf.length - SPARK_MAX);
  try {
    localStorage.setItem(SPARK_KEY, JSON.stringify(buf));
  } catch {
    /* storage full / disabled — degrade silently */
  }
  return buf;
}

// ── inline SVG sparkline (no dependency) ──
function Spark({ values, color }: { values: number[]; color: string }) {
  if (values.length < 2) {
    return (
      <span className="ink-muted" style={{ fontSize: 10 }}>
        collecting…
      </span>
    );
  }
  const w = 96;
  const h = 24;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * w;
    const y = h - ((v - min) / span) * (h - 2) - 1;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return (
    <svg width={w} height={h} aria-hidden style={{ display: 'block' }}>
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// ── SLA band text from expected cadence ──
function slaBands(cadenceHours: number | null): string {
  if (cadenceHours == null) return 'no SLA';
  const fmt = (h: number) =>
    h >= 24 ? `${Math.round(h / 24)}d` : `${h}h`;
  return `fresh <${fmt(cadenceHours)} · stale >${fmt(cadenceHours * 2)}`;
}

export function Observability() {
  const { data, isLoading, isError, error, dataUpdatedAt } = useObservability();
  const health = data ? pipelineHealth(data) : null;
  const [spark, setSpark] = useState<number[]>([]);

  // Append this fetch's health score to the rolling session buffer. Real
  // observed samples only — never backfilled or fabricated.
  useEffect(() => {
    if (health) setSpark(pushSpark(health.score));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataUpdatedAt]);

  const overdueJobs = data
    ? data.jobs.filter((j) => isOverdue(j.next_run_at, j.enabled))
    : [];

  // Worst freshness offender (client-side): oldest stale/degraded channel.
  const mostStale = data
    ? [...data.freshness.matrix]
        .filter((m) => m.age_hours != null
          && (m.status === 'stale' || m.status === 'degraded'))
        .sort((a, b) => (b.age_hours ?? 0) - (a.age_hours ?? 0))[0]
    : undefined;

  return (
    <ArthosPage topBarEyebrow="Admin">
      <PageHeader
        eyebrow="System"
        title={<>Observability.</>}
        description="Did the jobs run, is the data fresh, are the workers alive — read-only. No actions here; this surface only observes."
      />

      {isLoading && (
        <SurfaceCard variant="muted" className="p-6">
          <p className="ink-muted" style={{ fontSize: 14 }}>Loading system snapshot…</p>
        </SurfaceCard>
      )}

      {isError && (
        <SurfaceCard variant="default" className="p-6">
          <p style={{ fontSize: 14, color: 'var(--destructive)', fontWeight: 600 }}>
            Could not load the observability snapshot.
          </p>
          <pre
            className="mt-2 whitespace-pre-wrap break-words"
            style={{ fontSize: 12, color: 'var(--muted-foreground)' }}
          >
            {String((error as Error)?.message ?? 'Unknown error')}
          </pre>
        </SurfaceCard>
      )}

      {data && health && (
        <>
          {/* ── Pipeline health hero: score + session sparkline + last
              successful full refresh + overdue summary ── */}
          <SurfaceCard variant="highlight" className="mb-4">
            <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-5">
              <div>
                <p
                  className="font-semibold uppercase mb-2"
                  style={{ fontSize: 10, letterSpacing: '0.14em', color: 'var(--muted-foreground)' }}
                >
                  Pipeline health
                </p>
                <div className="flex items-baseline gap-2">
                  <span
                    className="font-display leading-none tabular-nums"
                    style={{ fontSize: 48, color: toneColor(health.tone) }}
                  >
                    {health.score}
                  </span>
                  <span className="ink-muted" style={{ fontSize: 16 }}>/100</span>
                  <span
                    className="ml-2 px-2 py-0.5 rounded-full"
                    style={{
                      fontSize: 11, fontWeight: 600,
                      color: toneColor(health.tone),
                      backgroundColor: `color-mix(in oklch, ${toneColor(health.tone)} 14%, transparent)`,
                      border: `1px solid color-mix(in oklch, ${toneColor(health.tone)} 28%, transparent)`,
                    }}
                  >
                    {health.label}
                  </span>
                </div>
                <div className="flex items-center gap-2 mt-3">
                  <Spark values={spark} color={toneColor(health.tone)} />
                  <span className="ink-muted" style={{ fontSize: 10.5 }}>
                    score · this session
                  </span>
                </div>
              </div>

              <div className="text-left sm:text-right">
                <p
                  className="font-semibold uppercase mb-1.5"
                  style={{ fontSize: 10, letterSpacing: '0.14em', color: 'var(--muted-foreground)' }}
                >
                  Last successful full refresh
                </p>
                <p className="font-display ink-primary leading-none" style={{ fontSize: 26 }}>
                  {relAge(data.freshness.last_successful_cycle_at)}
                </p>
                <p className="ink-muted mt-1" style={{ fontSize: 12 }}>
                  {absTime(data.freshness.last_successful_cycle_at)}
                </p>
                {overdueJobs.length > 0 ? (
                  <p className="mt-2" style={{ fontSize: 12, fontWeight: 600, color: AMBER }}>
                    {overdueJobs.length} job{overdueJobs.length === 1 ? '' : 's'} overdue
                  </p>
                ) : (
                  <p className="ink-muted mt-2" style={{ fontSize: 12 }}>
                    No overdue jobs
                  </p>
                )}
              </div>
            </div>
          </SurfaceCard>

          {/* ── A. Top status cards ── */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
              label="System"
              value={<StatusPill status={data.system_status} />}
              sub={`Updated ${relAge(new Date(dataUpdatedAt).toISOString())}`}
            />
            <StatCard
              label="API"
              value={<StatusPill status={data.api.status} />}
              sub={`v${data.api.version ?? '—'} · up ${fmtUptime(data.api.uptime_seconds)}`}
            />
            <StatCard
              label="Workers"
              value={
                <StatusPill
                  status={
                    data.workers.tickloop_alive == null
                      ? 'unknown'
                      : data.workers.tickloop_alive ? 'healthy' : 'failed'
                  }
                />
              }
              sub={data.workers.note}
            />
            <StatCard
              label="DB schema"
              value={
                <span
                  className="font-mono"
                  style={{
                    fontSize: 13,
                    color: data.db.head_matches === false
                      ? toneColor('warn') : 'var(--foreground)',
                  }}
                >
                  {data.db.head ?? 'unknown'}
                </span>
              }
              sub={data.db.reachable ? 'reachable' : 'unreachable'}
            />
            <StatCard
              label="Last full refresh"
              value={
                <span style={{ fontSize: 15 }}>
                  {relAge(data.freshness.last_successful_cycle_at)}
                </span>
              }
              sub={absTime(data.freshness.last_successful_cycle_at)}
            />
            <StatCard
              label="Stale data"
              value={data.freshness.stale_count}
              tone={data.freshness.stale_count > 0 ? 'warn' : 'good'}
              sub={`${data.freshness.matrix.length} channels tracked`}
            />
            <StatCard
              label="Failed jobs"
              value={data.failed_jobs_count}
              tone={data.failed_jobs_count > 0 ? 'bad' : 'good'}
              sub={`${data.jobs.length} jobs scheduled`}
            />
            <StatCard
              label="Canary"
              value={<StatusPill status={data.canary.status} />}
              sub={`${data.canary.lifecycle_run_count ?? '—'} lifecycle runs (expect 0)`}
            />
            <StatCard
              label="Errors (24h)"
              value={data.errors_24h.failures ?? '—'}
              tone={
                (data.errors_24h.failures ?? 0) > 0 ? 'bad' : 'good'
              }
              sub={
                data.errors_24h.total == null
                  ? 'no run history'
                  : `${data.errors_24h.successes ?? 0} ok / ${data.errors_24h.total} runs · ${data.errors_24h.failure_rate_pct ?? 0}% fail`
              }
            />
          </div>

          {/* ── D. Alerts (surfaced high when present) ── */}
          <SectionTitle n="01" title="Alerts" />
          {data.alerts.length === 0 ? (
            <SurfaceCard variant="muted" className="p-5">
              <p className="ink-muted" style={{ fontSize: 13.5 }}>
                Nothing needs attention. No stale data, no failed jobs, canary dormant.
              </p>
            </SurfaceCard>
          ) : (
            <div className="space-y-2">
              {[...data.alerts]
                .sort((a, b) => ALERT_ORDER[a.severity] - ALERT_ORDER[b.severity])
                .map((a, i) => {
                  const color = toneColor(TONE_FOR[a.severity] ?? 'muted');
                  return (
                    <SurfaceCard key={i} variant="default" className="p-4">
                      <div className="flex items-start gap-3">
                        <StatusPill status={a.severity} />
                        <div className="min-w-0">
                          <p
                            className="font-mono"
                            style={{ fontSize: 11, color: 'var(--muted-foreground)' }}
                          >
                            {a.area}
                          </p>
                          <p
                            className="ink-primary break-words"
                            style={{ fontSize: 13.5, color }}
                          >
                            {a.message}
                          </p>
                        </div>
                      </div>
                    </SurfaceCard>
                  );
                })}
            </div>
          )}

          {/* ── B. Job timeline table ── */}
          <SectionTitle n="02" title="Jobs" />
          <SurfaceCard variant="default" className="p-0 overflow-x-auto">
            <table className="w-full" style={{ fontSize: 12.5, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['Job', 'Status', 'Last run', 'Last success', 'Next run', 'Duration', 'Error']
                    .map((h) => (
                      <th
                        key={h}
                        className="text-left font-semibold uppercase ink-muted px-3 py-2.5 whitespace-nowrap"
                        style={{ fontSize: 10, letterSpacing: '0.1em' }}
                      >
                        {h}
                      </th>
                    ))}
                </tr>
              </thead>
              <tbody>
                {data.jobs.length === 0 && (
                  <tr><td colSpan={7} className="px-3 py-4 ink-muted">No scheduled jobs found.</td></tr>
                )}
                {data.jobs.map((j) => (
                  <tr key={j.name} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td className="px-3 py-2.5 align-top">
                      <span className="font-mono ink-primary">{j.name}</span>
                      {isOverdue(j.next_run_at, j.enabled) && (
                        <span
                          className="ml-2 px-1.5 py-0.5 rounded"
                          style={{
                            fontSize: 9.5, fontWeight: 700, textTransform: 'uppercase',
                            letterSpacing: '0.06em', color: AMBER,
                            backgroundColor: `color-mix(in oklch, ${AMBER} 16%, transparent)`,
                          }}
                        >
                          overdue
                        </span>
                      )}
                      <span
                        className="block ink-muted"
                        style={{ fontSize: 10.5 }}
                      >
                        {j.cron ?? '—'}{!j.enabled && ' · disabled'}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 align-top"><StatusPill status={j.last_status} /></td>
                    <td className="px-3 py-2.5 align-top ink-primary whitespace-nowrap" title={absTime(j.last_run_at)}>{relAge(j.last_run_at)}</td>
                    <td className="px-3 py-2.5 align-top ink-muted whitespace-nowrap" title={absTime(j.last_success_at)}>{relAge(j.last_success_at)}</td>
                    <td className="px-3 py-2.5 align-top ink-muted whitespace-nowrap" title={absTime(j.next_run_at)}>{absTime(j.next_run_at)}</td>
                    <td className="px-3 py-2.5 align-top ink-muted whitespace-nowrap">
                      {j.last_duration_seconds
                        ? `${Number(j.last_duration_seconds).toFixed(1)}s` : '—'}
                    </td>
                    <td className="px-3 py-2.5 align-top" style={{ maxWidth: 280 }}>
                      {j.last_error
                        ? (
                          <span
                            className="break-words"
                            style={{ fontSize: 11.5, color: 'var(--destructive)' }}
                          >
                            {j.last_error}
                          </span>
                        )
                        : <span className="ink-muted">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </SurfaceCard>

          {/* ── Slowest jobs (top 5 by max duration) ── */}
          <p
            className="font-semibold uppercase mt-6 mb-3 ink-muted"
            style={{ fontSize: 11, letterSpacing: '0.12em' }}
          >
            Slowest jobs
          </p>
          {data.slowest_jobs.length === 0 ? (
            <SurfaceCard variant="muted" className="p-4">
              <p className="ink-muted" style={{ fontSize: 13 }}>No timed runs recorded yet.</p>
            </SurfaceCard>
          ) : (
            <SurfaceCard variant="default" className="p-0 overflow-x-auto">
              <table className="w-full" style={{ fontSize: 12.5, borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    {['Job', 'Max', 'Avg', 'Last run'].map((h) => (
                      <th
                        key={h}
                        className="text-left font-semibold uppercase ink-muted px-3 py-2.5 whitespace-nowrap"
                        style={{ fontSize: 10, letterSpacing: '0.1em' }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.slowest_jobs.map((s) => (
                    <tr key={s.name} style={{ borderBottom: '1px solid var(--border)' }}>
                      <td className="px-3 py-2.5 font-mono ink-primary">{s.name}</td>
                      <td className="px-3 py-2.5 ink-primary tabular-nums whitespace-nowrap">
                        {s.max_duration_seconds != null ? `${s.max_duration_seconds}s` : '—'}
                      </td>
                      <td className="px-3 py-2.5 ink-muted tabular-nums whitespace-nowrap">
                        {s.avg_duration_seconds != null ? `${s.avg_duration_seconds}s` : '—'}
                      </td>
                      <td className="px-3 py-2.5 ink-muted whitespace-nowrap" title={absTime(s.last_run_at)}>
                        {relAge(s.last_run_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </SurfaceCard>
          )}

          {/* ── C. Freshness matrix (+ market context + worst offender) ── */}
          <SectionTitle n="03" title="Data freshness" />
          <div className="flex flex-wrap items-center gap-3 mb-3">
            <span
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full"
              style={{
                fontSize: 11.5, fontWeight: 600,
                color: data.market.is_open ? 'var(--brand)' : 'var(--muted-foreground)',
                backgroundColor: data.market.is_open
                  ? 'color-mix(in oklch, var(--brand) 14%, transparent)'
                  : 'var(--card)',
                border: `1px solid ${data.market.is_open
                  ? 'color-mix(in oklch, var(--brand) 28%, transparent)'
                  : 'var(--border)'}`,
              }}
            >
              <span
                aria-hidden
                className="inline-block rounded-full"
                style={{
                  width: 7, height: 7,
                  backgroundColor: data.market.is_open ? 'var(--brand)' : 'var(--muted-foreground)',
                }}
              />
              {data.market.label}
            </span>
            <span className="ink-muted" style={{ fontSize: 11.5 }}>
              {data.market.is_open
                ? 'Intraday data expected to be fresh.'
                : 'Stale market data is expected outside trading hours.'}
            </span>
            {mostStale && (
              <span className="ml-auto" style={{ fontSize: 11.5, color: AMBER, fontWeight: 600 }}>
                Most stale: {mostStale.label} ({mostStale.age_human} old)
              </span>
            )}
          </div>
          <SurfaceCard variant="default" className="p-0 overflow-x-auto">
            <table className="w-full" style={{ fontSize: 12.5, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['Channel', 'Status', 'Age', 'Latest', 'Cadence', 'SLA', 'Source'].map((h) => (
                    <th
                      key={h}
                      className="text-left font-semibold uppercase ink-muted px-3 py-2.5 whitespace-nowrap"
                      style={{ fontSize: 10, letterSpacing: '0.1em' }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.freshness.matrix.map((m) => (
                  <tr key={m.key} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td className="px-3 py-2.5 ink-primary">{m.label}</td>
                    <td className="px-3 py-2.5"><StatusPill status={m.status} /></td>
                    <td className="px-3 py-2.5 ink-primary whitespace-nowrap">{m.age_human ?? '—'}</td>
                    <td className="px-3 py-2.5 ink-muted whitespace-nowrap" title={m.latest ?? ''}>{absTime(m.latest)}</td>
                    <td className="px-3 py-2.5 ink-muted whitespace-nowrap">
                      {m.expected_cadence_hours != null
                        ? (m.expected_cadence_hours >= 24
                            ? `~${Math.round(m.expected_cadence_hours / 24)}d`
                            : `~${m.expected_cadence_hours}h`)
                        : '—'}
                    </td>
                    <td className="px-3 py-2.5 ink-muted whitespace-nowrap" style={{ fontSize: 11 }}>{slaBands(m.expected_cadence_hours)}</td>
                    <td className="px-3 py-2.5 ink-muted font-mono" style={{ fontSize: 11 }}>{m.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </SurfaceCard>

          {/* ── 04. Container runtime ── */}
          <SectionTitle n="04" title="Runtime" />
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
              label="API process"
              value={<span style={{ fontSize: 15 }}>{fmtUptime(data.api.uptime_seconds)}</span>}
              sub={`up · ${data.api.status}`}
            />
            <StatCard
              label="Database"
              value={<span style={{ fontSize: 15 }}>{fmtUptime(data.db.uptime_seconds)}</span>}
              tone={data.db.reachable ? 'good' : 'bad'}
              sub={data.db.reachable
                ? `up since ${absTime(data.db.postmaster_start_time)}`
                : 'unreachable'}
            />
            <StatCard
              label="Tickloop worker"
              value={
                <StatusPill
                  status={
                    data.workers.tickloop_alive == null ? 'unknown'
                      : data.workers.tickloop_alive ? 'healthy' : 'failed'
                  }
                />
              }
              sub={`last run ${relAge(data.workers.last_job_run_at)}`}
            />
            <StatCard
              label="Scheduler"
              value={
                <StatusPill status={overdueJobs.length > 0 ? 'degraded' : 'healthy'} />
              }
              sub={`${data.jobs.filter((j) => j.enabled).length} enabled · ${overdueJobs.length} overdue`}
            />
            <StatCard
              label="DB connections"
              value={
                <span style={{ fontSize: 15 }}>
                  {data.db_connections.total ?? '—'}
                  <span className="ink-muted" style={{ fontSize: 12 }}>
                    {data.db_connections.max_connections != null
                      ? ` / ${data.db_connections.max_connections}` : ''}
                  </span>
                </span>
              }
              tone={
                data.db_connections.status === 'critical' ? 'bad'
                  : data.db_connections.status === 'warning' ? 'warn'
                  : data.db_connections.status === 'healthy' ? 'good' : 'muted'
              }
              sub={
                data.db_connections.utilization_pct != null
                  ? `${data.db_connections.active ?? 0} active · ${data.db_connections.idle ?? 0} idle · ${data.db_connections.utilization_pct}% used`
                  : 'unknown'
              }
            />
          </div>
          <p className="ink-muted mt-2" style={{ fontSize: 11 }}>
            Per-container Docker uptimes (web, cron) are not exposed to the API
            and show as inference only.
          </p>

          {/* ── 05. Deployment metadata ── */}
          <SectionTitle n="05" title="Deployment" />
          <SurfaceCard variant="default" className="p-0 overflow-x-auto">
            <table className="w-full" style={{ fontSize: 12.5, borderCollapse: 'collapse' }}>
              <tbody>
                {([
                  ['App version', data.deploy.app_version],
                  ['Git commit', data.deploy.git_sha],
                  ['Image tag', data.deploy.image_tag],
                  ['Build time', data.deploy.build_time],
                  ['DB head', data.deploy.db_head],
                  ['Expected head', data.deploy.expected_head],
                ] as Array<[string, string | null]>).map(([k, v], i, arr) => (
                  <tr
                    key={k}
                    style={i < arr.length - 1 ? { borderBottom: '1px solid var(--border)' } : undefined}
                  >
                    <td className="px-3 py-2.5 ink-muted whitespace-nowrap" style={{ width: 160 }}>{k}</td>
                    <td className="px-3 py-2.5 font-mono ink-primary break-all">
                      {v ?? <span className="ink-muted">— not set</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </SurfaceCard>

          {/* ── E. Read-only footer note ── */}
          <p
            className="ink-muted mt-8"
            style={{ fontSize: 11.5, lineHeight: 1.6 }}
          >
            Read-only surface. Snapshot at {absTime(data.as_of)} · auto-refreshes every 60s.
            Values shown as “—” / “Unknown” are genuinely unavailable, never fabricated.
          </p>
        </>
      )}
    </ArthosPage>
  );
}
