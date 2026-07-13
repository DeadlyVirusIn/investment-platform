// Wave 1A — owner Publication Preflight console (dev-only surface).
// Full verdict records: ordered checks, severities, limitations, blocking
// reasons, provenance (rule set, hashes, evaluator sha), re-evaluation
// history. Server routes are owner-gated (404 posture) and mounted only
// when RECOMMENDATION_PREFLIGHT_ENABLED — this page fails closed to an
// owner-only StatusPanel everywhere else. Read + evaluate only; verdicts
// are immutable and nothing here can edit one.

import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArthosPage } from '../chrome/ArthosChrome';
import { StatusPanel } from '../components/ui/StatusPanel';
import { freshnessInfo } from '../lib/freshness';
import { apiGet, apiPost } from '@/lib/api';

type Check = {
  check_id: string; severity: 'info' | 'limitation' | 'hold' | 'block';
  passed: boolean; detail: string; beginner_text?: string;
};
type VerdictRow = {
  id: string; recommendation_id: string;
  verdict: 'READY' | 'READY_WITH_LIMITATIONS' | 'HOLD' | 'BLOCKED';
  rule_set_version: string; input_hash: string;
  checks: Check[]; limitations: Check[]; blocking_reasons: Check[];
  evaluated_at: string | null; evaluator_git_sha: string;
  source_freshness_at: string | null; created_at: string | null;
};

const VERDICT_TONE: Record<VerdictRow['verdict'], { color: string; glyph: string }> = {
  READY: { color: 'var(--brand)', glyph: '✓' },
  READY_WITH_LIMITATIONS: { color: 'oklch(0.70 0.14 75)', glyph: '◐' },
  HOLD: { color: 'oklch(0.70 0.14 75)', glyph: '⏸' },
  BLOCKED: { color: 'oklch(0.62 0.19 25)', glyph: '⛔' },
};

function VerdictChip({ v }: { v: VerdictRow['verdict'] }) {
  const t = VERDICT_TONE[v];
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full font-semibold uppercase shrink-0"
      style={{
        fontSize: 10.5, letterSpacing: '0.05em', padding: '3px 10px',
        color: t.color,
        backgroundColor: `color-mix(in oklch, ${t.color} 11%, transparent)`,
        border: `1px solid color-mix(in oklch, ${t.color} 30%, transparent)`,
      }}>
      <span aria-hidden>{t.glyph}</span>{v.replace(/_/g, ' ')}
    </span>
  );
}

const SEV_COLOR: Record<Check['severity'], string> = {
  info: 'var(--muted-foreground)',
  limitation: 'oklch(0.70 0.14 75)',
  hold: 'oklch(0.70 0.14 75)',
  block: 'oklch(0.62 0.19 25)',
};

function CheckRow({ c }: { c: Check }) {
  return (
    <li className="flex items-baseline gap-2.5 py-1"
      style={{ borderBottom: '1px solid color-mix(in oklch, var(--border) 55%, transparent)' }}>
      <span aria-hidden style={{
        color: c.passed ? 'var(--brand)' : SEV_COLOR[c.severity], fontSize: 12,
      }}>
        {c.passed ? '✓' : '✕'}
      </span>
      <code className="ink-primary" style={{ fontSize: 11.5 }}>{c.check_id}</code>
      <span className="rounded-full px-1.5" style={{
        fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.05em',
        color: SEV_COLOR[c.severity],
        border: `1px solid color-mix(in oklch, ${SEV_COLOR[c.severity]} 30%, transparent)`,
      }}>{c.severity}</span>
      <span className="ink-muted min-w-0" style={{ fontSize: 11.5 }}>{c.detail}</span>
    </li>
  );
}

function VerdictCard({ row, onReevaluate, busy }: {
  row: VerdictRow; onReevaluate: (recId: string) => void; busy: boolean;
}) {
  const fresh = freshnessInfo(row.evaluated_at);
  const failed = row.checks.filter((c) => !c.passed);
  return (
    <li className="rounded-xl px-5 py-4" style={{
      border: '1px solid var(--border)',
      backgroundColor: 'color-mix(in oklch, var(--card) 60%, transparent)',
    }}>
      <div className="flex items-center justify-between gap-3 flex-wrap mb-1.5">
        <code className="ink-primary text-[12px]">{row.recommendation_id}</code>
        <VerdictChip v={row.verdict} />
      </div>
      <p className="ink-fainter text-[11px] tabular-nums">
        {fresh.label} · rule set {row.rule_set_version} · evaluator{' '}
        {row.evaluator_git_sha.slice(0, 12)} · input{' '}
        {row.input_hash?.slice(0, 12)}…
      </p>
      {failed.length > 0 && (
        <details className="mt-2" open={row.verdict !== 'READY_WITH_LIMITATIONS'}>
          <summary className="ink-muted text-[12px] cursor-pointer select-none">
            {failed.length} failed check{failed.length === 1 ? '' : 's'}
          </summary>
          <ul className="mt-1.5">{failed.map((c) => <CheckRow key={c.check_id} c={c} />)}</ul>
        </details>
      )}
      <details className="mt-1.5">
        <summary className="ink-fainter text-[11.5px] cursor-pointer select-none">
          All {row.checks.length} checks (ordered)
        </summary>
        <ul className="mt-1.5">{row.checks.map((c) => <CheckRow key={c.check_id} c={c} />)}</ul>
      </details>
      <button type="button" disabled={busy}
        onClick={() => onReevaluate(row.recommendation_id)}
        className="mt-3 px-3 py-1.5 rounded-full font-semibold"
        style={{
          fontSize: 12, color: 'var(--muted-foreground)',
          border: '1px solid var(--border)', backgroundColor: 'transparent',
          opacity: busy ? 0.6 : 1,
        }}>
        Re-evaluate (appends a new record)
      </button>
    </li>
  );
}

