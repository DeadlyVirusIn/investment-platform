// V2 Pick Detail — P0 LIVE rewire. Per-symbol reasoning sourced from the
// LIVE recommendation engine (useTodaysRecommendations → GET
// /recommendations). NO PICK_NARRATIVE / getPosition / getPickEvidence /
// arthosData static literals. Fields the backend lacks are omitted, never
// fabricated. Honest not-found when the symbol has no live recommendation.

import { useParams, Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { useUserPrefs } from '../state/UserPrefsContext';
import {
  useTodaysRecommendations,
  effectiveAction,
  confidenceNum,
  type RecApi,
} from '@/lib/operator/hooks';

interface EvidenceItem {
  factor_key?: string;
  family?: string;
  direction?: string;
  score?: string | null;
  narrative?: string;
}

function FadeIn({ delay = 0, children }: { delay?: number; children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.32, 0.72, 0, 1] }}
    >
      {children}
    </motion.div>
  );
}

function absTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function isFresh(rec: RecApi): boolean {
  if (rec.stale_data) return false;
  if (!rec.generated_at) return true;
  const h = (Date.now() - new Date(rec.generated_at).getTime()) / 3600_000;
  return !(Number.isFinite(h) && h > 30);
}

export function PickPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const navigate = useNavigate();
  const { inWatchlist, toggleWatchlist } = useUserPrefs();
  const { data, isLoading } = useTodaysRecommendations();

  const recs: RecApi[] = data?.recommendations ?? [];
  const rec = symbol
    ? recs.find((r) => (r.symbol ?? '').toUpperCase() === symbol.toUpperCase())
    : undefined;

  if (isLoading) {
    return (
      <ArthosPage maxWidth="max-w-narrative">
        <div className="py-20"><p className="ink-muted">Loading the live recommendation…</p></div>
      </ArthosPage>
    );
  }

  if (!rec) {
    return (
      <ArthosPage maxWidth="max-w-narrative">
        <div className="py-20">
          <p className="ink-primary text-[16px] mb-2">
            No live recommendation for {symbol ?? 'that symbol'} today.
          </p>
          <p className="ink-muted text-[13.5px] max-w-narrative">
            The engine did not surface this name in today's evaluated set. It may not have cleared data-sufficiency, or it isn't in the current universe.
          </p>
          <Link to="/v2/opportunities" className="text-meta ink-muted mt-4 inline-block">
            See the live desk →
          </Link>
        </div>
      </ArthosPage>
    );
  }

  const action = effectiveAction(rec) ?? 'Hold';
  const conf = confidenceNum(rec);
  const fresh = isFresh(rec);
  const watching = inWatchlist(rec.symbol ?? '');
  const evidence = (rec.evidence ?? []) as EvidenceItem[];
  const families = rec.family_scores ?? {};

  return (
    <ArthosPage maxWidth="max-w-copy">
      <button
        onClick={() => navigate(-1)}
        className="text-meta ink-fainter hover:ink-muted mb-12 inline-flex items-center gap-1.5 transition-colors"
      >
        <span aria-hidden>←</span> Back
      </button>

      <FadeIn>
        <div className="mb-10">
          <div className="flex items-center justify-between gap-4 mb-2">
            <div className="font-mono text-meta ink-fainter">{rec.symbol}</div>
            <button
              onClick={() => rec.symbol && toggleWatchlist(rec.symbol)}
              className={`text-meta inline-flex items-center gap-1.5 transition-colors ${
                watching ? 'ink-primary' : 'ink-fainter hover:ink-muted'
              }`}
            >
              <span aria-hidden className="text-[15px] leading-none">{watching ? '★' : '☆'}</span>
              {watching ? 'Watching' : 'Watch'}
            </button>
          </div>
          <h1 className="font-serif text-headline ink-primary mb-3">
            {rec.symbol} — {action}
          </h1>
          <div className="text-meta ink-muted tabular-nums">
            {rec.confidence_label ?? 'Medium'} confidence · {conf.toFixed(0)}
            {' · '}
            <span style={{ color: fresh ? 'var(--brand)' : 'oklch(0.70 0.14 75)' }}>
              {fresh ? 'fresh' : 'stale'}
            </span>
            {rec.composite_score != null && <> · composite {Number(rec.composite_score).toFixed(3)}</>}
          </div>
        </div>
      </FadeIn>

      <FadeIn delay={0.04}>
        <div className="mb-12 max-w-narrative">
          <div className="flex items-baseline gap-3 mb-1.5">
            <MetaLabel>As of</MetaLabel>
            <span className="ink-primary text-[13px] tabular-nums">{absTime(rec.generated_at)}</span>
          </div>
          <p className="ink-fainter text-[12px] italic leading-relaxed">
            Live engine{rec.engine_version ? ` · ${rec.engine_version}` : ''} · source: live
          </p>
        </div>
      </FadeIn>

      {rec.thesis && (
        <FadeIn delay={0.06}>
          <p className="font-serif text-subhead ink-primary leading-snug mb-16 max-w-narrative">
            {rec.thesis}
          </p>
        </FadeIn>
      )}

      {evidence.length > 0 && (
        <FadeIn delay={0.14}>
          <section className="mb-20">
            <MetaLabel>What the engine is seeing</MetaLabel>
            <ul className="mt-6 space-y-6 max-w-copy">
              {evidence.map((s, i) => (
                <li key={i} className="grid sm:grid-cols-[1fr_auto] gap-x-8 gap-y-1.5 items-baseline border-t border-hairline pt-6">
                  <div className="min-w-0">
                    <div className="ink-primary text-[15px] leading-snug mb-1">
                      {s.narrative ?? s.factor_key ?? 'factor'}
                    </div>
                    <div className="ink-fainter text-[12px] leading-relaxed">
                      {s.family ?? ''}{s.direction ? ` · ${s.direction}` : ''}
                    </div>
                  </div>
                  <div className="ink-muted text-[13px] tabular-nums leading-snug sm:text-right">
                    {s.score != null ? Number(s.score).toFixed(3) : '—'}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </FadeIn>
      )}

      {Object.keys(families).length > 0 && (
        <FadeIn delay={0.18}>
          <section className="mb-20">
            <MetaLabel>Family scores</MetaLabel>
            <ul className="mt-6 grid sm:grid-cols-2 gap-x-10 gap-y-3 max-w-copy">
              {Object.entries(families).map(([k, v]) => (
                <li key={k} className="flex items-baseline justify-between gap-4 border-t border-hairline pt-3">
                  <span className="ink-primary text-[13.5px]">{k.replace(/_/g, ' ')}</span>
                  <span className="ink-muted text-[13px] tabular-nums">
                    {v != null ? Number(v).toFixed(3) : '—'}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </FadeIn>
      )}

      <FadeIn delay={0.22}>
        <section className="border-t border-hairline pt-10 max-w-narrative">
          <p className="ink-muted text-[13px] leading-relaxed">
            This is the live engine's read for {rec.symbol} as of {absTime(rec.generated_at)}.
            Data sufficiency: {rec.enough_data ? 'sufficient' : 'limited'}.
          </p>
          <Link to="/v2/opportunities" className="text-meta ink-primary mt-4 inline-block" style={{ fontWeight: 600 }}>
            Back to the live desk →
          </Link>
        </section>
      </FadeIn>
    </ArthosPage>
  );
}
