// V2 Pick Detail — P0 LIVE rewire. Per-symbol reasoning sourced from the
// LIVE recommendation engine (useTodaysRecommendations → GET
// /recommendations). NO PICK_NARRATIVE / getPosition / getPickEvidence /
// arthosData static literals. Fields the backend lacks are omitted, never
// fabricated. Honest not-found when the symbol has no live recommendation.

import { useEffect, useRef } from 'react';
import { useParams, Link, useNavigate, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { useUserPrefs } from '../state/UserPrefsContext';
import { CONFIDENCE_DOCTRINE } from '../lib/copy';
import { useAddIdeaToPaper } from '@/lib/operator/modelPortfolios';
import {
  useTodaysRecommendations,
  effectiveAction,
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

// Translate a raw factor direction into a plain-English cue (no scores).
function dirMark(direction?: string): { glyph: string; color: string } {
  const d = (direction ?? '').toLowerCase();
  if (/up|bull|pos|support|long/.test(d)) return { glyph: '▲', color: 'var(--brand)' };
  if (/down|bear|neg|risk|short/.test(d)) return { glyph: '▼', color: 'oklch(0.70 0.14 75)' };
  return { glyph: '•', color: 'var(--muted-foreground)' };
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
  const [sp] = useSearchParams();
  const addIdea = useAddIdeaToPaper();
  const autoFired = useRef(false);

  const recs: RecApi[] = data?.recommendations ?? [];
  const rec = symbol
    ? recs.find((r) => (r.symbol ?? '').toUpperCase() === symbol.toUpperCase())
    : undefined;

  // Add this idea to the canonical paper book ($1,000), then go to My Portfolio.
  const addToPaper = () => {
    if (!rec?.symbol) return;
    addIdea.mutate(
      { symbol: rec.symbol },
      { onSuccess: () => navigate('/v2/portfolio') },
    );
  };

  // ?add=1 from the Discover card "Add to paper" CTA auto-fires once.
  useEffect(() => {
    if (sp.get('add') === '1' && rec?.symbol && !autoFired.current && !addIdea.isPending) {
      autoFired.current = true;
      addToPaper();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sp, rec?.symbol]);

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
  const fresh = isFresh(rec);
  const watching = inWatchlist(rec.symbol ?? '');
  const evidence = (rec.evidence ?? []) as EvidenceItem[];

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
            {rec.confidence_label ?? 'Medium'} confidence
            {' · '}
            <span style={{ color: fresh ? 'var(--brand)' : 'oklch(0.70 0.14 75)' }}>
              {fresh ? 'updated today' : 'needs a refresh'}
            </span>
          </div>
          {/* P1.3 — confidence doctrine (shared SSOT) */}
          <p className="ink-fainter text-[12px] leading-relaxed mt-2 max-w-narrative">
            {CONFIDENCE_DOCTRINE}
          </p>
          {/* MVP — add this idea to the paper book ($1,000). */}
          <button type="button" onClick={addToPaper} disabled={addIdea.isPending}
            className="mt-4 px-4 py-2 rounded-full"
            style={{
              fontSize: 13, fontWeight: 600, color: 'var(--background)',
              backgroundColor: 'var(--brand)', border: 'none',
              opacity: addIdea.isPending ? 0.6 : 1,
              cursor: addIdea.isPending ? 'default' : 'pointer',
            }}>
            {addIdea.isPending ? 'Adding…' : 'Add to paper ($1,000)'}
          </button>
          {addIdea.isError && (
            <p className="mt-2 text-[12px]" style={{ color: 'var(--destructive)' }}>
              Couldn't add to your paper book. Try again.
            </p>
          )}
        </div>
      </FadeIn>

      <FadeIn delay={0.04}>
        <div className="mb-12 max-w-narrative">
          <div className="flex items-baseline gap-3 mb-1.5">
            <MetaLabel>As of</MetaLabel>
            <span className="ink-primary text-[13px] tabular-nums">{absTime(rec.generated_at)}</span>
          </div>
          <p className="ink-fainter text-[12px] italic leading-relaxed">
            Generated live from current market data.
          </p>
        </div>
      </FadeIn>

      {rec.thesis && (
        <FadeIn delay={0.06}>
          <section className="mb-16 max-w-narrative">
            <MetaLabel>Why this idea exists</MetaLabel>
            <p className="font-serif text-subhead ink-primary leading-snug mt-3">
              {rec.thesis}
            </p>
          </section>
        </FadeIn>
      )}

      {evidence.filter((s) => s.narrative).length > 0 && (
        <FadeIn delay={0.14}>
          <section className="mb-16 max-w-narrative">
            <MetaLabel>What the engine sees</MetaLabel>
            <ul className="mt-6 space-y-4">
              {evidence.filter((s) => s.narrative).map((s, i) => {
                const m = dirMark(s.direction);
                return (
                  <li key={i} className="border-t border-hairline pt-4 flex items-baseline gap-3">
                    <span aria-hidden style={{ color: m.color, fontSize: 12 }}>{m.glyph}</span>
                    <span className="ink-primary text-[15px] leading-snug">{s.narrative}</span>
                  </li>
                );
              })}
            </ul>
          </section>
        </FadeIn>
      )}

      {/* Sprint C — plain-English risk framing. Honest + general: ArthOS does
          not fabricate a per-name risk number, so we frame what would weaken
          the idea in language a beginner can act on. */}
      <FadeIn delay={0.18}>
        <section className="mb-16 max-w-narrative">
          <MetaLabel>Key risks &amp; what would invalidate this</MetaLabel>
          <p className="ink-muted text-[14px] leading-relaxed mt-3">
            This is the engine's current read, not a promise. It weakens if the
            supporting signals above reverse, if the company's story changes, or
            if newer data moves the picture. Markets can fall as well as rise —
            only practice with money you're comfortable simulating.
          </p>
        </section>
      </FadeIn>

      <FadeIn delay={0.22}>
        <section className="border-t border-hairline pt-10 max-w-narrative">
          <p className="ink-muted text-[13px] leading-relaxed">
            ArthOS's read for {rec.symbol}, as of {absTime(rec.generated_at)}
            {rec.enough_data ? '.' : ' — based on limited data, so treat it with extra caution.'}
          </p>
          <div className="mt-4 flex items-center gap-5">
            <Link to="/v2/discover" className="text-meta ink-primary inline-block" style={{ fontWeight: 600 }}>
              Back to ideas →
            </Link>
            {/* Embed a path to the glossary so unfamiliar terms are one tap away. */}
            <Link to="/v2/learn/glossary" className="text-meta ink-muted inline-block">
              New to these terms? Glossary →
            </Link>
          </div>
        </section>
      </FadeIn>
    </ArthosPage>
  );
}
