// Research Inbox — owner-only review workflow UI (Elite ArthOS P4).
//
// Frontend gate: renders only when VITE_RESEARCH_INBOX === '1' (dev/default
// off — the route is not registered otherwise, and never appears in public
// navigation). Server gate: every /api/admin/inbox/* route is owner-gated
// (404 posture) AND mounted only when RESEARCH_INBOX_ENABLED is true, so
// this page fails closed to the owner-only panel everywhere else.
// Review actions go through the existing state-machine routes ONLY
// (approve/reject); corrections arrive as NEW versions server-side — this
// UI never edits or overwrites a report body.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArthosPage } from '../chrome/ArthosChrome';
import { StatusPanel } from '../components/ui/StatusPanel';
import { freshnessInfo } from '../lib/freshness';
import { apiGet, apiPost } from '@/lib/api';

export function researchInboxEnabled(): boolean {
  return import.meta.env.VITE_RESEARCH_INBOX === '1';
}

type Task = { id: string; title: string; question: string; scope: string | null; created_at: string | null };
type Report = {
  id: string; task_id: string; version: number; body: string;
  citations: unknown[] | null;
  /** Server-enforced origin: 'generated' (starts pending) or 'human'. */
  provenance: 'generated' | 'human' | string | null;
  review_status: 'pending' | 'approved' | 'rejected';
  reviewed_by: string | null; reviewed_at: string | null;
  created_at: string | null;
  state: 'fresh' | 'stale' | 'superseded';
};

const REVIEW_META: Record<Report['review_status'], { text: string; color: string; glyph: string; hint: string }> = {
  pending: {
    text: 'Pending review', color: 'oklch(0.70 0.14 75)', glyph: '◐',
    hint: 'Generated report — not human-approved yet. Treat as unverified.',
  },
  approved: {
    text: 'Approved', color: 'var(--brand)', glyph: '✓',
    hint: 'Reviewed and approved by the owner.',
  },
  rejected: {
    text: 'Rejected', color: 'oklch(0.62 0.19 25)', glyph: '✕',
    hint: 'Reviewed and rejected — kept for the record, never deleted.',
  },
};

const STATE_META: Record<Report['state'], { text: string; hint: string }> = {
  fresh: { text: 'Fresh', hint: 'Latest version, within its validity window.' },
  stale: { text: 'Stale', hint: 'Past its validity window — treat with caution.' },
  superseded: { text: 'Superseded', hint: 'A newer version (correction) exists; history is preserved.' },
};

function Chip({ color, glyph, children, title }: {
  color: string; glyph: string; children: React.ReactNode; title?: string;
}) {
  return (
    <span title={title} className="inline-flex items-center gap-1 rounded-full font-semibold uppercase shrink-0"
      style={{
        fontSize: 10, letterSpacing: '0.05em', padding: '2px 8px', color,
        backgroundColor: `color-mix(in oklch, ${color} 11%, transparent)`,
        border: `1px solid color-mix(in oklch, ${color} 30%, transparent)`,
      }}>
      <span aria-hidden>{glyph}</span>{children}
    </span>
  );
}

type Filter = 'all' | 'pending' | 'approved' | 'rejected' | 'stale' | 'superseded';
const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'pending', label: 'Pending' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'superseded', label: 'Corrected (superseded)' },
  { key: 'stale', label: 'Stale' },
];

