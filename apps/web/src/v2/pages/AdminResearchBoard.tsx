// Research Mission Board — Wave 2B. Owner-only operational overview
// composed ENTIRELY from existing Research Inbox + Agent Gateway state
// (GET /api/admin/inbox/mission-board, rule set mission-board-1).
//
// This page sits ABOVE the Research Inbox: every action is a LINK into the
// existing Inbox surface — nothing is approved, corrected, cancelled, or
// launched from here. Frontend gate: renders only when VITE_RESEARCH_INBOX
// === '1' (same flag as the Inbox); server gate: owner-only 404 posture,
// route mounted only when RESEARCH_INBOX_ENABLED is on.
//
// Desktop: calm responsive column grid (no sideways-only board). Mobile
// (~390px): segmented column tabs + one vertical list; counts preserved.

import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArthosPage } from '../chrome/ArthosChrome';
import { StatusPanel } from '../components/ui/StatusPanel';
import { researchInboxEnabled } from './AdminResearchInbox';
import { apiGet } from '@/lib/api';

export { researchInboxEnabled };

type Freshness = 'fresh' | 'aging' | 'stale' | 'unknown';

type TaskCard = {
  kind: 'task';
  card_id: string;
  task_id: string;
  column: string;
  title: string | null;
  question_preview: string | null;
  scope: string | null;
  task_status: string | null;
  schedule: { defined: boolean; note?: string };
  is_follow_up: boolean;
  follow_up: {
    available: boolean; note?: string;
    parent_task_id?: string | null; parent_title?: string | null;
    depth?: number;
    /** mission-board-2: exact source report version (null = not recorded). */
    source_version?: number | null;
    source_superseded?: boolean | null;
  } | null;
  /** mission-board-2: linked gateway-job execution summary (null = none). */
  execution: {
    attempts: number; retries: number;
    active_status: string | null;
    last_attempt_at: string | null;
    last_error: string | null;
    history_available: boolean;
  } | null;
  latest_report: {
    report_id: string; version: number; review_status: string;
    provenance: string | null; generated_by_label: string;
    delivered_at: string | null; citation_count: number;
    review_age_days: number | null;
  } | null;
  chain: {
    versions: number; prior_retained: number; corrections: number;
    current_version: number | null; current_status: string | null;
  };
  freshness: Freshness;
  freshness_reason: string | null;
};

type JobCard = {
  kind: 'gateway_job';
  card_id: string;
  column: string;
  title: string;
  job_uid: string;
  job_type: string;
  job_status: string;
  token_prefix: string | null;
  task_link: null;
  queued_at: string | null;
  started_at: string | null;
  freshness: Freshness;
  freshness_reason: string | null;
};

type Card = TaskCard | JobCard;

type BoardColumn = {
  key: string; title: string; help: string;
  total: number; shown: number; overflow: number; cards: Card[];
};

type Board = {
  rule_set_version: string;
  generated_at: string;
  gateway_enabled: boolean;
  counts: Record<string, number>;
  columns: BoardColumn[];
  board_health: { complete: boolean; notes: string[] };
};

const COLUMN_LABELS: Record<string, string> = {
  queued: 'Queued', running: 'Running', review_needed: 'Review needed',
  delivered: 'Delivered', corrected: 'Corrected', stale: 'Stale',
  failed: 'Failed',
};

const FRESHNESS_META: Record<Freshness, { text: string; color: string }> = {
  fresh: { text: 'Fresh', color: 'var(--brand)' },
  aging: { text: 'Aging', color: 'oklch(0.70 0.14 75)' },
  stale: { text: 'Stale', color: 'oklch(0.62 0.19 25)' },
  unknown: { text: 'Freshness unknown', color: 'var(--muted-foreground)' },
};

function Pill({ color, children, title }: {
  color: string; children: React.ReactNode; title?: string;
}) {
  return (
    <span title={title} className="inline-flex items-center rounded-full font-semibold uppercase shrink-0"
      style={{
        fontSize: 10, letterSpacing: '0.05em', padding: '2px 8px', color,
        backgroundColor: `color-mix(in oklch, ${color} 11%, transparent)`,
        border: `1px solid color-mix(in oklch, ${color} 30%, transparent)`,
      }}>
      {children}
    </span>
  );
}

