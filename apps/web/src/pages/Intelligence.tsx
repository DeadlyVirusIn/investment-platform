import Badge from '@/components/Badge';
import Card from '@/components/Card';
import PageHeader from '@/components/PageHeader';
import { ErrorState, LoadingState } from '@/components/States';
import UpdatedLabel from '@/components/UpdatedLabel';
import { useIntelligenceSummary } from '@/lib/hooks';
import {
  formatCurrency,
  formatPercent,
  formatSignedCurrency,
  formatSignedPercent,
  n,
  pnlToneClass,
} from '@/lib/format';
import type {
  DecisionReview,
  NewsAnalysis,
  PortfolioIntel,
  TuningSuggestion,
} from '@/types';

export default function Intelligence() {
  const q = useIntelligenceSummary();

  if (q.isLoading) return <LoadingState />;
  if (q.error) return <ErrorState message={String(q.error)} />;
  if (!q.data) return <LoadingState />;

  const { decision_review, portfolio, news, tuning_advice } = q.data;

  return (
    <>
      <PageHeader
        title="Intelligence Console"
        subtitle="Decision quality · portfolio insight · tuning advice · news usefulness"
        actions={<UpdatedLabel at={q.dataUpdatedAt} />}
      />

      <TuningAdviceCard suggestions={tuning_advice.suggestions} />
      <DecisionReviewCard review={decision_review} />
      <PortfolioIntelligenceCard p={portfolio} />
      <NewsInsightCard news={news} />
    </>
  );
}

// ---------------------------------------------------------------------------
// Tuning advice
// ---------------------------------------------------------------------------


function sevTone(s: string): 'info' | 'warning' | 'negative' | 'muted' {
  if (s === 'critical') return 'negative';
  if (s === 'warn') return 'warning';
  if (s === 'info') return 'info';
  return 'muted';
}


