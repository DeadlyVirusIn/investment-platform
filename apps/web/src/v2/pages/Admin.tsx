// Owner Admin Console — Admin-1 (read-only).
//
// AdminGuard probes GET /api/admin/overview. The SERVER is the real enforcer:
// non-owner + anonymous callers get 404, so the probe errors and we bounce to
// Discover. This frontend gate is cosmetic (prevents a broken render); it is
// NOT the security boundary.
//
// AdminHome (/v2/admin): user/demand/data counters.
// AdminFeedback (/v2/admin/feedback): anonymized feedback report.
// Both show only safe aggregates returned by the owner-guarded API.

import { useQuery } from '@tanstack/react-query';
import { Navigate, Link } from 'react-router-dom';
import { apiGet } from '@/lib/api';
import { ArthosPage } from '../chrome/ArthosChrome';
import { PageHeader } from '../components/ui/PageHeader';
import { SurfaceCard } from '../components/ui/SurfaceCard';

interface AdminOverview {
  users: {
    total: number; qa_estimated: number; real_estimated: number;
    new_24h: number; new_7d: number; profiles_started: number;
    signups_by_day: { day: string; count: number }[];
  };
  feedback: { signals_total: number };
  data: { price_bar_date: string | null; recommendation_latest: string | null };
  generated_at: string;
}

interface AdminFeedbackReport {
  total_signals: number;
  authenticated_users: number;
  anonymous_contexts: number;
  by_type: Record<string, number>;
  by_surface: Record<string, number>;
  useful: number; not_useful: number; useful_ratio: number | null;
  would_use_again: number; would_not_use_again: number; would_use_again_ratio: number | null;
  beta_interest: number;
  feedback_text_count: number;
  text_samples: string[];
}

function useAdminOverview() {
  return useQuery<AdminOverview>({
    queryKey: ['admin', 'overview'],
    queryFn: () => apiGet<AdminOverview>('/admin/overview'),
    retry: false, staleTime: 30_000,
  });
}

function useAdminFeedback() {
  return useQuery<AdminFeedbackReport>({
    queryKey: ['admin', 'feedback'],
    queryFn: () => apiGet<AdminFeedbackReport>('/admin/feedback'),
    retry: false, staleTime: 30_000,
  });
}

// Owner-only gate. Errors (incl. 404 for non-owner/anonymous) → bounce.
export function AdminGuard({ children }: { children: React.ReactNode }) {
  const { isLoading, isError } = useAdminOverview();
  if (isLoading) {
    return (
      <ArthosPage maxWidth="max-w-copy">
        <div className="py-20"><p className="ink-muted" style={{ fontSize: 14 }}>Checking access…</p></div>
      </ArthosPage>
    );
  }
  if (isError) return <Navigate to="/discover" replace />;
  return <>{children}</>;
}

function Stat({ label, value, tone = 'default' }: {
  label: string; value: string | number; tone?: 'pos' | 'muted' | 'default';
}) {
  const color = tone === 'pos' ? 'var(--brand)' : tone === 'muted' ? 'var(--muted-foreground)' : 'var(--foreground)';
  return (
    <div>
      <p className="font-semibold uppercase" style={{ fontSize: 10, letterSpacing: '0.1em', color: 'var(--muted-foreground)', marginBottom: 3 }}>{label}</p>
      <p className="tabular-nums" style={{ fontSize: 22, fontWeight: 600, color, lineHeight: 1 }}>{value}</p>
    </div>
  );
}

type AdminTab = 'overview' | 'feedback' | 'jobs' | 'system' | 'observability';

function AdminNav({ active }: { active: AdminTab }) {
  const tab = (to: string, key: AdminTab, label: string) => (
    <Link key={key} to={to} style={{
      fontSize: 13, fontWeight: 600, padding: '6px 12px', borderRadius: 999,
      color: active === key ? 'var(--brand-foreground)' : 'var(--muted-foreground)',
      backgroundColor: active === key ? 'var(--brand)' : 'transparent',
      border: active === key ? 'none' : '1px solid var(--border)',
    }}>{label}</Link>
  );
  return (
    <div className="flex items-center gap-2 mb-6 flex-wrap">
      {tab('/admin', 'overview', 'Overview')}
      {tab('/admin/feedback', 'feedback', 'Feedback')}
      {tab('/admin/jobs', 'jobs', 'Jobs')}
      {tab('/admin/system', 'system', 'System')}
      {tab('/admin/observability', 'observability', 'Observability')}
    </div>
  );
}

