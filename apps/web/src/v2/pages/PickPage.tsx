// V2 Pick Detail — P0 LIVE rewire. Per-symbol reasoning sourced from the
// LIVE recommendation engine (useTodaysRecommendations → GET
// /recommendations). NO PICK_NARRATIVE / getPosition / getPickEvidence /
// arthosData static literals. Fields the backend lacks are omitted, never
// fabricated. Honest not-found when the symbol has no live recommendation.

import { useEffect, useRef, useState } from 'react';
import { useParams, Link, useNavigate, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { useUserPrefs } from '../state/UserPrefsContext';
import { useAddIdeaToPaper } from '@/lib/operator/modelPortfolios';
import { plainThesis, ideaSignals } from '../lib/plainText';
import { sectorLabel } from '../lib/companyMeta';
import { CompanyTitle } from '../components/CompanyTitle';
import { PlanRows } from '../components/PlanRows';
import { useSymbolNews } from '@/lib/market/hooks';
import {
  useTodaysRecommendations,
  effectiveAction,
  type RecApi,
} from '@/lib/operator/hooks';

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

// ArthOS recommendations are swing ideas (the engine's design horizon), so the
// expected holding period is a real property of the strategy — not per-name.
const HOLDING_PERIOD =
  'Medium-term — these are swing ideas, usually held a few weeks to a few months.';

// Plain "what to do next" framing for the engine's action.
function actionPlain(action: string): { verb: string; explain: string; tone: 'pos' | 'neg' | 'muted' } {
  switch (action) {
    case 'Buy':
      return { verb: 'Consider buying', tone: 'pos',
        explain: "ArthOS sees more working for this than against it right now." };
    case 'Trim':
      return { verb: 'Consider trimming', tone: 'neg',
        explain: "ArthOS would lighten up here — the risks outweigh the upside." };
    case 'Sell':
    case 'Exit':
      return { verb: 'Consider stepping aside', tone: 'neg',
        explain: "ArthOS would not hold this right now." };
    default:
      return { verb: 'Hold — no action today', tone: 'muted',
        explain: "Nothing compelling to do right now; owners can sit tight." };
  }
}

function isFresh(rec: RecApi): boolean {
  if (rec.stale_data) return false;
  if (!rec.generated_at) return true;
  const h = (Date.now() - new Date(rec.generated_at).getTime()) / 3600_000;
  return !(Number.isFinite(h) && h > 30);
}

// One-time explainer: clarifies "paper" the first time a user reaches an
// idea detail. Dismiss persists in localStorage so it shows only once.
function PaperExplainer() {
  const KEY = 'arthos_seen_paper_explainer';
  const [show, setShow] = useState(false);
  useEffect(() => {
    try { if (!localStorage.getItem(KEY)) setShow(true); } catch { /* ignore */ }
  }, []);
  if (!show) return null;
  return (
    <div className="mt-3 rounded-xl px-3 py-2 flex items-start justify-between gap-3"
      style={{ backgroundColor: 'color-mix(in oklch, var(--brand) 8%, transparent)', border: '1px solid var(--border)' }}>
      <p className="ink-muted text-[12.5px] leading-relaxed">
        Paper means practice money — no real money is used.
      </p>
      <button type="button"
        onClick={() => { try { localStorage.setItem(KEY, '1'); } catch { /* ignore */ } setShow(false); }}
        className="text-[12px] ink-fainter hover:ink-muted shrink-0">Got it</button>
    </div>
  );
}

export function PickPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const navigate = useNavigate();
  const { inWatchlist, toggleWatchlist } = useUserPrefs();
  const { data, isLoading } = useTodaysRecommendations();
  const { data: news } = useSymbolNews(symbol);
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

  // Reset the one-shot guard when navigating between symbols (the router
  // reuses this component instance on param change).
  useEffect(() => { autoFired.current = false; }, [symbol]);

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
  const sig = ideaSignals(rec.family_scores);
  const holding = HOLDING_PERIOD;
  const sec = sectorLabel(rec.sector);

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
            <CompanyTitle symbol={rec.symbol} name={rec.name}
              tickerClassName="font-mono ink-muted" tickerStyle={{ fontSize: '0.6em' }} />
            {' — '}{action}
          </h1>
          <div className="text-meta ink-muted tabular-nums">
            {sec && <>{sec}{' · '}</>}
            {rec.confidence_label ?? 'Medium'} confidence
            {' · '}
            <span style={{ color: fresh ? 'var(--brand)' : 'oklch(0.70 0.14 75)' }}>
              {fresh ? 'updated today' : 'needs a refresh'}
            </span>
          </div>
          {/* Phase 4 — beginner-safe explanation of what "confidence" means. */}
          <p className="ink-fainter text-[12px] leading-relaxed mt-2 max-w-narrative">
            Confidence means how strongly Arth’s model supports this idea based on
            available data. It is not a guarantee.
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
          <PaperExplainer />
        </div>
      </FadeIn>

      {/* Sprint J — "What do I do next?" — the decision, up front. ArthOS gives
          a buy/hold/trim call, not fabricated price targets. */}
      <FadeIn delay={0.03}>
        <section className="mb-12 max-w-narrative">
          <MetaLabel>What to do next</MetaLabel>
          {(() => {
            const act = actionPlain(action);
            const color = act.tone === 'pos' ? 'var(--brand)'
              : act.tone === 'neg' ? 'oklch(0.70 0.14 75)' : 'var(--foreground)';
            return (
              <>
                <p className="font-serif leading-snug mt-3" style={{ fontSize: 24, color }}>{act.verb}</p>
                <p className="ink-muted text-[14px] leading-relaxed mt-2">{act.explain}</p>
              </>
            );
          })()}
          {/* Plan — Entry / Target / Exit if wrong / Timeframe (Sprint K).
              Real paper-planning zones when price + ATR are present, honest
              placeholders otherwise. Never fabricated. */}
          <div className="mt-5"><PlanRows rec={rec} /></div>
        </section>
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

      {/* Sprint H — "Why this idea exists" in plain investor language, derived
          from the engine's real signals (no scores/jargon). Falls back to the
          plain evidence narratives if family signals aren't present. */}
      <FadeIn delay={0.06}>
        <section className="mb-12 max-w-narrative">
          <MetaLabel>Why this idea exists</MetaLabel>
          <p className="font-serif text-subhead ink-primary leading-snug mt-3 mb-5">
            {plainThesis(rec.thesis)
              ?? `ArthOS flagged ${rec.symbol} as a ${action.toLowerCase()} based on what's working in its favor.`}
          </p>
          {sig.why.length > 0 ? (
            <ul className="space-y-3">
              {sig.why.map((w) => (
                <li key={w} className="flex items-baseline gap-3 border-t border-hairline pt-3">
                  <span aria-hidden style={{ color: 'var(--brand)', fontSize: 12 }}>▲</span>
                  <span className="ink-primary text-[15px] leading-snug">{w}</span>
                </li>
              ))}
            </ul>
          ) : (
            // Phase 4 — beginner-safe fallback. Never expose raw engine
            // narratives (SMA / RSI / ATR) when no plain signals are available.
            <p className="ink-muted text-[14px] leading-relaxed">
              Arth’s model rates this a {action.toLowerCase()} from current price and
              market trend. The detailed signals aren’t available in plain language
              for this name yet.
            </p>
          )}
        </section>
      </FadeIn>

      <FadeIn delay={0.12}>
        <section className="mb-12 max-w-narrative">
          <MetaLabel>Potential risks</MetaLabel>
          {sig.risks.length > 0 && (
            <ul className="mt-4 mb-3 space-y-3">
              {sig.risks.map((r) => (
                <li key={r} className="flex items-baseline gap-3 border-t border-hairline pt-3">
                  <span aria-hidden style={{ color: 'oklch(0.70 0.14 75)', fontSize: 12 }}>▼</span>
                  <span className="ink-primary text-[15px] leading-snug">{r}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="ink-muted text-[14px] leading-relaxed mt-2">
            This is ArthOS's current read, not a promise. It weakens if the
            signals above reverse or the company's story changes. Markets fall as
            well as rise — practice first with money you're fine simulating.
          </p>
        </section>
      </FadeIn>

      <FadeIn delay={0.16}>
        <section className="mb-16 max-w-narrative">
          <MetaLabel>Expected holding period</MetaLabel>
          <p className="ink-primary text-[15px] leading-snug mt-3">{holding}</p>
        </section>
      </FadeIn>

      {/* Sprint I — Recent news & catalysts (real, from /news/symbol). */}
      {news && news.items.length > 0 && (
        <FadeIn delay={0.18}>
          <section className="mb-12 max-w-narrative">
            <MetaLabel>Recent news &amp; catalysts</MetaLabel>
            <ul className="mt-4 space-y-4">
              {news.items.slice(0, 5).map((n) => (
                <li key={n.id} className="border-t border-hairline pt-4">
                  {n.category && (
                    <span className="inline-block mb-1 px-2 py-0.5 rounded-full"
                      style={{ fontSize: 10.5, textTransform: 'capitalize',
                        color: 'var(--muted-foreground)', border: '1px solid var(--border)' }}>
                      {n.category}
                    </span>
                  )}
                  {n.url ? (
                    <a href={n.url} target="_blank" rel="noopener noreferrer"
                      className="block ink-primary text-[14.5px] leading-snug hover:opacity-70">
                      {n.title}
                    </a>
                  ) : (
                    <span className="block ink-primary text-[14.5px] leading-snug">{n.title}</span>
                  )}
                  <span className="block ink-fainter text-[11.5px] mt-1">
                    {n.source} · {absTime(n.published_at)}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </FadeIn>
      )}

      {/* Sprint I — Fundamentals: honest placeholder. ArthOS does not yet
          ingest revenue/earnings/valuation, and will not show numbers it can't
          verify. Surfaced when the data layer lands. */}
      <FadeIn delay={0.2}>
        <section className="mb-12 max-w-narrative">
          <MetaLabel>Fundamentals</MetaLabel>
          <p className="ink-muted text-[14px] leading-relaxed mt-3">
            Company fundamentals — revenue growth, earnings, profitability and
            valuation — are coming soon. ArthOS won't show numbers it can't
            verify, so this stays empty until the data is wired in.
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