type ExecutionAttempt = {
  attempt: number; job_uid: string; job_type: string; status: string;
  token_prefix: string | null;
  queued_at: string | null; started_at: string | null;
  finished_at: string | null;
  result_summary: string | null; error_summary: string | null;
  is_retry: boolean;
};

/** mission-board-2 — linked-job summary + expandable owner-only execution
 *  history (read-only; fetched on demand from the typed history route).
 *  No raw JSON, no params, no cancel action. */
function ExecutionSummary({ card }: { card: TaskCard }) {
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState<{
    attempts: ExecutionAttempt[]; total: number; overflow: number;
  } | null>(null);
  const [failed, setFailed] = useState(false);
  const ex = card.execution;
  if (!ex) return null;

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && history === null && !failed) {
      apiGet<{ attempts: ExecutionAttempt[]; total: number; overflow: number }>(
        `/admin/inbox/tasks/${card.task_id}/execution-history`)
        .then(setHistory)
        .catch(() => setFailed(true));
    }
  }

  return (
    <div className="mt-1">
      <p className="ink-fainter text-[11px] tabular-nums">
        {ex.attempts} run{ex.attempts === 1 ? '' : 's'}
        {ex.retries > 0 && ` (${ex.retries} ${ex.retries === 1 ? 'retry' : 'retries'})`}
        {ex.active_status && ` · ${ex.active_status} now`}
        {ex.last_error && ` · last failure: ${ex.last_error}`}
      </p>
      <button type="button" onClick={toggle} aria-expanded={open}
        className="text-[11.5px] font-semibold mt-0.5"
        style={{ color: 'var(--brand)', background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}>
        {open ? 'Hide execution history' : 'Execution history →'}
      </button>
      {open && (
        <div className="mt-1.5">
          {failed ? (
            <p className="ink-fainter text-[11px]">Execution history is unavailable right now.</p>
          ) : history === null ? (
            <p className="ink-fainter text-[11px]" role="status">Loading history…</p>
          ) : history.attempts.length === 0 ? (
            <p className="ink-fainter text-[11px]">No recorded runs.</p>
          ) : (
            <ul className="space-y-1" aria-label="Execution attempts">
              {history.attempts.map((a) => (
                <li key={a.job_uid} className="ink-fainter text-[11px] tabular-nums rounded px-2 py-1"
                  style={{ border: '1px solid var(--border)' }}>
                  Attempt {a.attempt}{a.is_retry ? ' (retry)' : ''} · {a.job_type} · {a.status}
                  {a.queued_at && ` · ${new Date(a.queued_at).toLocaleString()}`}
                  {a.error_summary && <span> · {a.error_summary}</span>}
                  {a.result_summary && a.status === 'succeeded' && <span> · {a.result_summary}</span>}
                </li>
              ))}
            </ul>
          )}
          {history && history.overflow > 0 && (
            <p className="ink-fainter text-[11px] mt-1">+{history.overflow} earlier run{history.overflow === 1 ? '' : 's'} not shown.</p>
          )}
        </div>
      )}
    </div>
  );
}