export function AdminHome() {
  const { data } = useAdminOverview();
  const u = data?.users;
  return (
    <AdminGuard>
      <ArthosPage maxWidth="max-w-copy" topBarEyebrow="Owner">
        <PageHeader eyebrow="Owner console" title={<>Beta overview.</>}
          description="Read-only. Owner-only. Aggregates from live data — no PII beyond what's shown here." />
        <AdminNav active="overview" />

        <SurfaceCard variant="default" className="p-5 mb-5">
          <p className="font-semibold uppercase mb-4" style={{ fontSize: 11, letterSpacing: '0.12em', color: 'var(--brand)' }}>Users</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Stat label="Total" value={u?.total ?? '—'} />
            <Stat label="Real (est.)" value={u?.real_estimated ?? '—'} tone="pos" />
            <Stat label="QA (est.)" value={u?.qa_estimated ?? '—'} tone="muted" />
            <Stat label="New 24h" value={u?.new_24h ?? '—'} />
          </div>
          <p className="ink-fainter mt-3" style={{ fontSize: 11 }}>
            QA estimate = emails matching test markers (@ex.com, browsercheck, …). Heuristic, not exact.
          </p>
        </SurfaceCard>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <SurfaceCard variant="default" className="p-5">
            <p className="font-semibold uppercase mb-4" style={{ fontSize: 11, letterSpacing: '0.12em', color: 'var(--brand)' }}>Demand</p>
            <div className="grid grid-cols-2 gap-4">
              <Stat label="Feedback signals" value={data?.feedback.signals_total ?? '—'} />
              <Stat label="Profiles started" value={u?.profiles_started ?? '—'} />
              <Stat label="New 7d" value={u?.new_7d ?? '—'} />
            </div>
          </SurfaceCard>
          <SurfaceCard variant="default" className="p-5">
            <p className="font-semibold uppercase mb-4" style={{ fontSize: 11, letterSpacing: '0.12em', color: 'var(--brand)' }}>Data freshness</p>
            <div className="grid grid-cols-1 gap-3">
              <Stat label="Latest price bar" value={data?.data.price_bar_date ?? '—'} />
              <Stat label="Latest recommendation"
                value={data?.data.recommendation_latest ? data.data.recommendation_latest.slice(0, 16).replace('T', ' ') : '—'} />
            </div>
          </SurfaceCard>
        </div>

        {u?.signups_by_day && u.signups_by_day.length > 0 && (
          <SurfaceCard variant="default" className="p-5 mt-5">
            <p className="font-semibold uppercase mb-3" style={{ fontSize: 11, letterSpacing: '0.12em', color: 'var(--muted-foreground)' }}>Signups by day</p>
            <ul className="space-y-1.5">
              {u.signups_by_day.map((d) => (
                <li key={d.day} className="grid grid-cols-[120px_1fr] items-baseline gap-3" style={{ fontSize: 13 }}>
                  <span className="ink-muted tabular-nums">{d.day}</span>
                  <span className="ink-primary tabular-nums">{d.count}</span>
                </li>
              ))}
            </ul>
          </SurfaceCard>
        )}
      </ArthosPage>
    </AdminGuard>
  );
}

export function AdminFeedback() {
  const { data } = useAdminFeedback();
  return (
    <AdminGuard>
      <ArthosPage maxWidth="max-w-copy" topBarEyebrow="Owner">
        <PageHeader eyebrow="Owner console" title={<>Feedback.</>}
          description="Anonymized — counts, ratios, and length-capped text samples. No user IDs, emails, or sessions." />
        <AdminNav active="feedback" />

        <SurfaceCard variant="default" className="p-5 mb-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Stat label="Total signals" value={data?.total_signals ?? '—'} />
            <Stat label="Useful 👍" value={data?.useful ?? '—'} tone="pos" />
            <Stat label="Not useful 👎" value={data?.not_useful ?? '—'} tone="muted" />
            <Stat label="Beta interest" value={data?.beta_interest ?? '—'} />
            <Stat label="Would use again" value={data?.would_use_again ?? '—'} tone="pos" />
            <Stat label="Would not" value={data?.would_not_use_again ?? '—'} tone="muted" />
            <Stat label="Useful ratio" value={data?.useful_ratio != null ? `${Math.round(data.useful_ratio * 100)}%` : '—'} />
            <Stat label="Return ratio" value={data?.would_use_again_ratio != null ? `${Math.round(data.would_use_again_ratio * 100)}%` : '—'} />
          </div>
        </SurfaceCard>

        <SurfaceCard variant="default" className="p-5">
          <p className="font-semibold uppercase mb-3" style={{ fontSize: 11, letterSpacing: '0.12em', color: 'var(--muted-foreground)' }}>Text samples (anonymized, capped)</p>
          {data && data.text_samples.length > 0 ? (
            <ul className="space-y-2">
              {data.text_samples.map((t, i) => (
                <li key={i} className="ink-primary" style={{ fontSize: 13, lineHeight: 1.5, paddingLeft: 12, borderLeft: '2px solid var(--border)' }}>{t}</li>
              ))}
            </ul>
          ) : (
            <p className="ink-muted" style={{ fontSize: 13 }}>No free-text feedback yet.</p>
          )}
        </SurfaceCard>
      </ArthosPage>
    </AdminGuard>
  );
}

