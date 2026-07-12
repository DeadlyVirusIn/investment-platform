// Honest Numbers — owner Trust Center (real read-only feeds via
// /api/admin/trust-center; server-side owner guard 404s everyone else).
// Not linked from user navigation; reachable only inside the admin console.
//
// Elite WebUI pass (audit H4/H9): raw JSON replaced with explained metric
// rows + the shared EvidenceBadge; the untouched payload stays one
// disclosure away ("View raw data") so nothing is hidden — just organized.

import { useEffect, useState } from 'react';
import { apiGet } from '@/lib/api';
import { ArthosPage } from '../chrome/ArthosChrome';
import { EvidenceBadge, toEvidenceState } from '../components/ui/EvidenceBadge';
import { StatusPanel } from '../components/ui/StatusPanel';
import { Link } from 'react-router-dom';

type Section = { title: string; label: string; body: string; data: Record<string, unknown> };
type Payload = { generated_at: string; audience: string; sections: Section[] };

// Plain-English names + one-line meanings for every backend data key.
// Unknown keys fall back to a de-underscored name so new backend fields
// degrade gracefully instead of leaking developer vocabulary.
const KEY_META: Record<string, { name: string; meaning?: string }> = {
  stuck_null_schedules: { name: 'Jobs stuck without a next run', meaning: 'Scheduled jobs whose next run time is missing; they self-heal on the next tick.' },
  overdue_jobs: { name: 'Jobs overdue by more than a day' },
  newest_bar_ts: { name: 'Newest market data', meaning: 'Timestamp of the most recent ingested daily price bar.' },
  age_hours: { name: 'Data age (hours)' },
  git_sha: { name: 'Running code version' },
  git_branch: { name: 'Branch' },
  git_dirty: { name: 'Uncommitted changes in image' },
  build_ts: { name: 'Image built' },
  flags: { name: 'Provenance flags' },
  live_recommendations: { name: 'Recommendations issued (this environment)' },
  resolved_outcomes: { name: 'Ideas resolved to an outcome' },
  unresolved_outcomes: { name: 'Ideas still open' },
  latest_equity: { name: 'Latest engine-book equity (paper $)' },
  as_of: { name: 'As of' },
  options_enabled: { name: 'Options subsystem' },
  ml_can_affect_trades: { name: 'ML can affect trades' },
  ingest_contracts_enabled: { name: 'Ingest contracts' },
  demo_device_mode: { name: 'Demo device mode' },
};