function TuningAdviceCard({ suggestions }: { suggestions: TuningSuggestion[] }) {
  return (
    <Card title="What to tune next" className="mb-6" contentClassName="px-5 py-4">
      <ul className="space-y-3">
        {suggestions.map((s, i) => (
          <li
            key={`${s.code}-${i}`}
            className="flex items-start gap-3 border border-surface-border/50 rounded-md px-3 py-2"
          >
            <Badge tone={sevTone(s.severity)}>{s.severity}</Badge>
            <div className="flex-1">
              <div className="text-sm text-text-primary font-medium">
                {s.message}
              </div>
              <div className="text-xs text-text-secondary mt-0.5">
                {s.reasoning}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Decision review
// ---------------------------------------------------------------------------


function DecisionReviewCard({ review }: { review: DecisionReview }) {
  const avb = review.accepted_vs_blocked;

  return (
    <Card title="Decision review" className="mb-6" contentClassName="px-5 py-4">
      {review.sample_notes.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {review.sample_notes.map(note => (
            <Badge key={note} tone="muted">
              {note}
            </Badge>
          ))}
        </div>
      )}

      {avb && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-sm">
          <Stat
            label="Accepted avg return"
            value={formatSignedPercent(avb.accepted_avg_return_pct)}
            tone={
              n(avb.accepted_avg_return_pct) !== null &&
              n(avb.accepted_avg_return_pct)! >= 0
                ? 'positive' : 'negative'
            }
            secondary={`${avb.accepted_count} trade(s)`}
          />
          <Stat
            label="Blocked-alpha avg"
            value={formatSignedPercent(avb.blocked_avg_return_pct)}
            tone={
              n(avb.blocked_avg_return_pct) !== null &&
              n(avb.blocked_avg_return_pct)! >= 0
                ? 'positive' : 'negative'
            }
            secondary={`${avb.blocked_count} sim(s)`}
          />
          <Stat
            label="Accepted win rate"
            value={formatPercent(avb.accepted_win_rate)}
          />
          <Stat
            label="Win-rate delta"
            value={
              avb.win_rate_delta == null
                ? '—'
                : formatSignedPercent(avb.win_rate_delta)
            }
            tone={
              n(avb.win_rate_delta) !== null && n(avb.win_rate_delta)! >= 0
                ? 'positive' : 'negative'
            }
            secondary="accepted − blocked"
          />
        </div>
      )}

      {/* Score bucket performance */}
      <SectionHeader label="Performance by entry composite bucket" />
      <ul className="text-sm divide-y divide-surface-border/40">
        {review.bucket_performance.map(b => (
          <li key={b.bucket} className="py-1.5 flex items-center gap-4">
            <span className="w-28 font-medium">{b.bucket}</span>
            <span className="text-text-muted w-20 text-xs">
              {b.trade_count} trade{b.trade_count === 1 ? '' : 's'}
            </span>
            <span className={`w-28 text-right font-mono tabular-nums ${pnlToneClass(b.avg_pnl_per_trade)}`}>
              {formatSignedCurrency(b.avg_pnl_per_trade)}
            </span>
            <span className="text-text-muted text-xs">
              WR {formatPercent(b.win_rate)}
            </span>
          </li>
        ))}
      </ul>

      {/* Top rejection reasons */}
      {review.rejection_quality.length > 0 && (
        <>
          <SectionHeader label="Top rejection reasons" className="mt-4" />
          <ul className="text-sm divide-y divide-surface-border/40">
            {review.rejection_quality.slice(0, 5).map(rq => (
              <li key={rq.reason} className="py-1.5 flex items-center gap-4">
                <Badge tone="warning">{rq.reason}</Badge>
                <span className="text-text-muted text-xs">
                  {rq.rejected_count} rejected
                </span>
                <span className="text-text-muted text-xs ml-auto">
                  sim n={rq.simulated_count} · avg{' '}
                  {formatSignedPercent(rq.simulated_avg_return)}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      {/* Missed opportunities */}
      {review.missed_opportunities.length > 0 && (
        <>
          <SectionHeader label="Biggest missed winners" className="mt-4" />
          <ul className="text-sm divide-y divide-surface-border/40">
            {review.missed_opportunities.map((m, i) => (
              <li key={i} className="py-1.5 flex items-center gap-4">
                <span className="w-16 font-medium">{m.symbol ?? '—'}</span>
                <span className="text-text-muted text-xs w-24">
                  {m.as_of_date}
                </span>
                <Badge tone="warning">{m.rejection_reason}</Badge>
                <span
                  className={`ml-auto font-mono tabular-nums ${pnlToneClass(m.return_pct)}`}
                >
                  {formatSignedPercent(m.return_pct)}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Portfolio intelligence
// ---------------------------------------------------------------------------


function PortfolioIntelligenceCard({ p }: { p: PortfolioIntel }) {
  return (
    <Card
      title="Portfolio intelligence"
      className="mb-6"
      contentClassName="px-5 py-4"
    >
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-sm">
        <Stat label="NAV" value={formatCurrency(p.nav)} />
        <Stat
          label="Cash"
          value={formatCurrency(p.cash)}
          secondary={`${formatPercent(p.cash_pct)} of NAV`}
          tone="muted"
        />
        <Stat label="Invested" value={formatCurrency(p.invested)} />
        <Stat label="Positions" value={String(p.open_positions)} />
      </div>

      {p.flags.length > 0 ? (
        <div className="mb-4">
          <SectionHeader label="Flags" />
          <div className="flex flex-wrap gap-2">
            {p.flags.map(f => (
              <Badge key={f} tone="warning">
                {f}
              </Badge>
            ))}
          </div>
        </div>
      ) : (
        <div className="mb-4 text-text-muted text-xs">
          No risk flags raised.
        </div>
      )}

      {p.top_positions.length > 0 && (
        <>
          <SectionHeader label="Top positions" />
          <ul className="text-sm divide-y divide-surface-border/40">
            {p.top_positions.map(tp => (
              <li
                key={tp.symbol ?? Math.random()}
                className="py-1.5 flex items-center gap-4"
              >
                <span className="w-16 font-medium">{tp.symbol ?? '—'}</span>
                <span className="text-text-muted text-xs w-20">
                  {formatPercent(tp.weight)}
                </span>
                <span
                  className={`ml-auto font-mono tabular-nums ${pnlToneClass(tp.unrealized_pnl)}`}
                >
                  {formatSignedCurrency(tp.unrealized_pnl)}
                </span>
                <span
                  className={`text-xs font-mono tabular-nums ${pnlToneClass(tp.unrealized_pct)}`}
                >
                  {formatSignedPercent(tp.unrealized_pct)}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      {p.sector_exposure.length > 0 && (
        <>
          <SectionHeader label="Sector exposure" className="mt-4" />
          <div className="flex flex-wrap gap-2">
            {p.sector_exposure.map(s => (
              <Badge key={s.sector} tone="muted">
                {s.sector}: {formatPercent(s.weight)}
              </Badge>
            ))}
          </div>
        </>
      )}

      {p.regime_mix.length > 0 && (
        <>
          <SectionHeader label="Regime at entry" className="mt-4" />
          <div className="flex flex-wrap gap-2">
            {p.regime_mix.map((r, i) => (
              <Badge key={`${r.market_trend}-${r.vol_regime}-${i}`} tone="info">
                {r.market_trend} · {r.vol_regime} ({r.count})
              </Badge>
            ))}
          </div>
        </>
      )}

      {(p.avg_slippage_bps || p.max_slippage_bps) && (
        <div className="mt-4 text-xs text-text-muted">
          Slippage — avg {p.avg_slippage_bps ?? '—'} bps · max{' '}
          {p.max_slippage_bps ?? '—'} bps
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// News analysis
// ---------------------------------------------------------------------------


function NewsInsightCard({ news }: { news: NewsAnalysis }) {
  const hasData =
    news.trades_analyzed > 0 &&
    (news.by_sentiment.length > 0 || news.by_category.length > 0);

  return (
    <Card title="News usefulness" contentClassName="px-5 py-4">
      {!hasData ? (
        <div className="text-text-muted text-sm">
          Not enough linked trades to judge news signal yet.
          {news.sample_notes.length > 0 && (
            <span className="ml-2 italic">({news.sample_notes.join(', ')})</span>
          )}
        </div>
      ) : (
        <>
          <div className="mb-3 text-sm">
            {news.trades_analyzed} trade{news.trades_analyzed === 1 ? '' : 's'}{' '}
            analyzed · alignment{' '}
            <span className="font-medium">
              {formatPercent(news.alignment_pct)}
            </span>
          </div>

          {news.by_sentiment.length > 0 && (
            <>
              <SectionHeader label="By sentiment" />
              <ul className="text-sm divide-y divide-surface-border/40 mb-3">
                {news.by_sentiment.map(s => (
                  <li key={s.key} className="py-1.5 flex items-center gap-4">
                    <span className="w-20 font-medium capitalize">{s.key}</span>
                    <span className="text-text-muted text-xs w-20">
                      n={s.trade_count}
                    </span>
                    <span
                      className={`ml-auto font-mono tabular-nums ${pnlToneClass(s.avg_return_pct)}`}
                    >
                      {formatSignedPercent(s.avg_return_pct)}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {news.by_category.length > 0 && (
            <>
              <SectionHeader label="By category" />
              <ul className="text-sm divide-y divide-surface-border/40">
                {news.by_category.map(s => (
                  <li key={s.key} className="py-1.5 flex items-center gap-4">
                    <span className="w-24 capitalize">{s.key}</span>
                    <span className="text-text-muted text-xs w-20">
                      n={s.trade_count}
                    </span>
                    <span
                      className={`ml-auto font-mono tabular-nums ${pnlToneClass(s.avg_return_pct)}`}
                    >
                      {formatSignedPercent(s.avg_return_pct)}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Small primitives
// ---------------------------------------------------------------------------


function SectionHeader({
  label, className = '',
}: {
  label: string;
  className?: string;
}) {
  return (
    <div
      className={`text-[11px] font-semibold tracking-wider uppercase text-text-secondary mb-2 ${className}`}
    >
      {label}
    </div>
  );
}

function Stat({
  label, value, secondary, tone = 'neutral',
}: {
  label: string;
  value: string;
  secondary?: string;
  tone?: 'neutral' | 'positive' | 'negative' | 'muted';
}) {
  const toneClass =
    tone === 'positive'
      ? 'text-success'
      : tone === 'negative'
      ? 'text-danger'
      : tone === 'muted'
      ? 'text-text-secondary'
      : 'text-text-primary';
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-text-muted">
        {label}
      </div>
      <div className={`mt-0.5 font-mono tabular-nums text-lg ${toneClass}`}>
        {value}
      </div>
      {secondary && (
        <div className="text-xs text-text-muted mt-0.5">{secondary}</div>
      )}
    </div>
  );
}