// ---- Jobs ----------------------------------------------------------------

interface AdminJobsData {
  schedule: { name: string; enabled: boolean; cron: string | null; last_run_at: string | null; next_run_at: string | null }[];
  recent_runs: { name: string; status: string; started_at: string | null; duration_seconds: number | null; error: string | null }[];
  summary: { scheduled: number; stale: string[]; failed_in_recent: number };
}

function useAdminJobs() {
  return useQuery<AdminJobsData>({
    queryKey: ['admin', 'jobs'], queryFn: () => apiGet<AdminJobsData>('/admin/jobs'),
    retry: false, staleTime: 30_000,
  });
}

function StatusPill({ status }: { status: string }) {
  const s = status.toLowerCase();
  const tone = s === 'success' || s === 'running' ? 'var(--brand)'
    : s === 'failed' || s === 'error' ? 'oklch(0.58 0.15 28)' : 'var(--muted-foreground)';
  return (
    <span className="inline-flex items-center rounded-full font-semibold uppercase" style={{
      fontSize: 10, letterSpacing: '0.04em', padding: '2px 8px', color: tone,
      backgroundColor: `color-mix(in oklch, ${tone} 13%, transparent)`,
      border: `1px solid color-mix(in oklch, ${tone} 26%, transparent)`,
    }}>{status}</span>
  );
}

export function AdminJobs() {
  const { data } = useAdminJobs();
  const fmt = (iso: string | null) => (iso ? iso.slice(0, 16).replace('T', ' ') : '—');
  return (
    <AdminGuard>
      <ArthosPage maxWidth="max-w-copy" topBarEyebrow="Owner">
        <PageHeader eyebrow="Owner console" title={<>Jobs.</>}
          description="Read-only. Scheduler state + recent runs. Error text is capped; no secrets." />
        <AdminNav active="jobs" />

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-5">
          <Stat label="Scheduled" value={data?.summary.scheduled ?? '—'} />
          <Stat label="Stale" value={data?.summary.stale.length ?? '—'} tone={(data?.summary.stale.length ?? 0) > 0 ? 'muted' : 'pos'} />
          <Stat label="Failed (recent)" value={data?.summary.failed_in_recent ?? '—'} tone={(data?.summary.failed_in_recent ?? 0) > 0 ? 'muted' : 'pos'} />
          <Stat label="Recent runs" value={data?.recent_runs.length ?? '—'} />
        </div>

        {data && data.summary.stale.length > 0 && (
          <SurfaceCard variant="default" className="p-4 mb-5" >
            <p style={{ fontSize: 12.5, color: 'oklch(0.62 0.12 75)' }}>
              ⚠ Stale (no success &gt;26h): {data.summary.stale.join(', ')}
            </p>
          </SurfaceCard>
        )}

        <SurfaceCard variant="default" className="p-5 mb-5">
          <p className="font-semibold uppercase mb-3" style={{ fontSize: 11, letterSpacing: '0.12em', color: 'var(--muted-foreground)' }}>Recent runs</p>
          <ul className="space-y-2">
            {(data?.recent_runs ?? []).map((r, i) => (
              <li key={i} className="grid grid-cols-[1fr_auto] gap-3 items-baseline" style={{ fontSize: 12.5, borderTop: i ? '1px solid var(--border)' : 'none', paddingTop: i ? 8 : 0 }}>
                <span>
                  <StatusPill status={r.status} /> <span className="ink-primary">{r.name}</span>
                  {r.error && <span className="ink-muted" style={{ display: 'block', fontSize: 11, marginTop: 2 }}>{r.error}</span>}
                </span>
                <span className="ink-muted tabular-nums" style={{ textAlign: 'right' }}>
                  {fmt(r.started_at)}{r.duration_seconds != null ? ` · ${r.duration_seconds}s` : ''}
                </span>
              </li>
            ))}
            {data && data.recent_runs.length === 0 && <li className="ink-muted" style={{ fontSize: 13 }}>No runs recorded yet.</li>}
          </ul>
        </SurfaceCard>

        <SurfaceCard variant="default" className="p-5">
          <p className="font-semibold uppercase mb-3" style={{ fontSize: 11, letterSpacing: '0.12em', color: 'var(--muted-foreground)' }}>Schedule</p>
          <ul className="space-y-2">
            {(data?.schedule ?? []).map((s) => (
              <li key={s.name} className="grid grid-cols-[1fr_auto] gap-3 items-baseline" style={{ fontSize: 12.5 }}>
                <span className="ink-primary">{s.name} {!s.enabled && <span className="ink-fainter">(disabled)</span>}</span>
                <span className="ink-muted tabular-nums" style={{ textAlign: 'right' }}>next {fmt(s.next_run_at)}</span>
              </li>
            ))}
          </ul>
        </SurfaceCard>
      </ArthosPage>
    </AdminGuard>
  );
}

