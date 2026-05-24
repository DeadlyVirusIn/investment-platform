// V2 Today's Briefing — Phase C visual-parity rebuild.
//
// 8/4 desktop grid. Six cards. No editorial single-stream prose any
// more — the AI Copilot answer to "what should I do today?" is
// surfaced in structured cards with brand-tinted CTAs.
//
//   Main column (lg:col-span-8):
//     • WhatChanged       — 3 most-recent updates
//     • StrongestSetup    — top opportunity with RiskBadge + AcademyChips
//     • NearestCatalyst   — earliest catalyst with date + days-away
//
//   Aside column (lg:col-span-4):
//     • FollowedDecisions — useFollowedDecisions wired to journalEntries
//     • WorthLearning     — daily lesson recommendation
//     • PortfolioSummary  — equity + day-move + lifetime-move + position count
//
// All data sourced from existing arthosData / journal-data / state.
// No new backend, no new tracking, no new APIs.

import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, Calendar, Sparkles, BookOpen, Eye } from 'lucide-react';
import { ArthosPage } from '../chrome/ArthosChrome';
import { PageHeader } from '../components/ui/PageHeader';
import { Section } from '../components/ui/Section';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import { RiskBadge } from '../components/ui/RiskBadge';
import { AcademyChips } from '../components/ui/AcademyChips';
import {
  PORTFOLIO,
  WHAT_CHANGED_SINCE_YESTERDAY,
  LESSONS,
} from '../data/arthosData';
import {
  opportunities,
  journalEntries,
  getEntry,
} from '../data/journal-data';
import { useFollowedDecisions } from '../lib/lesson-progress';
import { useReadLessons } from '../lib/lesson-progress';
// Arth MVP — hero card replaces StrongestSetupCard; opening at top.
import { ArthOpening } from '../components/ArthOpening';
import { ArthHeroCard } from '../components/ArthHeroCard';
import { TrustBanner } from '../components/TrustBanner';
import { TodayLessonSlot } from '../components/TodayLessonSlot';
import { generateBriefing } from '../lib/arth/briefing';
import { todayKey } from '../lib/arth/storage';
import { useStreak } from '../lib/arth/streak';