function CardView({ card }: { card: Card }) {
  const fresh = FRESHNESS_META[card.freshness] ?? FRESHNESS_META.unknown;
  return (
    <li className="rounded-xl px-4 py-3" style={{
      border: '1px solid var(--border)',
      backgroundColor: 'color-mix(in oklch, var(--card) 60%, transparent)',
    }}>
      <div className="flex items-start justify-between gap-2 mb-1">
        <h4 className="ink-primary text-[13px] font-semibold min-w-0 leading-snug">
          {card.title ?? 'Untitled'}
        </h4>
        <Pill color={fresh.color} title={card.freshness_reason ?? undefined}>
          {fresh.text}
        </Pill>
      </div>

      {card.kind === 'task' ? (
        <>
          {card.question_preview && (
            <p className="ink-muted text-[12px] leading-relaxed mb-1.5">
              {card.question_preview}
            </p>
          )}
          <p className="ink-fainter text-[11px] tabular-nums">
            {card.latest_report ? (
              <>
                v{card.latest_report.version} · {card.latest_report.review_status}
                {' · '}{card.latest_report.generated_by_label}
                {' · '}{card.latest_report.citation_count} citation{card.latest_report.citation_count === 1 ? '' : 's'}
                {card.latest_report.review_age_days != null &&
                  ` · waiting ${card.latest_report.review_age_days}d`}
              </>
            ) : (
              <>no report yet{card.schedule.defined ? ' · schedule defined (nothing runs automatically)' : ''}</>
            )}
          </p>
          {card.chain.prior_retained > 0 && (
            <p className="ink-fainter text-[11px] mt-1">
              {card.chain.prior_retained} earlier version{card.chain.prior_retained === 1 ? '' : 's'} retained
              {card.chain.current_status ? ` — current v${card.chain.current_version} is ${card.chain.current_status}` : ''}
            </p>
          )}
          {card.is_follow_up && (
            <p className="ink-fainter text-[11px] mt-1">
              {card.follow_up?.available === false
                ? (card.follow_up.note ?? 'relationship unavailable')
                : (
                  <>
                    Follow-up to {card.follow_up?.parent_title ?? 'an earlier task'}
                    {card.follow_up?.source_version != null
                      ? ` — from v${card.follow_up.source_version}${card.follow_up.source_superseded ? ' (superseded — a newer version exists)' : ''}`
                      : ' — source version was not recorded'}
                  </>
                )}
            </p>
          )}
          {card.execution && (
            <ExecutionSummary card={card} />
          )}
          {card.freshness !== 'fresh' && card.freshness_reason && (
            <p className="ink-fainter text-[11px] mt-1">{card.freshness_reason}</p>
          )}
          <p className="mt-2">
            <Link to="/admin/research-inbox" className="text-[12px] font-semibold"
              style={{ color: 'var(--brand)' }}>
              {card.column === 'review_needed' ? 'Review in the Inbox →' : 'Open in the Inbox →'}
            </Link>
          </p>
        </>
      ) : (
        <>
          <p className="ink-fainter text-[11px] tabular-nums">
            {card.job_status} · {card.token_prefix ?? 'token'} · {card.job_uid}
          </p>
          <p className="ink-fainter text-[11px] mt-1">
            Standalone historical gateway job — recorded before task links
            existed; never guessed onto a task.
          </p>
          {card.freshness_reason && card.freshness !== 'fresh' && (
            <p className="ink-fainter text-[11px] mt-1">{card.freshness_reason}</p>
          )}
        </>
      )}
    </li>
  );
}

function ColumnView({ col }: { col: BoardColumn }) {
  return (
    <section aria-label={`${COLUMN_LABELS[col.key] ?? col.title} column`}
      className="min-w-0">
      <div className="flex items-baseline justify-between gap-2 mb-1">
        <h3 className="ink-primary text-[13px] font-semibold">
          {COLUMN_LABELS[col.key] ?? col.title}
          <span className="ink-fainter font-normal ml-1.5 tabular-nums">{col.total}</span>
        </h3>
      </div>
      <p className="ink-fainter text-[11px] leading-snug mb-2">{col.help}</p>
      {col.cards.length === 0 ? (
        <p className="ink-fainter text-[11.5px] rounded-lg px-3 py-2"
          style={{ border: '1px dashed var(--border)' }}>
          Nothing here right now.
        </p>
      ) : (
        <ul className="space-y-2.5">
          {col.cards.map((c) => <CardView key={c.card_id} card={c} />)}
        </ul>
      )}
      {col.overflow > 0 && (
        <p className="ink-fainter text-[11px] mt-2">
          +{col.overflow} more — open the <Link to="/admin/research-inbox"
            style={{ color: 'var(--brand)' }}>Inbox</Link> for the full list.
        </p>
      )}
    </section>
  );
}