// ---- System --------------------------------------------------------------

interface AdminSystemData {
  db_connectivity: boolean;
  app_version: string;
  health: {
    available: boolean; stale?: boolean; age_seconds?: number | null; reason?: string;
    fields: Record<string, string | number | null>;
  };
  generated_at: string;
}

function useAdminSystem() {
  return useQuery<AdminSystemData>({
    queryKey: ['admin', 'system'], queryFn: () => apiGet<AdminSystemData>('/admin/system'),
    retry: false, staleTime: 30_000,
  });
}

function HealthCard({ label, value, ok }: { label: string; value: string; ok: boolean | null }) {
  const color = ok === null ? 'var(--muted-foreground)' : ok ? 'var(--brand)' : 'oklch(0.58 0.15 28)';
  return (
    <SurfaceCard variant="default" className="p-4">
      <p className="font-semibold uppercase" style={{ fontSize: 9.5, letterSpacing: '0.1em', color: 'var(--muted-foreground)', marginBottom: 4 }}>{label}</p>
      <p style={{ fontSize: 16, fontWeight: 600, color }}>{value}</p>
    </SurfaceCard>
  );
}

export function AdminSystem() {
  const { data } = useAdminSystem();
  const f = data?.health.fields ?? {};
  const okStr = (v: unknown, good: string) => (v == null ? null : String(v) === good);
  return (
    <AdminGuard>
      <ArthosPage maxWidth="max-w-copy" topBarEyebrow="Owner">
        <PageHeader eyebrow="Owner console" title={<>System.</>}
          description="Read-only health from the periodic healthcheck + a live DB ping. No secrets, no shell-out." />
        <AdminNav active="system" />

        {data && !data.health.available && (
          <SurfaceCard variant="default" className="p-4 mb-5">
            <p className="ink-muted" style={{ fontSize: 12.5 }}>
              Healthcheck JSON not available yet{data.health.reason ? ` (${data.health.reason})` : ''}. It populates on the next 15-min cron tick.
            </p>
          </SurfaceCard>
        )}
        {data?.health.stale && (
          <SurfaceCard variant="default" className="p-4 mb-5">
            <p style={{ fontSize: 12.5, color: 'oklch(0.62 0.12 75)' }}>⚠ Healthcheck data is stale ({data.health.age_seconds}s old).</p>
          </SurfaceCard>
        )}

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mb-5">
          <HealthCard label="Public site" value={f.site != null ? String(f.site) : '—'} ok={okStr(f.site, '200')} />
          <HealthCard label="API health" value={f.api_health != null ? String(f.api_health) : '—'} ok={okStr(f.api_health, 'ok')} />
          <HealthCard label="DB connectivity" value={data ? (data.db_connectivity ? 'ok' : 'down') : '—'} ok={data ? data.db_connectivity : null} />
          <HealthCard label="Tunnel" value={f.tunnel != null ? String(f.tunnel) : '—'} ok={okStr(f.tunnel, 'active')} />
          <HealthCard label="Bot" value={f.bot != null ? String(f.bot) : '—'} ok={okStr(f.bot, 'active')} />
          <HealthCard label="Workers" value={`${f.worker_cron ?? '—'} / ${f.worker_tickloop ?? '—'}`} ok={okStr(f.worker_cron, 'running') && okStr(f.worker_tickloop, 'running')} />
        </div>

        <SurfaceCard variant="default" className="p-5">
          <p className="font-semibold uppercase mb-4" style={{ fontSize: 11, letterSpacing: '0.12em', color: 'var(--muted-foreground)' }}>Resources</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Stat label="Disk used" value={f.disk_pct != null ? `${f.disk_pct}%` : '—'} tone={Number(f.disk_pct) >= 90 ? 'muted' : 'default'} />
            <Stat label="Mem avail" value={f.mem_avail_mb != null ? `${f.mem_avail_mb}M` : '—'} />
            <Stat label="Swap free" value={f.swap_free_mb != null ? `${f.swap_free_mb}M` : '—'} />
            <Stat label="Job age" value={f.job_age_h != null ? `${f.job_age_h}h` : '—'} />
          </div>
          <p className="ink-fainter mt-4" style={{ fontSize: 11 }}>
            App {data?.app_version ?? '—'} · health as of {f.ts ? String(f.ts).slice(0, 16).replace('T', ' ') : '—'}
          </p>
        </SurfaceCard>
      </ArthosPage>
    </AdminGuard>
  );
}
