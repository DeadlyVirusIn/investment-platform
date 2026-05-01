import { Link } from 'react-router-dom';
import ActionStack from '@/components/ActionStack';
import Badge from '@/components/Badge';
import Card from '@/components/Card';
import DecisionQualityRibbon, {
  deriveVerdict,
} from '@/components/DecisionQualityRibbon';
import PageHeader from '@/components/PageHeader';
import StatCard from '@/components/StatCard';
import { EmptyState, ErrorState, LoadingState } from '@/components/States';
import ResearchPulseCard from '@/components/research/ResearchPulseCard';
import UpdatedLabel from '@/components/UpdatedLabel';
import {
  useDashboardSummary,
  useIntelligenceSummary,
  usePnlSummary,
} from '@/lib/hooks';
import {
  formatCurrency,
  formatPercent,
  formatSignedCurrency,
  formatSignedPercent,
  n,
  pnlToneClass,
} from '@/lib/format';

export default function Dashboard() {
  const intelQ = useIntelligenceSummary();
  const dashQ = useDashboardSummary();
  const pnlQ = usePnlSummary();

  if (dashQ.isLoading || intelQ.isLoading) return <LoadingState />;
  if (dashQ.error) return <ErrorState message={String(dashQ.error)} />;

  const intel = intelQ.data;
  const dash = dashQ.data;
  const pnl = pnlQ.data;
  const verdict = deriveVerdict(
    intel?.decision_review?.accepted_vs_blocked ?? null,
  );
  const dailyPnl = pnl?.daily_pnl ?? null;
  const cumPnl = pnl?.cumulative_pnl ?? null;
  const pnlPositive = n(dailyPnl) !== null && n(dailyPnl)! >= 0;
  const cumPositive = n(cumPnl) !== null && n(cumPnl)! >= 0;

  const misalignment =
    (verdict === 'red' || verdict === 'yellow') && cumPositive;

  return (
    <>
      <PageHeader
        title="Command Center"
        subtitle={
          dash?.as_of_date
            ? `Default Paper — ${dash.as_of_date}`
            : 'Default Paper'
        }
        actions={<UpdatedLabel at={dashQ.dataUpdatedAt} />}
      />

      {/* Decision-quality ribbon above PnL — intentionally dominates */}
      <DecisionQualityRibbon intelligence={intel} className="mb-3" />

      {misalignment && (
        <div className="mb-4 rounded-md border border-warning/40 bg-warning/10 px-4 py-2 text-xs text-warning">
          Returns positive but signal quality deteriorating — review
          decision review before adding risk.
        </div>
      )}

      {/* ZONE A — WHAT'S HAPPENING */}
      <Zone label="What's happening">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="NAV"
            value={formatCurrency(pnl?.nav)}
          />
          <StatCard
            label="Daily PnL"
            value={formatSignedCurrency(dailyPnl)}
            tone={pnlPositive ? 'positive' : 'negative'}
          />
          <StatCard
            label="Cumulative PnL"
            value={formatSignedCurrency(cumPnl)}
            tone={cumPositive ? 'positive' : 'negative'}
          />
          <StatCard
            label="Cash %"
            value={formatPercent(intel?.portfolio?.cash_pct)}
            tone="muted"
          />
        </div>

        <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card title="Regime" contentClassName="px-5 py-4">
            {dash?.regime ? (
              <div className="flex flex-wrap gap-2">
                <Badge tone="info">trend: {dash.regime.market_trend}</Badge>
                <Badge tone={dash.regime.vol_regime === 'high' ? 'warning' : 'muted'}>
                  vol: {dash.regime.vol_regime}
                </Badge>
                <span className="text-xs text-text-muted self-center">
                  rv20 {dash.regime.realized_vol_20d} · ATR pct {dash.regime.atr_pctile_1y}
                </span>
              </div>
            ) : (
              <EmptyState title="No regime snapshot" />
            )}
          </Card>

          <Card title="Top positions" contentClassName="px-5 py-4">
            {intel?.portfolio?.top_positions && intel.portfolio.top_positions.length > 0 ? (
              <ul className="divide-y divide-surface-border/60">
                {intel.portfolio.top_positions.slice(0, 5).map((p) => (
                  <li key={p.symbol ?? Math.random()} className="py-1.5 flex items-center gap-3">
                    <span className="w-16 font-medium">{p.symbol ?? '—'}</span>
                    <span className="text-text-muted text-xs w-20">
                      {formatPercent(p.weight)}
                    </span>
                    <span
                      className={`ml-auto font-mono tabular-nums text-sm ${pnlToneClass(p.unrealized_pnl)}`}
                    >
                      {formatSignedCurrency(p.unrealized_pnl)}
                    </span>
                    <span
                      className={`text-xs font-mono tabular-nums ${pnlToneClass(p.unrealized_pct)}`}
                    >
                      {formatSignedPercent(p.unrealized_pct)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <span className="text-text-muted text-sm">No open positions.</span>
            )}
          </Card>
        </div>
      </Zone>

      {/* ZONE B — WHAT TO WATCH */}
      <Zone label="What to watch">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card
            title={`Top accepted Buys (${dash?.top_buys?.length ?? 0})`}
            contentClassName="px-5 py-4"
            actions={
              <Link to="/recommendations" className="text-xs text-accent hover:underline">
                Open
              </Link>
            }
          >
            {dash?.top_buys && dash.top_buys.length > 0 ? (
              <ul className="divide-y divide-surface-border/60">
                {dash.top_buys.slice(0, 5).map((b) => (
                  <li key={b.symbol} className="py-1.5 flex items-center gap-3">
                    <span className="w-16 font-medium">{b.symbol}</span>
                    <span className="text-xs text-text-muted">{b.sector}</span>
                    <span className="ml-auto font-mono tabular-nums">
                      {b.composite_score ?? '—'}
                    </span>
                    <span className="text-xs text-text-muted">
                      conf {b.confidence ?? '—'}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="No accepted Buys today" />
            )}
          </Card>

          <Card
            title="Missed opportunities"
            contentClassName="px-5 py-4"
            actions={
              <Link to="/intelligence" className="text-xs text-accent hover:underline">
                Details
              </Link>
            }
          >
            {intel?.decision_review?.missed_opportunities &&
             intel.decision_review.missed_opportunities.length > 0 ? (
              <ul className="divide-y divide-surface-border/60">
                {intel.decision_review.missed_opportunities.slice(0, 5).map((m, i) => (
                  <li key={i} className="py-1.5 flex items-center gap-3">
                    <span className="w-16 font-medium">{m.symbol ?? '—'}</span>
                    <span className="text-xs text-text-muted">{m.as_of_date}</span>
                    <Badge tone="warning">{m.rejection_reason}</Badge>
                    <span
                      className={`ml-auto font-mono tabular-nums ${pnlToneClass(m.return_pct)}`}
                    >
                      {formatSignedPercent(m.return_pct)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <span className="text-text-muted text-sm">
                No blocked-alpha winners flagged.
              </span>
            )}
          </Card>
        </div>
      </Zone>

      {/* ZONE C — WHAT TO DO (Decision UX v1: ActionStack) */}
      <Zone label="What to do">
        <Card contentClassName="px-5 py-4">
          <ActionStack compact />
        </Card>
      </Zone>

      {/*
        Phase 11W (Phase B) — Research Pulse card. Mounted only when
        VITE_RESEARCH_RO_ENABLED === 'true'. Phase B = empty state.
      */}
      {import.meta.env.VITE_RESEARCH_RO_ENABLED === 'true' && (
        <Zone label="Research">
          <ResearchPulseCard />
        </Zone>
      )}
    </>
  );
}

function Zone({
  label, children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-6">
      <div className="text-[11px] font-semibold tracking-wider uppercase text-text-secondary mb-2">
        {label}
      </div>
      {children}
    </section>
  );
}