function FadeIn({
  delay = 0,
  children,
  className,
}: {
  delay?: number;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay, ease: [0.32, 0.72, 0, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 5) return 'Late evening';
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  if (hour < 21) return 'Good evening';
  return 'Late evening';
}

// ──────────────────────────────────────────────────────────────
// Main-column cards
// ──────────────────────────────────────────────────────────────

function WhatChangedCard() {
  const items = WHAT_CHANGED_SINCE_YESTERDAY.slice(0, 3);
  return (
    <SurfaceCard variant="muted">
      <div className="flex items-center gap-2 mb-4">
        <Sparkles className="size-4 ink-brand" aria-hidden />
        <p
          className="font-semibold uppercase"
          style={{
            fontSize: 11,
            letterSpacing: '0.16em',
            color: 'var(--muted-foreground)',
          }}
        >
          What changed
        </p>
      </div>
      <ul className="space-y-4">
        {items.map((c, i) => (
          <li key={i} className="flex items-baseline gap-4">
            <span
              aria-hidden
              className="font-mono tabular-nums shrink-0 mt-0.5"
              style={{
                fontSize: 11,
                color: 'var(--muted-foreground)',
                width: 18,
              }}
            >
              {String(i + 1).padStart(2, '0')}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-2 mb-1 flex-wrap">
                <span
                  className="ink-primary leading-snug"
                  style={{ fontSize: 14.5 }}
                >
                  {c.headline}
                </span>
                {c.symbol && (
                  <span
                    className="font-mono tabular-nums"
                    style={{ fontSize: 11, color: 'var(--muted-foreground)' }}
                  >
                    {c.symbol}
                  </span>
                )}
              </div>
              <p
                className="ink-muted leading-relaxed max-w-narrative"
                style={{ fontSize: 13 }}
              >
                {c.body}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </SurfaceCard>
  );
}

function StrongestSetupCard() {
  const top = opportunities[0];
  const entry = top ? getEntry(top.journalId) : null;
  if (!top || !entry) return null;
  return (
    <SurfaceCard variant="highlight">
      <div className="flex items-center gap-2 mb-4">
        <Sparkles className="size-4 ink-brand" aria-hidden />
        <p
          className="font-semibold uppercase"
          style={{
            fontSize: 11,
            letterSpacing: '0.16em',
            color: 'var(--brand)',
          }}
        >
          Strongest setup
        </p>
      </div>
      <div className="flex items-baseline gap-3 mb-3 flex-wrap">
        <span
          className="font-mono ink-primary tabular-nums"
          style={{ fontSize: 18 }}
        >
          {top.ticker}
        </span>
        <RiskBadge risk={top.risk} />
      </div>
      <p
        className="font-display ink-primary leading-snug mb-3 max-w-narrative"
        style={{ fontSize: 20 }}
      >
        {top.thesis}
      </p>
      <p
        className="ink-muted leading-relaxed mb-4 max-w-narrative"
        style={{ fontSize: 14 }}
      >
        {top.edge}
      </p>
      <div className="flex items-center justify-between gap-3 mb-4">
        <AcademyChips academies={top.academies} />
        <span
          className="font-mono tabular-nums"
          style={{ fontSize: 12, color: 'var(--muted-foreground)' }}
        >
          {top.daysToCatalyst}d to catalyst
        </span>
      </div>
      <Link
        to={`/v2/today/pick/${top.ticker}`}
        className="inline-flex items-center gap-2 transition-colors"
        style={{
          fontSize: 13,
          color: 'var(--brand)',
          fontWeight: 600,
        }}
      >
        Read the working <ArrowRight className="size-3.5" aria-hidden />
      </Link>
    </SurfaceCard>
  );
}

function NearestCatalystCard() {
  const sorted = [...opportunities].sort(
    (a, b) => a.daysToCatalyst - b.daysToCatalyst,
  );
  const nearest = sorted[0];
  const entry = nearest ? getEntry(nearest.journalId) : null;
  if (!nearest || !entry) return null;
  const catalyst = entry.catalysts[0];
  return (
    <SurfaceCard>
      <div className="flex items-center gap-2 mb-4">
        <Calendar
          className="size-4"
          style={{ color: 'var(--muted-foreground)' }}
          aria-hidden
        />
        <p
          className="font-semibold uppercase"
          style={{
            fontSize: 11,
            letterSpacing: '0.16em',
            color: 'var(--muted-foreground)',
          }}
        >
          Nearest catalyst
        </p>
      </div>
      <div className="flex items-baseline gap-3 mb-2 flex-wrap">
        <span
          className="font-mono ink-primary tabular-nums"
          style={{ fontSize: 16 }}
        >
          {nearest.ticker}
        </span>
        <span
          className="font-mono tabular-nums"
          style={{ fontSize: 12, color: 'var(--muted-foreground)' }}
        >
          · {catalyst?.date}
        </span>
      </div>
      <p
        className="font-display ink-primary leading-snug mb-3 max-w-narrative"
        style={{ fontSize: 19 }}
      >
        {catalyst?.label ?? 'Upcoming catalyst'}
      </p>
      <p
        className="ink-muted leading-relaxed mb-4"
        style={{ fontSize: 13.5 }}
      >
        <span
          className="font-mono tabular-nums"
          style={{ color: 'var(--brand)' }}
        >
          {nearest.daysToCatalyst} {nearest.daysToCatalyst === 1 ? 'day' : 'days'}
        </span>{' '}
        away — the moment the thesis behind {nearest.ticker} resolves.
      </p>
      <Link
        to={`/v2/today/pick/${nearest.ticker}`}
        className="inline-flex items-center gap-2 transition-colors"
        style={{ fontSize: 13, color: 'var(--muted-foreground)' }}
      >
        Open the position →
      </Link>
    </SurfaceCard>
  );
}

// ──────────────────────────────────────────────────────────────
// Aside cards
// ──────────────────────────────────────────────────────────────

function FollowedDecisionsCard() {
  const followed = useFollowedDecisions();
  const entries = followed
    .map((id) => getEntry(id))
    .filter((e): e is NonNullable<ReturnType<typeof getEntry>> => Boolean(e));
  if (entries.length === 0) return null;
  return (
    <SurfaceCard>
      <div className="flex items-center gap-2 mb-3">
        <Eye className="size-4 ink-brand" aria-hidden />
        <p
          className="font-semibold uppercase"
          style={{
            fontSize: 11,
            letterSpacing: '0.16em',
            color: 'var(--muted-foreground)',
          }}
        >
          Following
        </p>
      </div>
      <ul className="space-y-2.5">
        {entries.slice(0, 4).map((e) => {
          const pending = e.status === 'active' && !e.outcome;
          return (
            <li key={e.id}>
              <Link
                to={`/v2/reflections`}
                className="group block -mx-2 px-2 py-2 rounded-lg transition-colors"
                style={{
                  backgroundColor: 'transparent',
                }}
                onMouseEnter={(ev) => {
                  ev.currentTarget.style.backgroundColor =
                    'color-mix(in oklch, var(--sage-light) 50%, transparent)';
                }}
                onMouseLeave={(ev) => {
                  ev.currentTarget.style.backgroundColor = 'transparent';
                }}
              >
                <div className="flex items-center gap-2 mb-0.5">
                  <span
                    className="font-mono font-semibold"
                    style={{ fontSize: 11, color: 'var(--muted-foreground)' }}
                  >
                    {e.ticker}
                  </span>
                  {pending && (
                    <span
                      className="font-bold uppercase"
                      style={{
                        fontSize: 10,
                        letterSpacing: '0.12em',
                        color: 'var(--brand)',
                      }}
                    >
                      · pending outcome
                    </span>
                  )}
                </div>
                <p
                  className="ink-primary leading-snug"
                  style={{ fontSize: 13 }}
                >
                  {e.headline}
                </p>
              </Link>
            </li>
          );
        })}
      </ul>
    </SurfaceCard>
  );
}

function WorthLearningCard() {
  // Pick first unread lesson; fall back to first lesson if all read.
  const readSlugs = new Set(useReadLessons());
  const lesson = LESSONS.find((l) => !readSlugs.has(l.slug)) ?? LESSONS[0];
  if (!lesson) return null;
  return (
    <SurfaceCard variant="muted">
      <div className="flex items-center gap-2 mb-3">
        <BookOpen className="size-4 ink-brand" aria-hidden />
        <p
          className="font-semibold uppercase"
          style={{
            fontSize: 11,
            letterSpacing: '0.16em',
            color: 'var(--muted-foreground)',
          }}
        >
          Worth learning
        </p>
      </div>
      <p
        className="font-display ink-primary leading-snug mb-2"
        style={{ fontSize: 17 }}
      >
        {lesson.title}
      </p>
      <p
        className="ink-muted leading-relaxed mb-3 max-w-narrative"
        style={{ fontSize: 13 }}
      >
        {lesson.abstract}
      </p>
      <Link
        to={`/v2/learn/lesson/${lesson.slug}`}
        className="inline-flex items-center gap-1.5"
        style={{
          fontSize: 12,
          color: 'var(--brand)',
          fontWeight: 600,
        }}
      >
        {lesson.readMinutes} min read →
      </Link>
    </SurfaceCard>
  );
}

function PortfolioSummaryCard() {
  return (
    <SurfaceCard>
      <p
        className="font-semibold uppercase mb-3"
        style={{
          fontSize: 11,
          letterSpacing: '0.16em',
          color: 'var(--muted-foreground)',
        }}
      >
        Portfolio
      </p>
      <div className="mb-3">
        <div
          className="font-display ink-primary tabular-nums leading-none mb-2"
          style={{ fontSize: 28 }}
        >
          $
          {PORTFOLIO.equity.toLocaleString(undefined, {
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
          })}
        </div>
        <div
          className="font-mono tabular-nums"
          style={{ fontSize: 12.5 }}
        >
          <span
            style={{
              color:
                PORTFOLIO.dayMovePct >= 0
                  ? 'var(--brand)'
                  : 'var(--destructive)',
            }}
          >
            {PORTFOLIO.dayMovePct >= 0 ? '▲' : '▼'}{' '}
            {PORTFOLIO.dayMovePct >= 0 ? '+' : ''}
            {PORTFOLIO.dayMovePct.toFixed(2)}%
          </span>{' '}
          <span style={{ color: 'var(--muted-foreground)' }}>on the day</span>
        </div>
        <div
          className="font-mono tabular-nums mt-1"
          style={{ fontSize: 11.5, color: 'var(--muted-foreground)' }}
        >
          {PORTFOLIO.lifetimeMovePct >= 0 ? '+' : ''}
          {PORTFOLIO.lifetimeMovePct.toFixed(2)}% since Day 1
        </div>
      </div>
      <div
        className="font-semibold uppercase mb-2.5"
        style={{
          fontSize: 10,
          letterSpacing: '0.12em',
          color: 'var(--muted-foreground)',
        }}
      >
        {PORTFOLIO.positions.length} positions
      </div>
      <ul className="space-y-1.5">
        {PORTFOLIO.positions.slice(0, 6).map((p) => {
          const move = ((p.current - p.costBasis) / p.costBasis) * 100;
          return (
            <li key={p.symbol}>
              <Link
                to={`/v2/today/pick/${p.symbol}`}
                className="flex items-baseline justify-between gap-3 transition-colors"
                style={{ fontSize: 12.5 }}
              >
                <span
                  className="font-mono ink-primary tabular-nums shrink-0"
                  style={{ width: 48 }}
                >
                  {p.symbol}
                </span>
                <span
                  className="flex-1 truncate"
                  style={{ fontSize: 11, color: 'var(--muted-foreground)' }}
                >
                  Day {p.dayHeld}
                </span>
                <span
                  className="font-mono tabular-nums"
                  style={{
                    color:
                      move >= 0 ? 'var(--brand)' : 'var(--destructive)',
                  }}
                >
                  {move >= 0 ? '+' : ''}
                  {move.toFixed(1)}%
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
      <Link
        to="/v2/portfolio"
        className="inline-flex items-center gap-1.5 mt-4 transition-colors"
        style={{ fontSize: 12, color: 'var(--muted-foreground)' }}
      >
        See practice account →
      </Link>
    </SurfaceCard>
  );
}

// ──────────────────────────────────────────────────────────────
// Today shell — Arth MVP wiring
// Arth opening at top + ArthHeroCard replacing StrongestSetupCard.
// Existing sibling cards (WhatChanged / NearestCatalyst / sidebar) kept.
// ──────────────────────────────────────────────────────────────
export function Briefing() {
  const streak = useStreak();
  const briefing = generateBriefing({
    todayKey: todayKey(),
    streakDay: streak.current_day || 1,
  });
  const heroRec = briefing.hero;

  return (
    <ArthosPage topBarEyebrow="Today">
      <FadeIn>
        <PageHeader
          eyebrow={greeting()}
          title={
            <>
              A calm read on
              <br />
              the day ahead.
            </>
          }
          description="No tickers to chase. Your AI copilot walks you through what changed, the strongest setup, the nearest catalyst, and one thing worth learning today."
        />
      </FadeIn>

      <FadeIn delay={0.02}>
        <ArthOpening />
      </FadeIn>

      <FadeIn delay={0.03}>
        <TrustBanner />
      </FadeIn>

      {/* Phase 2D — contextual lesson surfaced when a pattern fires
          or a streak milestone hits. Renders nothing when no trigger. */}
      <FadeIn delay={0.04}>
        <TodayLessonSlot />
      </FadeIn>

      <Section>
        <div className="grid gap-5 lg:gap-6 lg:grid-cols-12">
          <div className="lg:col-span-8 space-y-5 lg:space-y-6">
            <FadeIn delay={0.1}>
              {heroRec ? <ArthHeroCard rec={heroRec} /> : <StrongestSetupCard />}
            </FadeIn>
            <FadeIn delay={0.05}>
              <WhatChangedCard />
            </FadeIn>
            <FadeIn delay={0.15}>
              <NearestCatalystCard />
            </FadeIn>
          </div>

          <aside className="lg:col-span-4 space-y-5 lg:space-y-6">
            <FadeIn delay={0.2}>
              <FollowedDecisionsCard />
            </FadeIn>
            <FadeIn delay={0.25}>
              <WorthLearningCard />
            </FadeIn>
            <FadeIn delay={0.3}>
              <PortfolioSummaryCard />
            </FadeIn>
          </aside>
        </div>
      </Section>

      {/* Trust footer — methodology link reaffirms the AI Copilot
          category every page. */}
      <FadeIn delay={0.4}>
        <div
          className="mt-12 pt-8 flex flex-wrap items-center justify-between gap-3"
          style={{ borderTop: '1px solid var(--border)' }}
        >
          <Link
            to="/v2/methodology"
            className="inline-flex items-center gap-1.5 transition-colors"
            style={{ fontSize: 12, color: 'var(--muted-foreground)' }}
          >
            How ArthOS works →
          </Link>
          <p
            className="italic"
            style={{ fontSize: 11.5, color: 'var(--muted-foreground)' }}
          >
            Practice only · nothing real is at stake · not financial advice
          </p>
        </div>
      </FadeIn>

      {/* Journal-data import keeps the journalEntries source alive
          for downstream surfaces (FollowedDecisionsCard uses getEntry). */}
      <noscript>{journalEntries.length}</noscript>
    </ArthosPage>
  );
}
