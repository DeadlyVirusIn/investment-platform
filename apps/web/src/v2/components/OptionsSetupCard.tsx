// OptionsSetupCard — trader-facing options setup, styled to mirror the
// stock RecCard / LiveTodayHero. Two layouts:
//   - featured: the hero card (strategy, confidence, descriptor, thesis,
//     "Why Arth likes this", catalyst, CTA)
//   - row (OptionsSetupRow): a compact "also actionable" line item
//
// Leads with the setup, never telemetry. Shows ONLY truthful fields the
// opportunity card carries (strategy, confidence, DTE, bias, premium /
// liquidity tier, thesis, catalyst). NO Max Profit / Max Risk / POP — those
// are deferred to Phase C (see optionsPresent.ts). Read-only; no trade
// controls. UI-only.

import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { SurfaceCard } from './ui/SurfaceCard';
import { TickerBadge } from './IdeaIdentity';
import type { PresentedOption, BiasTone, ActionTone } from '../lib/optionsPresent';

const AMBER = 'oklch(0.70 0.14 75)';

export const OPTIONS_TAB_HREF = '/opportunities?tab=options';

/** Detail route for a single setup (Phase B). */
export function optionDetailHref(observationId: number): string {
  return `/today/options/${observationId}`;
}

function toneColor(tone: BiasTone): string {
  switch (tone) {
    case 'bull': return 'var(--brand)';
    case 'bear': return 'var(--destructive)';
    case 'vol': return AMBER;
    case 'neutral':
    default: return 'var(--muted-foreground)';
  }
}

function Chip({
  children, tone = 'brand',
}: {
  children: React.ReactNode;
  tone?: 'brand' | 'warn' | 'muted';
}) {
  const color = tone === 'warn' ? AMBER
    : tone === 'muted' ? 'var(--foreground)' : 'var(--brand)';
  return (
    <span className="px-2.5 py-0.5 rounded-full" style={{
      fontSize: 11.5, fontWeight: 500,
      backgroundColor: `color-mix(in oklch, ${color} 10%, transparent)`,
      color,
      border: `1px solid color-mix(in oklch, ${color} 20%, transparent)`,
    }}>{children}</span>
  );
}

function ToneDot({ tone }: { tone: BiasTone }) {
  return (
    <span
      aria-hidden
      className="inline-block rounded-full"
      style={{ width: 7, height: 7, backgroundColor: toneColor(tone) }}
    />
  );
}

const ACTION_COLOR: Record<ActionTone, string> = {
  open: 'var(--brand)',
  consider: 'var(--brand)',
  watch: AMBER,
  skip: 'var(--muted-foreground)',
};

/** Phase D — Open|Consider|Watch|Skip pill (Open is the solid CTA). */
export function ActionPill({ action }: { action: PresentedOption['action'] }) {
  const c = ACTION_COLOR[action.tone];
  const solid = action.tone === 'open';
  return (
    <span className="shrink-0 px-2.5 py-0.5 rounded-full font-semibold uppercase" style={{
      fontSize: 10.5, letterSpacing: '0.08em',
      color: solid ? 'var(--brand-foreground)' : c,
      backgroundColor: solid ? c : `color-mix(in oklch, ${c} 12%, transparent)`,
      border: `1px solid color-mix(in oklch, ${c} ${solid ? 0 : 26}%, transparent)`,
    }}>{action.label}</span>
  );
}

