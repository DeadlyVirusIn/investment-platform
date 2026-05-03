import Badge from '@/components/Badge';
import Card from '@/components/Card';
import PageHeader from '@/components/PageHeader';
import StatCard from '@/components/StatCard';
import { EmptyState, ErrorState, LoadingState } from '@/components/States';
import UpdatedLabel from '@/components/UpdatedLabel';
import {
  useBriefingNarrative,
  useDashboardSummary,
  useMarketNewsSummary,
  useNewsSummaryBatch,
} from '@/lib/hooks';
import { NewsSummaryBadges } from '@/components/NewsBadges';
import {
  formatCurrency,
  formatSignedCurrency,
  formatSignedPercent,
  n,
  pnlToneClass,
} from '@/lib/format';

export default function Briefing() {
  const q = useDashboardSummary();
  const marketNewsQ = useMarketNewsSummary(3, 5);
  const narrativeQ = useBriefingNarrative();

  // Derive top-buy symbols BEFORE any early return so hook order stays
  // stable across renders.
  const topBuySymbols =
    (q.data?.top_buys ?? [])
      .map(b => b.symbol)
      .filter((s): s is string => !!s);
  const buyNewsQ = useNewsSummaryBatch(topBuySymbols, 7);

  if (q.isLoading) return <LoadingState />;
  if (q.error) return <ErrorState message={String(q.error)} />;

  const d = q.data;
  if (!d) return <LoadingState />;

  const regime = d.regime;
  const p = d.portfolio;
  const candidates = d.candidates;
  const blocked = d.blocked_alpha;

  return (
    <>
      <PageHeader
        title="Daily Briefing"
        subtitle={
          d.as_of_date
            ? `Default Paper — ${d.as_of_date}`
            : 'Default Paper — no data yet'
        }
        actions={<UpdatedLabel at={q.dataUpdatedAt} />}
      />

      {/* Narrative + Δ vs yesterday */}
      {narrativeQ.data && (
        <Card className="mb-6" contentClassName="px-5 py-4">
          <p className="text-sm text-text-primary leading-relaxed">
            {narrativeQ.data.narrative}
          </p>
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <Delta label="NAV" value={narrativeQ.data.delta.nav}
                   valuePct={narrativeQ.data.delta.nav_pct} money />
            <Delta label="Positions" value={narrativeQ.data.delta.positions} />
            <Delta label="Candidates" value={narrativeQ.data.delta.candidates} />
            {narrativeQ.data.delta.regime_changed && narrativeQ.data.delta.prev_regime && (
              <Badge tone="warning">
                Regime shift: {narrativeQ.data.delta.prev_regime.market_trend}/
                {narrativeQ.data.delta.prev_regime.vol_regime} →{' '}
                {narrativeQ.data.regime?.market_trend}/{narrativeQ.data.regime?.vol_regime}
              </Badge>
            )}
          </div>
        </Card>
      )}

      {/* Portfolio snapshot */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          label="NAV"
          value={p ? formatCurrency(p.nav) : '—'}
          tone="neutral"
        />
        <StatCard
          label="Cash"
          value={p ? formatCurrency(p.cash) : '—'}
          tone="muted"
        />
        <StatCard
          label="Open positions"
          value={p?.open_positions_count ?? 0}
        />
        <StatCard
          label="Accepted Buys"
          value={candidates.accepted_buys}
          secondary={`${candidates.total_evaluated} evaluated`}
        />
      </div>

      {/* Regime */}
      <Card title="Regime" className="mb-6" contentClassName="px-5 py-4">
        {regime ? (
          <div className="flex flex-wrap gap-2 text-sm">
            <Badge tone="info">trend: {regime.market_trend}</Badge>
            <Badge tone={regime.vol_regime === 'high' ? 'warning' : 'muted'}>
              vol: {regime.vol_regime}
            </Badge>
            <Badge tone="muted">
              SPY {regime.sma50_over_sma200 ? 'sma50>sma200' : 'sma50<=sma200'}
            </Badge>
            <span className="text-text-muted text-xs self-center">
              rv20 {regime.realized_vol_20d} · atr p{'{'}pctile{'}'} {regime.atr_pctile_1y}
            </span>
          </div>
        ) : (
          <EmptyState
            title="No regime snapshot"
            hint="compute_regime_snapshot job has not produced today's row yet."
          />
        )}
      </Card>

      {/* Top buys OR no-buy explanation */}
      <Card title="Top Buy candidates" className="mb-6" contentClassName="px-5 py-4">
        {d.top_buys.length > 0 ? (
          <ul className="divide-y divide-surface-border/60">
            {d.top_buys.map(b => (
              <li key={b.symbol} className="py-2 flex items-center justify-between gap-4">
                <span className="font-medium">{b.symbol}</span>
                <span className="text-xs text-text-muted">{b.sector}</span>
                <span className="font-mono tabular-nums text-sm">
                  composite {b.composite_score ?? '—'}
                </span>
                <span className="font-mono tabular-nums text-xs text-text-muted">
                  conf {b.confidence ?? '—'}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            title="No accepted Buys today"
            hint={
              Object.keys(candidates.reasons).length > 0 ? (
                <>
                  Dominant rejection reasons:{' '}
                  {Object.entries(candidates.reasons)
                    .sort(([, a], [, b]) => b - a)
                    .slice(0, 3)
                    .map(([k, v]) => `${k}=${v}`)
                    .join(', ')}
                </>
              ) : (
                <>No candidates evaluated for this date.</>
              )
            }
          />
        )}
      </Card>

      {/* Blocked alpha summary */}
      {blocked.count > 0 && (
        <Card title="Blocked alpha" className="mb-6" contentClassName="px-5 py-4">
          <p className="text-sm text-text-secondary mb-3">
            {blocked.count} rejected candidate(s) with composite ≥ {blocked.min_score}.
          </p>
          <ul className="space-y-1 text-sm">
            {blocked.top.map(item => (
              <li key={item.symbol} className="flex items-center gap-3">
                <span className="font-medium w-16">{item.symbol}</span>
                <span className="font-mono tabular-nums text-xs">
                  {item.composite_score ?? '—'}
                </span>
                <Badge tone="warning">{item.rejection_reason ?? '—'}</Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Top positions */}
      {p && p.top_positions.length > 0 && (
        <Card title="Top positions" className="mb-6" contentClassName="px-5 py-4">
          <ul className="divide-y divide-surface-border/60">
            {p.top_positions.map(pos => (
              <li key={pos.symbol} className="py-2 flex items-center gap-4">
                <span className="font-medium w-20">{pos.symbol}</span>
                <span className="text-xs text-text-muted w-24">
                  weight {(Number(pos.weight) * 100).toFixed(1)}%
                </span>
                <span className={`text-xs font-mono tabular-nums ${
                  n(pos.unrealized_pnl) !== null && n(pos.unrealized_pnl)! >= 0
                    ? 'text-success' : 'text-danger'
                }`}>
                  {formatSignedCurrency(pos.unrealized_pnl)}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Market News */}
      <Card
        title={`Market news (last ${marketNewsQ.data?.window_days ?? 3}d)`}
        className="mb-6"
        contentClassName="px-5 py-4"
      >
        {!marketNewsQ.data || marketNewsQ.data.total_articles === 0 ? (
          <span className="text-text-muted text-sm">
            No recent articles ingested yet.
          </span>
        ) : (
          <>
            <div className="flex flex-wrap gap-2 mb-3 text-xs">
              {Object.entries(marketNewsQ.data.category_counts)
                .sort(([, a], [, b]) => b - a)
                .slice(0, 6)
                .map(([cat, n]) => (
                  <Badge key={cat} tone="muted">
                    {cat}: {n}
                  </Badge>
                ))}
            </div>
            <ul className="divide-y divide-surface-border/60">
              {marketNewsQ.data.top_headlines.map(h => (
                <li key={h.id} className="py-2 flex items-start gap-3">
                  <Badge
                    tone={
                      h.sentiment === 'positive'
                        ? 'positive'
                        : h.sentiment === 'negative'
                        ? 'negative'
                        : 'info'
                    }
                  >
                    {h.sentiment}
                  </Badge>
                  <Badge tone={h.impact_level === 'high' ? 'warning' : 'muted'}>
                    {h.impact_level} impact
                  </Badge>
                  <a
                    href={h.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-1 text-sm text-text-primary hover:text-accent truncate"
                    title={h.title}
                  >
                    {h.title}
                  </a>
                  <span className="text-[11px] text-text-muted shrink-0">
                    {h.published_at.slice(0, 10)}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      {/* Per-Buy news highlights */}
      {d.top_buys.length > 0 && (
        <Card title="News for top Buys" className="mb-6" contentClassName="px-5 py-4">
          <ul className="space-y-3">
            {d.top_buys.map(b => {
              const sum = buyNewsQ.data?.summaries[b.symbol];
              const latest = sum?.latest ?? null;
              return (
                <li key={b.symbol} className="space-y-1">
                  <div className="flex items-center gap-3">
                    <span className="font-medium w-16">{b.symbol}</span>
                    <NewsSummaryBadges summary={sum ?? null} />
                  </div>
                  {latest && (
                    <a
                      href={latest.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block text-xs text-text-secondary hover:text-accent truncate ml-[4.75rem]"
                      title={latest.title}
                    >
                      {latest.title}
                    </a>
                  )}
                </li>
              );
            })}
          </ul>
        </Card>
      )}

      {/* Alerts */}
      <Card title="Alerts" contentClassName="px-5 py-4">
        {d.alerts.length === 0 ? (
          <span className="text-text-muted text-sm">No active alerts.</span>
        ) : (
          <ul className="space-y-2 text-sm">
            {d.alerts.map((a, i) => (
              <li key={i} className="flex items-start gap-3">
                <Badge
                  tone={
                    a.severity === 'critical'
                      ? 'negative'
                      : a.severity === 'warning'
                      ? 'warning'
                      : 'info'
                  }
                >
                  {a.code}
                </Badge>
                <span className="text-text-secondary">{a.message}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}


function Delta({
  label, value, valuePct, money = false,
}: {
  label: string;
  value: string | number | null;
  valuePct?: string | null;
  money?: boolean;
}) {
  if (value === null || value === undefined || value === '') {
    return (
      <Badge tone="muted">
        Δ {label}: —
      </Badge>
    );
  }
  const num_ = typeof value === 'number' ? value : Number(value);
  const positive = Number.isFinite(num_) && num_ > 0;
  const negative = Number.isFinite(num_) && num_ < 0;
  const tone = positive ? 'positive' : negative ? 'negative' : 'muted';
  const main = money
    ? formatSignedCurrency(value as string | null)
    : positive
    ? `+${num_}`
    : String(value);
  const pctPart = valuePct ? ` (${formatSignedPercent(valuePct)})` : '';
  return (
    <Badge tone={tone}>
      Δ {label}: <span className={pnlToneClass(String(num_))}>{main}{pctPart}</span>
    </Badge>
  );
}
