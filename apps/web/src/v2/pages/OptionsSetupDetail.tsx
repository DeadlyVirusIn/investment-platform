// Options Setup Detail — the options counterpart to PickPage. Per-setup
// reasoning sourced from the LIVE options engine (useOptionsLanes →
// GET /options/opportunities), found by observation_id. NO by-id backend
// endpoint is needed (mirrors PickPage's find-by-symbol pattern).
//
// Shows ONLY truthful fields the opportunity card carries: strategy name,
// confidence, DTE, bias descriptor, premium/liquidity tier, "Why Arth likes
// this", catalyst, engine/research classification, paper-only disclaimer.
// NO Max Profit / Max Risk / POP (deferred to Phase C — only the short leg
// is stored). Honest not-found when the id isn't in today's set. Read-only;
// no trade controls. UI-only.

import { useParams, Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { useOptionsLanes } from '../lib/optionsLanes';
import { presentOption } from '../lib/optionsPresent';
import { OPTIONS_TAB_HREF } from '../components/OptionsSetupCard';

const AMBER = 'oklch(0.70 0.14 75)';

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

function toneColor(tone: ReturnType<typeof presentOption>['tone']): string {
  switch (tone) {
    case 'bull': return 'var(--brand)';
    case 'bear': return 'var(--destructive)';
    case 'vol': return AMBER;
    default: return 'var(--muted-foreground)';
  }
}

export function OptionsSetupDetail() {
  const { observationId } = useParams<{ observationId: string }>();
  const navigate = useNavigate();
  const lanes = useOptionsLanes();

  const id = Number(observationId);
  const all = [...lanes.engine, ...lanes.research];
  const item = Number.isFinite(id)
    ? all.find((o) => o.observation_id === id)
    : undefined;

  if (lanes.isLoading) {
    return (
      <ArthosPage maxWidth="max-w-narrative">
        <div className="py-20"><p className="ink-muted">Loading the options setup…</p></div>
      </ArthosPage>
    );
  }

  if (!item) {
    return (
      <ArthosPage maxWidth="max-w-narrative">
        <div className="py-20">
          <p className="ink-primary text-[16px] mb-2">
            No options setup for this id today.
          </p>
          <p className="ink-muted text-[13.5px] max-w-narrative">
            The engine did not surface this setup in today's set. It may have
            rolled off as the chain refreshed, or it isn't in the current run.
          </p>
          <Link to={OPTIONS_TAB_HREF} className="text-meta ink-muted mt-4 inline-block">
            See options in Opportunities →
          </Link>
        </div>
      </ArthosPage>
    );
  }

  const opt = presentOption(item);
  const isEngine = opt.family === 'engine_executable';
  const tone = toneColor(opt.tone);

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
            <div className="font-mono text-meta ink-fainter">{opt.underlying}</div>
            <span className="text-meta" style={{ color: isEngine ? 'var(--brand)' : 'var(--muted-foreground)' }}>
              {isEngine ? 'Engine setup' : 'Research idea'}
            </span>
          </div>
          <h1 className="font-serif text-headline ink-primary mb-3">
            {opt.underlying} — {opt.strategyName}
          </h1>
          <div className="text-meta ink-muted tabular-nums flex items-center gap-2 flex-wrap">
            <span
              aria-hidden
              className="inline-block rounded-full"
              style={{ width: 7, height: 7, backgroundColor: tone }}
            />
            <span>{opt.descriptor}</span>
            <span>·</span>
            <span>{opt.confidenceLabel} confidence · {opt.confidence}</span>
            <span>·</span>
            <span>DTE {opt.dte}</span>
            {opt.qualified && <><span>·</span><span style={{ color: 'var(--brand)' }}>qualified</span></>}
          </div>
          {(opt.runDate || opt.quoteAge || opt.freshness.label !== 'Unknown') && (
            <div className="text-meta ink-fainter mt-2 flex items-center gap-2 flex-wrap tabular-nums">
              {opt.runDate && <span>As of {opt.runDate}</span>}
              {opt.quoteAge && <><span aria-hidden>·</span><span>quotes {opt.quoteAge}</span></>}
              {opt.freshness.label !== 'Unknown' && (
                <>
                  <span aria-hidden>·</span>
                  <span style={{ color: opt.freshness.stale ? AMBER : 'var(--brand)' }}>
                    {opt.freshness.label.toLowerCase()}
                  </span>
                </>
              )}
            </div>
          )}
        </div>
      </FadeIn>

      {(opt.premiumLabel || opt.liquidityLabel || opt.catalyst) && (
        <FadeIn delay={0.04}>
          <div className="mb-12 flex flex-wrap items-center gap-2">
            {opt.premiumLabel && <Tag>{opt.premiumLabel}</Tag>}
            {opt.liquidityLabel && <Tag>{opt.liquidityLabel}</Tag>}
            {opt.catalyst && <Tag tone="warn">⚡ {opt.catalyst}</Tag>}
          </div>
        </FadeIn>
      )}

      {opt.thesis && (
        <FadeIn delay={0.06}>
          <p className="font-serif text-subhead ink-primary leading-snug mb-16 max-w-narrative">
            {opt.thesis}
          </p>
        </FadeIn>
      )}

      {opt.whyPoints.length > 0 && (
        <FadeIn delay={0.14}>
          <section className="mb-20">
            <MetaLabel>Why Arth likes this</MetaLabel>
            <ul className="mt-6 space-y-4 max-w-copy">
              {opt.whyPoints.map((p, i) => (
                <li key={i} className="flex gap-3 border-t border-hairline pt-4">
                  <span aria-hidden style={{ color: 'var(--brand)' }}>•</span>
                  <span className="ink-primary text-[15px] leading-snug">{p}</span>
                </li>
              ))}
            </ul>
          </section>
        </FadeIn>
      )}

      {opt.engine.length > 0 && (
        <FadeIn delay={0.16}>
          <section className="mb-20">
            <MetaLabel>What the engine is seeing</MetaLabel>
            <ul className="mt-6 space-y-3 max-w-copy">
              {opt.engine.map((r) => (
                <li key={r.key} className="border-t border-hairline pt-3">
                  <div className="flex items-baseline justify-between gap-4">
                    <span className="ink-primary text-[14px]">{r.label}</span>
                    <span className="ink-muted text-[13px] tabular-nums">{r.value}</span>
                  </div>
                  <div className="mt-1.5 h-1.5 rounded-full" style={{ background: 'color-mix(in oklch, var(--foreground) 8%, transparent)' }}>
                    <div className="h-full rounded-full" style={{ width: `${r.value}%`, background: 'var(--brand)' }} />
                  </div>
                </li>
              ))}
            </ul>
            <p className="ink-fainter text-[12px] mt-4 max-w-narrative leading-relaxed">
              Components of Arth's ranking score (0–100). Higher contributes more to where this setup ranks.
            </p>
          </section>
        </FadeIn>
      )}

      {opt.rejected.length > 0 && (
        <FadeIn delay={0.2}>
          <section className="mb-20">
            <MetaLabel>Considered &amp; rejected</MetaLabel>
            <ul className="mt-6 space-y-4 max-w-copy">
              {opt.rejected.map((r, i) => (
                <li key={i} className="border-t border-hairline pt-4">
                  <div className="ink-primary text-[14px] mb-1">{r.name}</div>
                  <div className="ink-muted text-[13px] leading-relaxed">{r.reason}</div>
                </li>
              ))}
            </ul>
            <p className="ink-fainter text-[12px] mt-4 max-w-narrative leading-relaxed">
              Structures Arth weighed for this name and passed on.
            </p>
          </section>
        </FadeIn>
      )}

      <FadeIn delay={0.22}>
        <section className="border-t border-hairline pt-10 max-w-narrative">
          <p className="ink-muted text-[13px] leading-relaxed">
            {isEngine
              ? 'Engine setup — a defined-risk structure the paper engine can open and risk-manage.'
              : 'Research idea — a structure the engine does not trade; shown to learn from, not to execute.'}
          </p>
          <p className="ink-muted text-[13px] leading-relaxed mt-2">
            Paper only — this surface observes and explains; it never opens or
            executes a position. Profit, risk and breakeven figures are not
            shown yet (the setup carries only the short leg).
          </p>
          <Link to={OPTIONS_TAB_HREF} className="text-meta ink-primary mt-4 inline-block" style={{ fontWeight: 600 }}>
            Back to options in Opportunities →
          </Link>
        </section>
      </FadeIn>
    </ArthosPage>
  );
}

function Tag({ children, tone = 'muted' }: { children: React.ReactNode; tone?: 'muted' | 'warn' }) {
  const color = tone === 'warn' ? AMBER : 'var(--foreground)';
  return (
    <span className="px-2.5 py-0.5 rounded-full" style={{
      fontSize: 11.5, fontWeight: 500,
      backgroundColor: `color-mix(in oklch, ${color} 10%, transparent)`,
      color,
      border: `1px solid color-mix(in oklch, ${color} 20%, transparent)`,
    }}>{children}</span>
  );
}
