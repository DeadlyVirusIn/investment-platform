import { Link } from 'react-router-dom';
import Badge from '@/components/Badge';
import Card from '@/components/Card';
import PageHeader from '@/components/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '@/components/States';
import UpdatedLabel from '@/components/UpdatedLabel';
import { useDashboardSummary, useIntelligenceSummary } from '@/lib/hooks';

type Severity = 'info' | 'warn' | 'critical';
type Category =
  | 'portfolio'
  | 'signal'
  | 'regime'
  | 'data'
  | 'other';

interface RiskRow {
  id: string;
  category: Category;
  severity: Severity;
  title: string;
  detail: string;
  actionLabel?: string;
  actionHref?: string;
}

const CATEGORY_LABEL: Record<Category, string> = {
  portfolio: 'Portfolio risk',
  signal: 'Signal risk',
  regime: 'Regime risk',
  data: 'Data risk',
  other: 'Other',
};

function sevTone(s: Severity): 'info' | 'warning' | 'negative' {
  if (s === 'critical') return 'negative';
  if (s === 'warn') return 'warning';
  return 'info';
}

function humanizeFlag(code: string): string {
  return code.replace(/_/g, ' ');
}


export default function Alerts() {
  const dashQ = useDashboardSummary();
  const intelQ = useIntelligenceSummary();

  if (dashQ.isLoading || intelQ.isLoading) return <LoadingState />;
  if (dashQ.error) return <ErrorState message={String(dashQ.error)} />;
  if (intelQ.error) return <ErrorState message={String(intelQ.error)} />;

  const dash = dashQ.data;
  const intel = intelQ.data;

  const rows: RiskRow[] = buildRiskRows(dash, intel);
  const bySeverity = {
    critical: rows.filter(r => r.severity === 'critical'),
    warn: rows.filter(r => r.severity === 'warn'),
    info: rows.filter(r => r.severity === 'info'),
  };
  const total = rows.length;

  return (
    <>
      <PageHeader
        title="Risk Engine"
        subtitle={
          dash?.as_of_date
            ? `Default Paper — ${dash.as_of_date}`
            : 'Default Paper'
        }
        actions={<UpdatedLabel at={intelQ.dataUpdatedAt} />}
      />

      {total === 0 ? (
        <Card>
          <EmptyState
            title="System operating normally"
            hint="No active risks. Intelligence, portfolio, regime and data checks are all within thresholds."
          />
        </Card>
      ) : (
        <div className="space-y-4">
          {bySeverity.critical.length > 0 && (
            <Group label={`Critical (${bySeverity.critical.length})`} rows={bySeverity.critical} />
          )}
          {bySeverity.warn.length > 0 && (
            <Group label={`Warnings (${bySeverity.warn.length})`} rows={bySeverity.warn} />
          )}
          {bySeverity.info.length > 0 && (
            <Group label={`Info (${bySeverity.info.length})`} rows={bySeverity.info} />
          )}
        </div>
      )}
    </>
  );
}


function Group({ label, rows }: { label: string; rows: RiskRow[] }) {
  return (
    <Card title={label} contentClassName="px-5 py-4">
      <ul className="space-y-2">
        {rows.map(r => (
          <li
            key={r.id}
            className="flex items-start gap-3 border border-surface-border/50 rounded-md px-3 py-2"
          >
            <Badge tone={sevTone(r.severity)}>{r.severity}</Badge>
            <Badge tone="muted">{CATEGORY_LABEL[r.category]}</Badge>
            <div className="flex-1 min-w-0">
              <div className="text-sm text-text-primary font-medium">
                {r.title}
              </div>
              <div className="text-xs text-text-secondary mt-0.5">
                {r.detail}
              </div>
            </div>
            {r.actionHref && (
              <Link
                to={r.actionHref}
                className="text-xs text-accent hover:underline shrink-0"
              >
                {r.actionLabel ?? 'Open'} →
              </Link>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Row builder
// ---------------------------------------------------------------------------


function buildRiskRows(
  dash: import('@/types').DashboardSummary | undefined,
  intel: import('@/types').IntelligenceSummary | undefined,
): RiskRow[] {
  const out: RiskRow[] = [];

  // Dashboard alerts → data/regime
  for (const a of dash?.alerts ?? []) {
    const cat: Category =
      a.code === 'regime_missing'
        ? 'regime'
        : a.code === 'factors_missing' || a.code === 'high_slippage_day'
        ? 'data'
        : 'portfolio';
    out.push({
      id: `dash-${a.code}`,
      category: cat,
      severity:
        a.severity === 'critical' ? 'critical' : a.severity === 'warning' ? 'warn' : 'info',
      title: humanizeFlag(a.code),
      detail: a.message,
      actionHref: cat === 'regime' || cat === 'data' ? '/jobs-health' : '/portfolio',
      actionLabel: cat === 'regime' || cat === 'data' ? 'Jobs' : 'Portfolio',
    });
  }

  // Portfolio flags
  for (const f of intel?.portfolio?.flags ?? []) {
    const [code, ...rest] = f.split(':');
    out.push({
      id: `pf-${f}`,
      category: 'portfolio',
      severity: code.includes('drawdown') ? 'critical' : 'warn',
      title: humanizeFlag(code),
      detail: rest.length > 0 ? rest.join(':') : humanizeFlag(code),
      actionHref: '/portfolio',
      actionLabel: 'Portfolio',
    });
  }

  // Tuning advice → signal
  for (const s of intel?.tuning_advice?.suggestions ?? []) {
    if (s.code === 'no_action') continue;
    out.push({
      id: `tune-${s.code}`,
      category:
        s.code.includes('universe') || s.code.includes('concentration')
          ? 'portfolio'
          : 'signal',
      severity:
        s.severity === 'critical' ? 'critical' : s.severity === 'warn' ? 'warn' : 'info',
      title: s.message,
      detail: s.reasoning,
      actionHref: '/intelligence',
      actionLabel: 'Intel',
    });
  }

  // Decision quality red ribbon → signal risk
  const avb = intel?.decision_review?.accepted_vs_blocked;
  if (avb && avb.accepted_count >= 3) {
    const wr = avb.accepted_win_rate ? Number(avb.accepted_win_rate) : null;
    if (wr !== null && wr === 0) {
      out.push({
        id: 'sig-wr-zero',
        category: 'signal',
        severity: 'critical',
        title: 'Accepted win rate = 0%',
        detail: `${avb.accepted_count} trade(s) with no wins. Decision-quality verdict: weak.`,
        actionHref: '/intelligence',
        actionLabel: 'Intel',
      });
    }
  }

  // Regime risk — vol high with sma50 under sma200 would be flagged
  // (caught via dashboard alerts already). Nothing extra here.

  return out;
}