function fmtValue(key: string, v: unknown): string {
  if (v == null) return '—';
  if (typeof v === 'boolean') return v ? 'On' : 'Off';
  if (Array.isArray(v)) return v.length ? v.join(', ') : '—';
  if (typeof v === 'number') {
    if (/equity|\$/.test(key)) {
      return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    return v.toLocaleString();
  }
  const s = String(v);
  // Humanize ISO timestamps without hiding the precise value (title attr
  // keeps the raw string reachable via the raw-data disclosure anyway).
  const t = Date.parse(s);
  if (!Number.isNaN(t) && /\d{4}-\d{2}-\d{2}/.test(s)) {
    return new Date(t).toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  }
  return s;
}

function MetricRows({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  if (entries.length === 0) return null;
  return (
    <dl className="mt-3 space-y-2">
      {entries.map(([k, v]) => {
        const meta = KEY_META[k] ?? { name: k.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()) };
        return (
          <div key={k} className="flex items-baseline justify-between gap-4 flex-wrap">
            <dt className="ink-muted text-[12.5px]">
              {meta.name}
              {meta.meaning && (
                <span className="block ink-fainter text-[11px] leading-snug max-w-narrative">{meta.meaning}</span>
              )}
            </dt>
            <dd className="ink-primary text-[13px] tabular-nums font-medium text-right">
              {fmtValue(k, v)}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

function SectionCard({ s }: { s: Section }) {
  return (
    <section className="rounded-xl px-5 py-4 mb-4" style={{
      border: '1px solid var(--border)',
      backgroundColor: 'color-mix(in oklch, var(--card) 60%, transparent)',
    }}>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h3 className="ink-primary text-[14.5px] font-semibold">{s.title}</h3>
        <EvidenceBadge state={toEvidenceState(s.label)} />
      </div>
      <p className="ink-muted text-[12.5px] leading-relaxed mt-1.5 max-w-narrative">{s.body}</p>
      <MetricRows data={s.data} />
      {Object.keys(s.data).length > 0 && (
        <details className="mt-3">
          <summary className="ink-fainter text-[11.5px] cursor-pointer select-none">
            View raw data
          </summary>
          <pre className="ink-fainter text-[10.5px] mt-2 overflow-x-auto">
            {JSON.stringify(s.data, null, 1)}
          </pre>
        </details>
      )}
    </section>
  );
}

// Organize the backend's flat section list into the trust-dashboard story:
// health first, then evidence, then honesty (incidents/limitations), then
// provenance. Sections not matched fall into the group that mentions them.
const GROUPS: { heading: string; blurb: string; titles: string[] }[] = [
  {
    heading: 'System health',
    blurb: 'Is the machine running, and on fresh data?',
    titles: ['System status', 'Data freshness'],
  },
  {
    heading: 'Recommendation evidence',
    blurb: 'How much history sits behind the ideas, and how well confidence is calibrated.',
    titles: ['Recommendation sample size', 'Resolved vs unresolved outcomes', 'Confidence calibration', 'Paper record', 'Benchmark comparison'],
  },
  {
    heading: 'Honesty ledger',
    blurb: 'What has gone wrong, what is known to be weak, and what changed.',
    titles: ['Known limitations', 'Recent incidents', 'Model / research change log', 'Promoted experiment history'],
  },
  {
    heading: 'Provenance & flags',
    blurb: 'Exactly which code is running and which safety switches are set.',
    titles: ['Model version', 'Feature schema version', 'Current feature flags'],
  },
];

// Overall posture = worst label present, so the page leads with one honest
// headline instead of making the owner scan fourteen chips.
const LABEL_SEVERITY: Record<string, number> = {
  degraded: 3, insufficient_data: 2, unavailable: 2,
  preliminary: 1, not_yet_evaluated: 1, proven: 0,
};

export function AdminTrustCenter() {
  const [payload, setPayload] = useState<Payload | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'denied'>('loading');

  useEffect(() => {
    apiGet<Payload>('/admin/trust-center')
      .then((p) => { setPayload(p); setState('ready'); })
      .catch(() => setState('denied'));
  }, []);

  const sections = payload?.sections ?? [];
  const worst = sections.reduce((acc, s) => Math.max(acc, LABEL_SEVERITY[s.label] ?? 1), 0);
  const degradedTitles = sections.filter((s) => s.label === 'degraded').map((s) => s.title);

  return (
    <ArthosPage maxWidth="max-w-copy">
      <p className="text-meta ink-fainter mb-1 mt-8">ADMIN — OWNER-FACING</p>
      <h1 className="font-serif text-headline ink-primary mb-2">Trust Center</h1>
      <p className="ink-muted text-[13.5px] mb-8 max-w-narrative">
        What ArthOS knows about itself, with honest labels. Sections without
        evidence say so — nothing here is a marketing number.
      </p>

      {state === 'loading' && (
        <p className="ink-fainter text-[13px]" role="status">Loading live status…</p>
      )}

      {state === 'denied' && (
        <StatusPanel variant="info" title="This page is owner-only." role="status"
          action={<Link to="/discover" className="text-[12.5px] font-semibold" style={{ color: 'var(--brand)' }}>Back to Discover →</Link>}>
          Nothing is wrong with your account — the Trust Center shows internal
          system evidence and is limited to the platform owner.
        </StatusPanel>
      )}

      {state === 'ready' && (
        <>
          {/* Overall trust status — one headline before the detail. */}
          <div className="mb-8">
            <StatusPanel
              variant={worst >= 3 ? 'warn' : worst >= 2 ? 'warn' : 'success'}
              title={
                worst >= 3
                  ? `Attention needed: ${degradedTitles.join(', ') || 'one or more areas degraded'}`
                  : worst >= 2
                    ? 'Running, with gaps in the evidence'
                    : 'All monitored areas look healthy'
              }
              role="status"
            >
              {sections.length} areas monitored · beta software · every label
              below is generated from live reads, never hand-entered.
            </StatusPanel>
          </div>

          {GROUPS.map((g) => {
            const inGroup = sections.filter((s) => g.titles.includes(s.title));
            if (inGroup.length === 0) return null;
            return (
              <div key={g.heading} className="mb-10">
                <h2 className="ink-primary text-[16px] font-semibold mb-0.5 font-serif">{g.heading}</h2>
                <p className="ink-fainter text-[12px] mb-4">{g.blurb}</p>
                {inGroup.map((s) => <SectionCard key={s.title} s={s} />)}
              </div>
            );
          })}
          {/* Anything the grouping doesn't know about still renders. */}
          {sections.filter((s) => !GROUPS.some((g) => g.titles.includes(s.title))).map((s) => (
            <SectionCard key={s.title} s={s} />
          ))}
          <p className="ink-fainter text-[10.5px] tabular-nums">
            Generated {fmtValue('generated_at', payload?.generated_at)}
          </p>
        </>
      )}
    </ArthosPage>
  );
}
