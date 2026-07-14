// Wave 1D — Decision Replay Timeline page (/today/pick/:symbol/history).
// Renders the stored, redacted timeline; hindsight-proof by construction
// (server renders stored values only). Semantic <ol> timeline, keyboard
// disclosures, status never color-only, no animation.

import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { StatusPanel } from '../components/ui/StatusPanel';
import { EvidenceBadge } from '../components/ui/EvidenceBadge';

type ReplayEvent = {
  key: string; type: string; occurred_at: string; title: string;
  summary: string; label: string; source: string;
  detail_status: string; details: Record<string, unknown>;
};
type Replay = {
  symbol: string; recommendation_as_of: string; lifecycle_status: string;
  completeness: string; completeness_note: string;
  events: ReplayEvent[];
  unavailable_sections: { section: string; reason: string }[];
  user_scoped: boolean; generated_at: string;
};

const timelineCache = new Map<string, { at: number; value: Replay | null }>();

export function useIdeaTimeline(symbol: string | undefined) {
  const [state, setState] = useState<Replay | null | undefined>(() => {
    const hit = symbol ? timelineCache.get(symbol.toUpperCase()) : undefined;
    return hit && Date.now() - hit.at < 60_000 ? hit.value : undefined;
  });
  useEffect(() => {
    if (!symbol) { setState(null); return; }
    const key = symbol.toUpperCase();
    const hit = timelineCache.get(key);
    if (hit && Date.now() - hit.at < 60_000) { setState(hit.value); return; }
    let alive = true;
    fetch(`/api/recommendations/${encodeURIComponent(key)}/timeline`,
      { credentials: 'include', headers: { Accept: 'application/json' } })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        timelineCache.set(key, { at: Date.now(), value: j });
        if (alive) setState(j);
      })
      .catch(() => { if (alive) setState(null); });
    return () => { alive = false; };
  }, [symbol]);
  return state;
}

const LIFECYCLE_COPY: Record<string, string> = {
  open: 'This idea is still open.',
  resolved_target: 'This idea resolved by reaching its target zone.',
  resolved_exit: 'This idea resolved by reaching its exit condition.',
  resolved_time: 'This idea resolved by reaching its time limit.',
};

function EventCard({ e }: { e: ReplayEvent }) {
  const detailEntries = Object.entries(e.details).filter(
    ([, v]) => v !== null && v !== undefined
    && !(Array.isArray(v) && v.length === 0),
  );
  return (
    <li className="relative pl-8 pb-8">
      <span aria-hidden className="absolute left-0 top-1.5 w-3 h-3 rounded-full"
        style={{
          backgroundColor: 'color-mix(in oklch, var(--brand) 25%, transparent)',
          border: '2px solid var(--brand)',
        }} />
      <span aria-hidden className="absolute left-[5px] top-6 bottom-0 w-px"
        style={{ backgroundColor: 'var(--border)' }} />
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h3 className="ink-primary text-[14.5px] font-semibold">{e.title}</h3>
        <EvidenceBadge state={e.label} size="sm" />
      </div>
      <p className="ink-fainter text-[11.5px] tabular-nums mt-0.5">
        <time dateTime={e.occurred_at}>
          {new Date(e.occurred_at).toLocaleString(undefined, {
            year: 'numeric', month: 'long', day: 'numeric',
            hour: '2-digit', minute: '2-digit',
          })}
        </time>
        {e.detail_status !== 'complete' && ` · detail ${e.detail_status.replace('_', ' ')}`}
      </p>
      <p className="ink-muted text-[13.5px] leading-relaxed mt-1.5 max-w-narrative">
        {e.summary}
      </p>
      {detailEntries.length > 0 && (
        <details className="mt-1.5">
          <summary className="ink-fainter text-[11.5px] cursor-pointer select-none">
            Details
          </summary>
          <dl className="mt-1.5 space-y-1">
            {detailEntries.map(([k, v]) => (
              <div key={k} className="flex items-baseline gap-3">
                <dt className="ink-fainter text-[11.5px] shrink-0">
                  {k.replace(/_/g, ' ')}
                </dt>
                <dd className="ink-muted text-[12px] tabular-nums min-w-0">
                  {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                </dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </li>
  );
}

export function IdeaHistory() {
  const { symbol } = useParams<{ symbol: string }>();
  const timeline = useIdeaTimeline(symbol);

  return (
    <ArthosPage maxWidth="max-w-copy">
      <MetaLabel>Decision replay</MetaLabel>
      <h1 className="font-serif text-headline ink-primary mt-3 mb-3">
        The full history of this ArthOS idea
      </h1>
      <p className="ink-muted text-[13.5px] leading-relaxed max-w-narrative mb-2">
        Everything below is rebuilt from records stored at the time — nothing
        is rewritten with hindsight. All activity is paper only: practice
        money, never real trades.
      </p>

      {timeline === undefined && (
        <p className="ink-fainter text-[13px]" role="status">Loading history…</p>
      )}

      {timeline === null && (
        <StatusPanel variant="info" title="History isn't available for this idea."
          action={<Link to={`/today/pick/${symbol ?? ''}`} className="text-[12.5px] font-semibold" style={{ color: 'var(--brand)' }}>Back to the idea →</Link>}>
          The replay feature may be off, or this symbol has no recorded
          recommendation. Nothing is lost.
        </StatusPanel>
      )}

      {timeline && (
        <>
          <p className="ink-primary text-[14px] mb-1">
            {LIFECYCLE_COPY[timeline.lifecycle_status] ?? 'Lifecycle recorded.'}
          </p>
          <div className="mb-8">
            <StatusPanel
              variant={timeline.completeness === 'complete' ? 'success' : 'info'}
              title={timeline.completeness === 'complete'
                ? 'Every recorded artifact is shown.'
                : 'Some history was not recorded — shown honestly below.'}
              role="status"
            >
              {timeline.completeness_note}
            </StatusPanel>
          </div>

          <ol className="list-none m-0 p-0">
            {timeline.events.map((e) => <EventCard key={e.key} e={e} />)}
          </ol>

          {timeline.unavailable_sections.length > 0 && (
            <section className="mt-4 mb-10">
              <MetaLabel>Not recorded</MetaLabel>
              <ul className="mt-2 space-y-1">
                {timeline.unavailable_sections.map((u) => (
                  <li key={u.section} className="ink-muted text-[12.5px] flex items-start gap-2">
                    <span aria-hidden style={{ color: 'var(--muted-foreground)' }}>∅</span>
                    {u.reason}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <Link to={`/today/pick/${timeline.symbol}`}
            className="inline-block text-[13px] font-semibold mt-2"
            style={{ color: 'var(--brand)' }}>
            ← Back to the current idea
          </Link>
        </>
      )}
    </ArthosPage>
  );
}
