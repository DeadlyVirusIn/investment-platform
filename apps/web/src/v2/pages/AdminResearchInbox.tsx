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

type Task = {
  id: string; title: string; question: string; scope: string | null;
  created_at: string | null;
  /** Wave 2C — structured follow-up provenance (nulls on historical rows). */
  follow_up_of_task_id?: string | null;
  source_report_id?: string | null;
  source_report_version?: number | null;
  source_report_superseded?: boolean | null;
};
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
  const [correcting, setCorrecting] = useState<Report | null>(null);
  const [followUp, setFollowUp] = useState<Report | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

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

  // Version chain per task (v1 → v2 → v3), newest last.
  const chainByTask = useMemo(() => {
    const m = new Map<string, Report[]>();
    for (const r of reports) {
      const arr = m.get(r.task_id) ?? [];
      arr.push(r);
      m.set(r.task_id, arr);
    }
    for (const arr of m.values()) arr.sort((a, b) => a.version - b.version);
    return m;
  }, [reports]);

  async function afterCorrection(newVersion: number) {
    setCorrecting(null);
    setFlash(`Created v${newVersion}. Earlier versions remain available and unchanged.`);
    load();
    // focus the new version heading once rendered
    setTimeout(() => {
      document.getElementById('inbox-flash')?.focus();
    }, 50);
  }

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
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h1 className="font-serif text-headline ink-primary mb-2">Research Inbox</h1>
        <Link to="/admin/research-board" className="text-[12.5px] font-semibold"
          style={{ color: 'var(--brand)' }}>
          Mission Board →
        </Link>
      </div>
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
          {flash && (
            <div className="mb-4">
              <div id="inbox-flash" tabIndex={-1} className="outline-none">
                <StatusPanel variant="success" title={flash} role="status" />
              </div>
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
                    {task?.follow_up_of_task_id && (
                      <p className="ink-fainter text-[11.5px] mb-1.5">
                        Follow-up to {taskById.get(task.follow_up_of_task_id)?.title ?? 'an earlier task'}
                        {task.source_report_version != null
                          ? <> — from v{task.source_report_version}
                            {task.source_report_superseded && ' (that version is now superseded; it remains retained)'}</>
                          : <> — follow-up source version was not recorded.</>}
                      </p>
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
                    {(() => {
                      const chain = chainByTask.get(r.task_id) ?? [r];
                      const supersede = formatSupersedesNoteForVersion(r, chain);
                      return supersede ? (
                        <p className="ink-fainter text-[11px] mt-1.5">{supersede}</p>
                      ) : null;
                    })()}
                    <div className="flex items-center gap-3 mt-3 flex-wrap">
                      {r.review_status === 'pending' && (
                        <>
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
                        </>
                      )}
                      {/* Correct — only the LATEST version of a report chain */}
                      {r.state !== 'superseded' && (
                        <button type="button" onClick={() => setCorrecting(r)}
                          className="px-3.5 py-1.5 rounded-full font-semibold"
                          style={{ fontSize: 12.5, color: 'var(--muted-foreground)', border: '1px solid var(--border)' }}>
                          Correct report
                        </button>
                      )}
                      <button type="button" onClick={() => setFollowUp(r)}
                        className="px-3.5 py-1.5 rounded-full font-semibold"
                        style={{ fontSize: 12.5, color: 'var(--muted-foreground)', border: '1px solid var(--border)' }}>
                        Create follow-up
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          {correcting && (
            <CorrectionDialog report={correcting}
              onClose={() => setCorrecting(null)}
              onDone={afterCorrection} />
          )}
          {followUp && (
            <FollowUpDialog report={followUp} taskById={taskById}
              onClose={() => setFollowUp(null)}
              onDone={(taskId) => { setFollowUp(null); setFlash(`Follow-up task created (${taskId.slice(0, 8)}…). The report was not modified.`); }} />
          )}
        </>
      )}
    </ArthosPage>
  );
}

// ── Version-chain helper ────────────────────────────────────────────────
function formatSupersedesNoteForVersion(r: Report, chain: Report[]): string | null {
  if (chain.length < 2) return null;
  const idx = chain.findIndex((c) => c.id === r.id);
  if (idx <= 0) return null;
  const prev = chain[idx - 1];
  return `Supersedes v${prev.version}${prev.review_status === 'rejected' ? ' (rejected)' : ''} — earlier versions remain available.`;
}

const dialogBackdrop: React.CSSProperties = {
  position: 'fixed', inset: 0, zIndex: 60,
  backgroundColor: 'color-mix(in oklch, var(--foreground) 30%, transparent)',
  display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
  padding: '5vh 1rem', overflowY: 'auto',
};
const dialogCard: React.CSSProperties = {
  width: '100%', maxWidth: 560, backgroundColor: 'var(--background)',
  border: '1px solid var(--border)', borderRadius: 16, padding: '1.5rem',
};
const fieldStyle: React.CSSProperties = {
  width: '100%', fontSize: 13, borderRadius: 8, padding: '8px 12px',
  border: '1px solid var(--border)', backgroundColor: 'var(--surface)',
  color: 'var(--foreground)',
};