export function AdminResearchBoard() {
  const [board, setBoard] = useState<Board | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'denied' | 'error'>('loading');
  const [mobileColumn, setMobileColumn] = useState<string>('review_needed');
  const [isNarrow, setIsNarrow] = useState<boolean>(
    () => typeof window !== 'undefined'
      && typeof window.matchMedia === 'function'
      && window.matchMedia('(max-width: 640px)').matches);

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(max-width: 640px)');
    const on = (e: MediaQueryListEvent) => setIsNarrow(e.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);

  const load = useCallback(() => {
    setState('loading');
    apiGet<Board>('/admin/inbox/mission-board')
      .then((b) => { setBoard(b); setState('ready'); })
      .catch((e: { status?: number }) => setState(e?.status === 404 ? 'denied' : 'error'));
  }, []);

  useEffect(() => { load(); }, [load]);

  const counts = board?.counts ?? {};
  const active = (counts.queued ?? 0) + (counts.running ?? 0) + (counts.review_needed ?? 0);

  return (
    <ArthosPage maxWidth="max-w-6xl">
      <p className="text-meta ink-fainter mb-1 mt-8">ADMIN — OWNER-FACING</p>
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h1 className="font-serif text-headline ink-primary mb-2">Research Mission Board</h1>
        <Link to="/admin/research-inbox" className="text-[12.5px] font-semibold"
          style={{ color: 'var(--brand)' }}>
          Research Inbox →
        </Link>
      </div>
      <p className="ink-muted text-[13.5px] mb-6 max-w-narrative">
        One view over existing research state — tasks, report versions and
        gateway jobs. The board never runs anything: every action links into
        the Research Inbox, and nothing here is a new source of truth.
      </p>

      {state === 'loading' && (
        <p className="ink-fainter text-[13px]" role="status">Loading the board…</p>
      )}

      {state === 'denied' && (
        <StatusPanel variant="info" title="This page is owner-only." role="status"
          action={<Link to="/discover" className="text-[12.5px] font-semibold" style={{ color: 'var(--brand)' }}>Back to Discover →</Link>}>
          The Mission Board is an operator surface (mounted only when the
          RESEARCH_INBOX flag is on). Nothing is wrong with your account.
        </StatusPanel>
      )}

      {state === 'error' && (
        <StatusPanel variant="error" title="Couldn't load the board." role="alert"
          action={
            <button type="button" onClick={load} className="px-3.5 py-1.5 rounded-full font-semibold"
              style={{ fontSize: 12.5, color: 'var(--brand-foreground)', backgroundColor: 'var(--brand)' }}>
              Try again
            </button>
          }>
          Nothing is lost — the board is a read-only view; tasks and reports
          live on the server.
        </StatusPanel>
      )}

      {state === 'ready' && board && (
        <>
          {/* top summary */}
          <div className="flex flex-wrap gap-x-6 gap-y-2 mb-4 tabular-nums"
            role="group" aria-label="Board summary">
            <p className="ink-muted text-[12.5px]"><strong className="ink-primary">{active}</strong> active</p>
            <p className="ink-muted text-[12.5px]"><strong className="ink-primary">{counts.review_needed ?? 0}</strong> review needed</p>
            <p className="ink-muted text-[12.5px]"><strong className="ink-primary">{counts.stale ?? 0}</strong> stale</p>
            <p className="ink-muted text-[12.5px]"><strong className="ink-primary">{counts.failed ?? 0}</strong> failed</p>
          </div>

          {board.board_health.notes.map((n) => (
            <p key={n} className="ink-fainter text-[12px] mb-2" role="note">{n}</p>
          ))}

          {isNarrow ? (
            <>
              <div className="flex flex-wrap gap-2 mb-4" role="group"
                aria-label="Choose a column">
                {board.columns.map((col) => {
                  const activeTab = mobileColumn === col.key;
                  return (
                    <button key={col.key} type="button" aria-pressed={activeTab}
                      onClick={() => setMobileColumn(col.key)}
                      className="rounded-full px-3 h-9 font-medium"
                      style={{
                        fontSize: 12,
                        border: activeTab ? '1px solid var(--brand)' : '1px solid var(--border)',
                        backgroundColor: activeTab ? 'var(--brand)' : 'transparent',
                        color: activeTab ? 'var(--brand-foreground)' : 'var(--muted-foreground)',
                      }}>
                      {COLUMN_LABELS[col.key] ?? col.title} ({col.total})
                    </button>
                  );
                })}
              </div>
              {board.columns.filter((c) => c.key === mobileColumn).map((col) => (
                <ColumnView key={col.key} col={col} />
              ))}
            </>
          ) : (
            <div className="grid gap-5"
              style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))' }}>
              {board.columns.map((col) => <ColumnView key={col.key} col={col} />)}
            </div>
          )}

          <p className="ink-fainter text-[11px] mt-8 tabular-nums">
            Rule set {board.rule_set_version} · generated {new Date(board.generated_at).toLocaleString()}
            {!board.gateway_enabled && ' · Agent Gateway off'}
          </p>
        </>
      )}
    </ArthosPage>
  );
}