/** The hero / featured setup card. */
export function OptionsSetupCard({
  opt, featured = false, href, badge, showCta = true,
}: {
  opt: PresentedOption;
  featured?: boolean;
  href?: string;
  badge?: string;
  showCta?: boolean;
}) {
  const target = href ?? optionDetailHref(opt.observationId);
  return (
    <SurfaceCard variant={featured ? 'highlight' : 'default'} className={featured ? 'p-6 lg:p-7' : 'p-5'}>
      {badge && (
        <div className="mb-2">
          <span className="px-2 py-0.5 rounded-full font-semibold uppercase"
            style={{
              fontSize: 10, letterSpacing: '0.14em',
              backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)',
            }}>{badge}</span>
        </div>
      )}

      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 flex-wrap min-w-0">
          <TickerBadge symbol={opt.underlying} size={featured ? 'lg' : 'md'} />
          <span className="ink-primary" style={{ fontSize: featured ? 16 : 14, fontWeight: 600 }}>
            {opt.strategyName}
          </span>
        </div>
        <ActionPill action={opt.action} />
      </div>

      <div className="flex items-center gap-2 mt-2" style={{ fontSize: 12.5, color: 'var(--muted-foreground)' }}>
        <ToneDot tone={opt.tone} />
        <span>{opt.descriptor}</span>
      </div>

      {/* Phase D — primary chips only (Confidence · DTE · Max profit · Max
          risk). Secondary chips (premium/liquidity/qualified) live on the
          detail page; freshness shows here only when stale (trust warning). */}
      <div className="flex items-center gap-2 flex-wrap mt-3">
        {/* P1.2 — qualitative label only; the numeric is a per-strategy
            constant until the derived score ships (P0-2B). */}
        <Chip>{opt.confidenceLabel} confidence</Chip>
        <Chip tone="muted">DTE {opt.dte}</Chip>
        {opt.economics && <Chip tone="muted">Max profit {opt.economics.maxProfit}</Chip>}
        {opt.economics && <Chip tone="muted">Max risk {opt.economics.maxRisk}</Chip>}
        {opt.economics?.pop && <Chip>POP {opt.economics.pop}</Chip>}
        {opt.freshness.stale && <Chip tone="warn">Stale</Chip>}
        {opt.assignment?.showChip && (
          <Chip tone="warn">⚠ Assignment risk: {opt.assignment.label}</Chip>
        )}
      </div>
      {opt.economics?.riskRewardLine && (
        <p className="ink-muted mt-2" style={{ fontSize: 12.5 }}>
          {opt.economics.riskRewardLine}
          {opt.economics.rrRatio ? ` · R:R ${opt.economics.rrRatio}` : ''}
        </p>
      )}

      {opt.catalyst && (
        <p className="mt-3" style={{ fontSize: 12.5, color: AMBER, fontWeight: 600 }}>
          ⚡ {opt.catalyst}
        </p>
      )}

      {featured && opt.thesis && (
        <p className="ink-primary leading-relaxed mt-4 max-w-narrative" style={{ fontSize: 15 }}>
          {opt.thesis}
        </p>
      )}

      {featured && opt.whyPoints.length > 0 && (
        <div className="mt-4">
          <p className="font-semibold uppercase mb-2" style={{
            fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
          }}>Why Arth likes this</p>
          <ul className="space-y-1.5">
            {opt.whyPoints.map((p, i) => (
              <li key={i} className="ink-primary flex gap-2" style={{ fontSize: 13.5, lineHeight: 1.55 }}>
                <span aria-hidden style={{ color: 'var(--brand)' }}>•</span>
                <span>{p}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {showCta && (
        <div className="mt-5">
          <Link
            to={target}
            className="inline-flex items-center gap-2 h-10 px-4 rounded-full"
            style={{ fontSize: 13, fontWeight: 600, backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)' }}
          >
            View full setup <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        </div>
      )}
    </SurfaceCard>
  );
}

/** Compact "also actionable" row — mirrors the stock hero's list rows. */
export function OptionsSetupRow({
  opt, href,
}: {
  opt: PresentedOption;
  href?: string;
}) {
  return (
    <Link
      to={href ?? optionDetailHref(opt.observationId)}
      className="flex items-center justify-between gap-3 py-2"
    >
      <span className="flex items-center gap-2 min-w-0">
        <TickerBadge symbol={opt.underlying} size="sm" />
        <span className="ink-muted truncate" style={{ fontSize: 12.5 }}>{opt.strategyName}</span>
      </span>
      <span className="shrink-0 tabular-nums flex items-baseline gap-1.5" style={{ fontSize: 12.5 }}>
        <span style={{ color: ACTION_COLOR[opt.action.tone], fontWeight: 600 }}>{opt.action.label}</span>
        <span className="ink-muted">· {opt.dte}d</span>
      </span>
    </Link>
  );
}