function CorrectionDialog({ report, onClose, onDone }: {
  report: Report; onClose: () => void; onDone: (v: number) => void;
}) {
  const [body, setBody] = useState(report.body);
  const [citationsText, setCitationsText] = useState(
    JSON.stringify(report.citations ?? [], null, 2));
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true); setErr(null);
    let citations: unknown;
    if (citationsText.trim()) {
      try { citations = JSON.parse(citationsText); }
      catch { setErr('Citations must be valid JSON (the existing format).'); setBusy(false); return; }
    }
    try {
      const out = await apiPost<{ version: number }>(
        `/admin/inbox/reports/${report.id}/correct`,
        { body, citations, reason });
      onDone(out.version);
    } catch (e) {
      const s = (e as { status?: number })?.status;
      setErr(s === 409 ? 'This is no longer the latest version — reload and correct the current one.'
        : s === 422 ? 'A citation is invalid (each needs a url and observed_at).'
        : "Couldn't save the correction.");
      setBusy(false);
    }
  }

  return (
    <div style={dialogBackdrop} role="dialog" aria-modal="true"
      aria-labelledby="correct-title" onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}>
      <div style={dialogCard}>
        <h2 id="correct-title" className="ink-primary text-[16px] font-semibold font-serif mb-1">
          Correct this report
        </h2>
        <p className="ink-muted text-[12.5px] leading-relaxed mb-3">
          The current version is <strong>not edited</strong>. A new version is
          created, earlier versions stay available, and the correction is
          recorded as owner-authored (approved) — it never becomes a
          machine-generated pending report.
        </p>
        <label className="block mb-3">
          <span className="ink-primary text-[12px] font-medium block mb-1">Corrected body</span>
          <textarea value={body} onChange={(e) => setBody(e.target.value)}
            rows={6} style={fieldStyle} />
        </label>
        <label className="block mb-3">
          <span className="ink-primary text-[12px] font-medium block mb-1">Citations (existing JSON format)</span>
          <textarea value={citationsText} onChange={(e) => setCitationsText(e.target.value)}
            rows={4} style={{ ...fieldStyle, fontFamily: 'monospace', fontSize: 11 }} />
        </label>
        <label className="block mb-3">
          <span className="ink-primary text-[12px] font-medium block mb-1">Correction reason</span>
          <input type="text" value={reason} maxLength={500}
            onChange={(e) => setReason(e.target.value)} style={fieldStyle} />
        </label>
        {err && <p className="text-[12px] mb-3" role="alert" style={{ color: 'oklch(0.62 0.19 25)' }}>{err}</p>}
        <div className="flex items-center gap-3">
          <button type="button" disabled={busy || !body.trim() || !reason.trim()}
            onClick={submit} className="px-4 py-2 rounded-full font-semibold"
            style={{ fontSize: 13, color: 'var(--brand-foreground)', backgroundColor: 'var(--brand)', opacity: busy || !body.trim() || !reason.trim() ? 0.5 : 1 }}>
            Create corrected version
          </button>
          <button type="button" onClick={onClose}
            className="px-4 py-2 rounded-full font-medium"
            style={{ fontSize: 13, color: 'var(--muted-foreground)', border: '1px solid var(--border)' }}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

function FollowUpDialog({ report, taskById, onClose, onDone }: {
  report: Report; taskById: Map<string, Task>;
  onClose: () => void; onDone: (taskId: string) => void;
}) {
  const srcTask = taskById.get(report.task_id);
  const [title, setTitle] = useState(
    srcTask ? `Follow up: ${srcTask.title}` : 'Follow-up investigation');
  const [question, setQuestion] = useState(
    srcTask ? `Following up on: ${srcTask.question}` : '');
  const [scope] = useState(srcTask?.scope ?? '');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true); setErr(null);
    try {
      const out = await apiPost<{ id: string }>(
        `/admin/inbox/reports/${report.id}/follow-up`,
        { title, question, scope: scope || undefined });
      onDone(out.id);
    } catch {
      setErr("Couldn't create the follow-up task.");
      setBusy(false);
    }
  }

  return (
    <div style={dialogBackdrop} role="dialog" aria-modal="true"
      aria-labelledby="followup-title" onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}>
      <div style={dialogCard}>
        <h2 id="followup-title" className="ink-primary text-[16px] font-semibold font-serif mb-1">
          Create a follow-up task
        </h2>
        <p className="ink-muted text-[12.5px] leading-relaxed mb-3">
          This creates a new research task. The report is <strong>not
          modified</strong>, and nothing runs automatically — the task waits
          for the existing review workflow.
        </p>
        <label className="block mb-3">
          <span className="ink-primary text-[12px] font-medium block mb-1">Title</span>
          <input type="text" value={title} maxLength={200}
            onChange={(e) => setTitle(e.target.value)} style={fieldStyle} />
        </label>
        <label className="block mb-3">
          <span className="ink-primary text-[12px] font-medium block mb-1">Question</span>
          <textarea value={question} rows={4} maxLength={4000}
            onChange={(e) => setQuestion(e.target.value)} style={fieldStyle} />
        </label>
        {err && <p className="text-[12px] mb-3" role="alert" style={{ color: 'oklch(0.62 0.19 25)' }}>{err}</p>}
        <div className="flex items-center gap-3">
          <button type="button" disabled={busy || !title.trim() || !question.trim()}
            onClick={submit} className="px-4 py-2 rounded-full font-semibold"
            style={{ fontSize: 13, color: 'var(--brand-foreground)', backgroundColor: 'var(--brand)', opacity: busy || !title.trim() || !question.trim() ? 0.5 : 1 }}>
            Create follow-up
          </button>
          <button type="button" onClick={onClose}
            className="px-4 py-2 rounded-full font-medium"
            style={{ fontSize: 13, color: 'var(--muted-foreground)', border: '1px solid var(--border)' }}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