export function AdminResearchInbox() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'denied' | 'error'>('loading');
  const [filter, setFilter] = useState<Filter>('all');
  const [acting, setActing] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(() => {
    setState('loading');
    Promise.all([
      apiGet<{ tasks: Task[] }>('/admin/inbox/tasks'),
      apiGet<{ reports: Report[] }>('/admin/inbox/reports?limit=100'),
    ])
      .then(([t, r]) => { setTasks(t.tasks); setReports(r.reports); setState('ready'); })
      .catch((e: { status?: number }) => setState(e?.status === 404 ? 'denied' : 'error'));
  }, []);

  useEffect(() => { load(); }, [load]);

  const taskById = useMemo(() => new Map(tasks.map((t) => [t.id, t])), [tasks]);

  const visible = reports.filter((r) => {
    if (filter === 'all') return true;
    if (filter === 'stale' || filter === 'superseded') return r.state === filter;
    return r.review_status === filter;
  });

  async function review(reportId: string, verb: 'approve' | 'reject') {
    setActing(reportId);
    setActionError(null);
    try {
      await apiPost(`/admin/inbox/reports/${reportId}/${verb}`, {});
      load();
    } catch {
      setActionError(`Couldn't ${verb} that report — it may have been reviewed already. Refreshing.`);
      load();
    } finally {
      setActing(null);
    }
  }

  return (
    <ArthosPage maxWidth="max-w-copy">
      <p className="text-meta ink-fainter mb-1 mt-8">ADMIN — OWNER-FACING</p>
      <h1 className="font-serif text-headline ink-primary mb-2">Research Inbox</h1>
      <p className="ink-muted text-[13.5px] mb-8 max-w-narrative">
        Generated research lands here <strong>pending</strong> — nothing is
        treated as truth until the owner approves it. Corrections arrive as new
        versions; history is never overwritten. Research never touches
        recommendations or trades.
      </p>

      {state === 'loading' && (
        <p className="ink-fainter text-[13px]" role="status">Loading the inbox…</p>
      )}

      {state === 'denied' && (
        <StatusPanel variant="info" title="This page is owner-only." role="status"
          action={<Link to="/discover" className="text-[12.5px] font-semibold" style={{ color: 'var(--brand)' }}>Back to Discover →</Link>}>
          The Research Inbox is an operator review surface (it is also mounted
          only when the RESEARCH_INBOX flag is on). Nothing is wrong with your
          account.
        </StatusPanel>
      )}

      {state === 'error' && (
        <StatusPanel variant="error" title="Couldn't load the inbox." role="alert"
          action={
            <button type="button" onClick={load} className="px-3.5 py-1.5 rounded-full font-semibold"
              style={{ fontSize: 12.5, color: 'var(--brand-foreground)', backgroundColor: 'var(--brand)' }}>
              Try again
            </button>
          }>
          Nothing is lost — reports live on the server. Retry, or check that the
          API is reachable.
        </StatusPanel>
      )}

      {state === 'ready' && (
        <>
          <div className="flex flex-wrap gap-2 mb-6" role="group" aria-label="Filter reports">
            {FILTERS.map((f) => {
              const active = filter === f.key;
              return (
                <button key={f.key} type="button" aria-pressed={active}
                  onClick={() => setFilter(f.key)}
                  className="rounded-full px-3 h-8 font-medium transition-colors"
                  style={{
                    fontSize: 12,
                    border: active ? '1px solid var(--brand)' : '1px solid var(--border)',
                    backgroundColor: active ? 'var(--brand)' : 'transparent',
                    color: active ? 'var(--brand-foreground)' : 'var(--muted-foreground)',
                  }}>
                  {f.label}
                </button>
              );
            })}
          </div>

          {actionError && (
            <div className="mb-4">
              <StatusPanel variant="warn" title={actionError} role="alert" />
            </div>
          )}

          {visible.length === 0 ? (
            <StatusPanel variant="info"
              title={reports.length === 0 ? 'The inbox is empty.' : 'Nothing matches this filter.'}>
              {reports.length === 0
                ? 'Reports appear here when a research task delivers — generated ones always start pending.'
                : 'Try another filter; nothing has been hidden or lost.'}
            </StatusPanel>
          ) : (
            <ul className="space-y-4">
              {visible.map((r) => {
                const task = taskById.get(r.task_id);
                const rev = REVIEW_META[r.review_status];
                const st = STATE_META[r.state];
                const fresh = freshnessInfo(r.created_at);
                const citations = Array.isArray(r.citations) ? r.citations : [];
                const provenance = r.provenance ?? 'generated';
                return (
                  <li key={r.id} className="rounded-xl px-5 py-4" style={{
                    border: '1px solid var(--border)',
                    backgroundColor: 'color-mix(in oklch, var(--card) 60%, transparent)',
                  }}>
                    <div className="flex items-center justify-between gap-3 flex-wrap mb-1.5">
                      <h2 className="ink-primary text-[14.5px] font-semibold min-w-0">
                        {task?.title ?? 'Research report'}
                        <span className="ink-fainter font-normal text-[12px] ml-2">v{r.version}</span>
                      </h2>
                      <span className="flex items-center gap-1.5 flex-wrap">
                        <Chip color={rev.color} glyph={rev.glyph} title={rev.hint}>{rev.text}</Chip>
                        {r.state !== 'fresh' && (
                          <Chip color="var(--muted-foreground)" glyph="↻" title={st.hint}>{st.text}</Chip>
                        )}
                      </span>
                    </div>
                    {task?.scope && (
                      <p className="ink-fainter text-[11.5px] mb-1.5">Scope: {task.scope}</p>
                    )}
                    <p className="ink-muted text-[13px] leading-relaxed max-w-narrative">
                      {r.body.length > 280 ? `${r.body.slice(0, 280)}…` : r.body}
                    </p>
                    <p className="ink-fainter text-[11.5px] mt-2 tabular-nums">
                      {fresh.label} · {citations.length} citation{citations.length === 1 ? '' : 's'}
                      {' · '}{provenance === 'human' ? 'written by the owner' : 'machine-generated'}
                      {r.reviewed_by && ` · reviewed by ${r.reviewed_by}`}
                    </p>
                    {citations.length > 0 && (
                      <details className="mt-2">
                        <summary className="ink-fainter text-[11.5px] cursor-pointer select-none">
                          Citations
                        </summary>
                        <ul className="ink-fainter text-[11px] mt-2 space-y-1 list-disc pl-4">
                          {citations.map((c, i) => (
                            <li key={i}>{typeof c === 'string' ? c : JSON.stringify(c)}</li>
                          ))}
                        </ul>
                      </details>
                    )}
                    {r.review_status === 'pending' && (
                      <div className="flex items-center gap-3 mt-3">
                        <button type="button" disabled={acting === r.id}
                          onClick={() => review(r.id, 'approve')}
                          className="px-3.5 py-1.5 rounded-full font-semibold"
                          style={{
                            fontSize: 12.5, color: 'var(--brand-foreground)',
                            backgroundColor: 'var(--brand)',
                            opacity: acting === r.id ? 0.6 : 1,
                          }}>
                          Approve
                        </button>
                        <button type="button" disabled={acting === r.id}
                          onClick={() => review(r.id, 'reject')}
                          className="px-3.5 py-1.5 rounded-full font-semibold"
                          style={{
                            fontSize: 12.5, color: 'var(--muted-foreground)',
                            border: '1px solid var(--border)', backgroundColor: 'transparent',
                            opacity: acting === r.id ? 0.6 : 1,
                          }}>
                          Reject
                        </button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </ArthosPage>
  );
}
