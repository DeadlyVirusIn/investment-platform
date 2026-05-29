// V2 Today's Briefing — P0 LIVE rewire.
//
// The hero + actionable list come from the LIVE recommendation engine
// (useTodaysRecommendations → GET /recommendations). NO static
// TODAYS_DESK, NO generateBriefing, NO arthosData recommendation
// literals. The masthead copy is DERIVED from real counts — "No tickers
// to chase" appears ONLY when the backend returns zero actionable Buys,
// and it explains why (from /recommendations/diagnostics).
//
// Sidebar PortfolioSummaryCard + TrustBanner remain live (canonical).

import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArthosPage } from '../chrome/ArthosChrome';
import { PageHeader } from '../components/ui/PageHeader';
import { Section } from '../components/ui/Section';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import { TrustBanner } from '../components/TrustBanner';
import { TodayLessonSlot } from '../components/TodayLessonSlot';
import { LiveTodayHero } from '../components/LiveTodayHero';
import {
  useCanonicalStockPortfolio,
  useTodaysRecommendations,
  useRecommendationDiagnostics,
  selectTopBuy,
  effectiveAction,
  type RecApi,
} from '@/lib/operator/hooks';

function FadeIn({
  delay = 0, children, className,
}: {
  delay?: number; children: React.ReactNode; className?: string;
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

export function Briefing() {
  const { data: recsData, isLoading, isError } = useTodaysRecommendations();
  const { data: diag } = useRecommendationDiagnostics();

  const recs: RecApi[] = recsData?.recommendations ?? [];
  const top = selectTopBuy(recs);
  const alsoBuys = recs.filter(
    (r) => effectiveAction(r) === 'Buy' && r.id !== top?.id,
  );
  const actionableCount = recs.filter((r) => effectiveAction(r) === 'Buy').length;
  const evaluated = diag?.total ?? null;
  const dist = diag?.action_distribution ?? {};

  // Masthead copy derives from real state — never unconditional.
  const hasBuys = top != null;
  const title = hasBuys
    ? <>Your strongest<br />setup today.</>
    : <>A calm read on<br />the day ahead.</>;
  const description = hasBuys
    ? `${actionableCount} actionable Buy${actionableCount === 1 ? '' : 's'}${
        evaluated != null ? ` from ${evaluated} recommendations evaluated today` : ''
      }. Start with the strongest below.`
    : (evaluated != null
        ? `${evaluated} recommendations evaluated today; none cleared the Buy threshold (${dist['Hold'] ?? 0} Hold, ${dist['Trim'] ?? 0} Trim). Nothing to chase right now.`
        : 'No actionable Buy recommendations right now.');

  return (
    <ArthosPage topBarEyebrow="Today">
      <FadeIn>
        <PageHeader eyebrow={greeting()} title={title} description={description} />
      </FadeIn>

      <FadeIn delay={0.03}>
        <TrustBanner />
      </FadeIn>

      <FadeIn delay={0.04}>
        <TodayLessonSlot />
      </FadeIn>

      <Section>
        <div className="grid gap-5 lg:gap-6 lg:grid-cols-12">
          <div className="lg:col-span-8 space-y-5 lg:space-y-6">
            <FadeIn delay={0.1}>
              {isLoading ? (
                <SurfaceCard variant="muted" className="p-6">
                  <p className="ink-muted" style={{ fontSize: 14 }}>
                    Loading today's recommendations…
                  </p>
                </SurfaceCard>
              ) : isError ? (
                <SurfaceCard variant="default" className="p-6">
                  <p style={{ fontSize: 14, color: 'var(--destructive)', fontWeight: 600 }}>
                    Couldn't load recommendations right now.
                  </p>
                </SurfaceCard>
              ) : top ? (
                <LiveTodayHero rec={top} alsoConsider={alsoBuys} />
              ) : (
                <EmptyDesk evaluated={evaluated} dist={dist} />
              )}
            </FadeIn>
          </div>

          <aside className="lg:col-span-4 space-y-5 lg:space-y-6">
            <FadeIn delay={0.2}>
              <PortfolioSummaryCard />
            </FadeIn>
          </aside>
        </div>
      </Section>

      <FadeIn delay={0.4}>
        <div
          className="mt-12 pt-8 flex flex-wrap items-center justify-between gap-3"
          style={{ borderTop: '1px solid var(--border)' }}
        >
          <Link to="/v2/methodology"
            className="inline-flex items-center gap-1.5"
            style={{ fontSize: 12.5, color: 'var(--muted-foreground)' }}>
            How Arth decides →
          </Link>
          <Link to="/v2/opportunities"
            className="inline-flex items-center gap-1.5"
            style={{ fontSize: 12.5, color: 'var(--brand)', fontWeight: 600 }}>
            See the full desk →
          </Link>
        </div>
      </FadeIn>
    </ArthosPage>
  );
}

// Honest empty state — only when the backend has zero actionable Buys.
function EmptyDesk({
  evaluated, dist,
}: {
  evaluated: number | null;
  dist: Record<string, number>;
}) {
  return (
    <SurfaceCard variant="highlight" className="p-6 lg:p-7">
      <p className="font-semibold uppercase mb-2" style={{
        fontSize: 11, letterSpacing: '0.14em', color: 'var(--brand)',
      }}>★ Cash is the call</p>
      <p className="ink-primary leading-relaxed max-w-narrative" style={{ fontSize: 15 }}>
        {evaluated != null
          ? `${evaluated} recommendations were evaluated today; none cleared the Buy threshold.`
          : 'No actionable Buy recommendations right now.'}
      </p>
      <p className="ink-muted leading-relaxed max-w-narrative mt-3" style={{ fontSize: 13.5 }}>
        Breakdown: {dist['Hold'] ?? 0} Hold · {dist['Trim'] ?? 0} Trim · {dist['Buy'] ?? 0} Buy.
        I'd rather show you nothing than manufacture a trade.
      </p>
      <Link to="/v2/opportunities"
        className="inline-flex items-center gap-1.5 mt-4"
        style={{ fontSize: 12.5, color: 'var(--brand)', fontWeight: 600 }}>
        See everything I'm watching →
      </Link>
    </SurfaceCard>
  );
}

// ── Live portfolio sidebar (canonical) ──────────────────────────────
function PortfolioSummaryCard() {
  const { data: book, isLoading } = useCanonicalStockPortfolio();
  const equity = book?.nav ?? null;
  const dayPnl = book?.daily_pnl ?? null;
  const totalRet = book?.total_return_pct ?? null;
  const posCount = book?.open_positions_count ?? null;

  return (
    <SurfaceCard>
      <p className="font-semibold uppercase mb-3" style={{
        fontSize: 11, letterSpacing: '0.16em', color: 'var(--muted-foreground)',
      }}>
        Practice portfolio
      </p>
      {equity == null ? (
        <div className="ink-muted" style={{ fontSize: 12.5, lineHeight: 1.5 }}>
          {isLoading ? 'Loading the practice account…' : 'Practice account is unavailable right now.'}
        </div>
      ) : (
        <>
          <div className="mb-3">
            <div className="font-display ink-primary tabular-nums leading-none mb-2" style={{ fontSize: 28 }}>
              ${equity.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
            </div>
            {dayPnl != null && (
              <div className="font-mono tabular-nums" style={{ fontSize: 12.5 }}>
                <span style={{
                  color: dayPnl > 0 ? 'var(--brand)' : dayPnl < 0 ? 'var(--destructive)' : 'var(--muted-foreground)',
                }}>
                  {dayPnl > 0 ? '▲ +' : dayPnl < 0 ? '▼ −' : ''}${Math.abs(dayPnl).toFixed(2)}
                </span>{' '}
                <span style={{ color: 'var(--muted-foreground)' }}>on the day</span>
              </div>
            )}
            {totalRet != null && (
              <div className="font-mono tabular-nums mt-1" style={{ fontSize: 11.5, color: 'var(--muted-foreground)' }}>
                {totalRet >= 0 ? '+' : ''}{totalRet.toFixed(2)}% since inception
              </div>
            )}
          </div>
          {posCount != null && (
            <div className="font-semibold uppercase mb-2.5" style={{
              fontSize: 10, letterSpacing: '0.12em', color: 'var(--muted-foreground)',
            }}>
              {posCount} open position{posCount === 1 ? '' : 's'}
            </div>
          )}
        </>
      )}
      <Link to="/v2/portfolio"
        className="inline-flex items-center gap-1.5 mt-4 transition-colors"
        style={{ fontSize: 12, color: 'var(--muted-foreground)' }}>
        See practice account →
      </Link>
    </SurfaceCard>
  );
}