export function AdminPreflight() {
  const [rows, setRows] = useState<VerdictRow[]>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'denied' | 'error'>('loading');
  const [filter, setFilter] = useState<string>('all');
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    setState('loading');
    const qs = filter === 'all' ? '' : `?verdict=${filter}`;
    apiGet<{ verdicts: VerdictRow[] }>(`/admin/preflight/verdicts${qs}`)
      .then((r) => { setRows(r.verdicts); setState('ready'); })
      .catch((e: { status?: number }) => setState(e?.status === 404 ? 'denied' : 'error'));
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  async function reevaluate(recId: string) {
    setBusy(recId);
    try {
      await apiPost(`/admin/preflight/recommendations/${encodeURIComponent(recId)}/evaluate`, {});
      load();
    } catch { /* surfaced by reload state */ } finally {
      setBusy(null);
    }
  }

  return (
    <ArthosPage maxWidth="max-w-copy">
      <p className="text-meta ink-fainter mb-1 mt-8">ADMIN — OWNER-FACING</p>
      <h1 className="font-serif text-headline ink-primary mb-2">Publication Preflight</h1>
      <p className="ink-muted text-[13.5px] mb-8 max-w-narrative">
        The deterministic gate between the engine and Discover. Verdicts are
        computed from stored facts only — no model, prompt, or person can
        override one; re-evaluation appends, never edits.
      </p>

      {state === 'loading' && (
        <p className="ink-fainter text-[13px]" role="status">Loading verdicts…</p>
      )}

      {state === 'denied' && (
        <StatusPanel variant="info" title="This page is owner-only." role="status"
          action={<Link to="/discover" className="text-[12.5px] font-semibold" style={{ color: 'var(--brand)' }}>Back to Discover →</Link>}>
          The preflight console is an operator surface (it is also mounted
          only when the RECOMMENDATION_PREFLIGHT flag is on).
        </StatusPanel>
      )}

      {state === 'error' && (
        <StatusPanel variant="error" title="Couldn't load verdicts." role="alert"
          action={
            <button type="button" onClick={load} className="px-3.5 py-1.5 rounded-full font-semibold"
              style={{ fontSize: 12.5, color: 'var(--brand-foreground)', backgroundColor: 'var(--brand)' }}>
              Try again
            </button>
          }>
          Nothing is lost — verdicts are immutable server records.
        </StatusPanel>
      )}

      {state === 'ready' && (
        <>
          <div className="flex flex-wrap gap-2 mb-6" role="group" aria-label="Filter verdicts">
            {['all', 'READY', 'READY_WITH_LIMITATIONS', 'HOLD', 'BLOCKED'].map((f) => {
              const active = filter === f;
              return (
                <button key={f} type="button" aria-pressed={active}
                  onClick={() => setFilter(f)}
                  className="rounded-full px-3 h-8 font-medium transition-colors"
                  style={{
                    fontSize: 12,
                    border: active ? '1px solid var(--brand)' : '1px solid var(--border)',
                    backgroundColor: active ? 'var(--brand)' : 'transparent',
                    color: active ? 'var(--brand-foreground)' : 'var(--muted-foreground)',
                  }}>
                  {f === 'all' ? 'All' : f.replace(/_/g, ' ')}
                </button>
              );
            })}
          </div>
          {rows.length === 0 ? (
            <StatusPanel variant="info" title="No verdicts recorded yet.">
              Verdicts appear as candidates are evaluated at publication time,
              or evaluate one from a recommendation id via the API.
            </StatusPanel>
          ) : (
            <ul className="space-y-4">
              {rows.map((r) => (
                <VerdictCard key={r.id} row={r} onReevaluate={reevaluate}
                  busy={busy === r.recommendation_id} />
              ))}
            </ul>
          )}
        </>
      )}
    </ArthosPage>
  );
}
