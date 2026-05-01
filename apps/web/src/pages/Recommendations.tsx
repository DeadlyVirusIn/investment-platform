import { useMemo, useState } from 'react';
import Badge, { actionTone } from '@/components/Badge';
import ResearchIntelligenceTab from '@/components/research/ResearchIntelligenceTab';
import Card from '@/components/Card';
import PageHeader from '@/components/PageHeader';
import Table, { type Column } from '@/components/Table';
import { EmptyState, ErrorState, LoadingState } from '@/components/States';
import UpdatedLabel from '@/components/UpdatedLabel';
import {
  useIntelligenceSummary,
  useNewsSummaryBatch,
  useRejectionSummary,
  useStockCandidates,
} from '@/lib/hooks';
import { NewsSummaryBadges } from '@/components/NewsBadges';
import DecisionQualityRibbon from '@/components/DecisionQualityRibbon';
import FactorContribBar, { parseContributions } from '@/components/FactorContribBar';
import { formatRatio } from '@/lib/format';
import type { StockCandidate } from '@/types';

// --- Conviction tier helper ---

function convictionTier(
  composite: string | null, confidence: string | null,
): 'S' | 'A' | 'B' {
  const c = composite ? Number(composite) : 0;
  const f = confidence ? Number(confidence) : 0;
  if (c >= 0.45 && f >= 70) return 'S';
  if (c >= 0.35 && f >= 60) return 'A';
  return 'B';
}

function tierTone(t: 'S' | 'A' | 'B'): 'positive' | 'info' | 'muted' {
  if (t === 'S') return 'positive';
  if (t === 'A') return 'info';
  return 'muted';
}

// Map a composite score to its intelligence bucket stats (win rate)
function bucketForScore(
  composite: string | null,
  intel: import('@/types').IntelligenceSummary | undefined,
): { label: string; wins: number; n: number; wr: number } | null {
  if (!intel || !composite) return null;
  const c = Number(composite);
  if (!Number.isFinite(c)) return null;
  const label =
    c >= 0.45 ? '0.45+' : c >= 0.35 ? '0.35-0.45' : c >= 0.25 ? '0.25-0.35' : null;
  if (!label) return null;
  const b = intel.decision_review?.bucket_performance?.find(
    x => x.bucket === label,
  );
  if (!b || b.trade_count === 0) return null;
  return {
    label,
    wins: b.wins,
    n: b.trade_count,
    wr: b.trade_count > 0 ? b.wins / b.trade_count : 0,
  };
}

type Filter = 'all' | 'accepted' | 'rejected';

const TOPN_FULL = 10;
const TOPN_HIGHVOL = 3;

// ---------------------------------------------------------------------------
// Human-readable labels
// ---------------------------------------------------------------------------


const REJECTION_LABELS: Record<string, string> = {
  regime_off: 'Regime off (downtrend / missing)',
  not_in_universe: 'Not in active universe',
  insufficient_history: 'Insufficient price history',
  stale_data: 'Stale price data',
  liquidity_fail: 'Below liquidity floor',
  earnings_too_close: 'Earnings within 5 days',
  below_long_trend: 'Below long-term trend (SMA200)',
  idiosyncratic_vol_high: 'Idiosyncratic volatility too high',
  already_at_cap: 'Already at position cap',
  topn_overflow: 'Below daily Top-N cutoff',
  high_vol_topn_overflow: 'Not selected in high-vol Top-3',
  job_error: 'Evaluation failed',
};

function prettyRejection(code: string | null): string {
  if (!code) return '—';
  return REJECTION_LABELS[code] ?? code;
}


// ---------------------------------------------------------------------------
// Explainability — "Why recommended" tags
// ---------------------------------------------------------------------------


interface ExplainCtx {
  /** 1-based rank among accepted Buys */
  buyRank: number | null;
  /** Top Buy's composite (for "leader gap" tags on Holds) */
  topBuyComposite: number | null;
  /** vol_regime parsed from candidate.regime_snapshot */
  volRegime: string | null;
  marketTrend: string | null;
  /** Highest composite seen today across accepted Buys */
}


function regimeFromCandidate(c: StockCandidate): { trend: string | null; vol: string | null } {
  const reg = c.regime_snapshot as Record<string, unknown> | null | undefined;
  return {
    trend: (reg?.market_trend as string | undefined) ?? null,
    vol: (reg?.vol_regime as string | undefined) ?? null,
  };
}


function num(v: string | null | undefined): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}


function explainBuy(c: StockCandidate, ctx: ExplainCtx): string[] {
  const tags: string[] = [];
  const score = num(c.composite_score) ?? 0;
  const conf = num(c.confidence) ?? 0;

  if (ctx.volRegime === 'high') {
    tags.push(`Top ${TOPN_HIGHVOL} under high-vol rule`);
  } else if (ctx.buyRank != null && ctx.buyRank <= 3) {
    tags.push(`Top ${ctx.buyRank} rank today`);
  } else if (ctx.buyRank != null) {
    tags.push(`Rank ${ctx.buyRank} of Top ${TOPN_FULL}`);
  }

  if (score >= 0.45) tags.push('Strong composite (≥0.45)');
  else if (score >= 0.35) tags.push('Solid composite (≥0.35)');

  if (conf >= 75) tags.push('High confidence');
  else if (conf >= 60) tags.push('Medium confidence');

  if (ctx.marketTrend === 'uptrend') tags.push('Aligned with uptrend');

  // Sector rank hint from factor_breakdown values (if present)
  const values = (c.factor_breakdown as Record<string, unknown> | undefined)?.values as
    | Record<string, string | null>
    | undefined;
  const sectorRank = values?.sector_relative_rank
    ? Number(values.sector_relative_rank)
    : null;
  if (sectorRank != null && sectorRank >= 0.75) {
    tags.push('Sector leader (rank ≥ 0.75)');
  }
  const price200 = values?.price_vs_200sma
    ? Number(values.price_vs_200sma)
    : null;
  if (price200 != null && price200 > 0) {
    tags.push('Above long-term trend');
  }

  return tags;
}


function explainHold(c: StockCandidate, ctx: ExplainCtx): string[] {
  const tags: string[] = [];
  const score = num(c.composite_score);
  const topScore = ctx.topBuyComposite;

  if (c.rejection_reason === 'topn_overflow') {
    tags.push('Below Top-N cutoff');
  }
  if (score != null && topScore != null && score < topScore) {
    const gap = (topScore - score).toFixed(3);
    tags.push(`Weaker composite vs leader (Δ ${gap})`);
  } else if (score != null && score < 0.25) {
    tags.push('Composite below Buy threshold (0.25)');
  }

  const values = (c.factor_breakdown as Record<string, unknown> | undefined)?.values as
    | Record<string, string | null>
    | undefined;
  const price200 = values?.price_vs_200sma
    ? Number(values.price_vs_200sma)
    : null;
  if (price200 != null && price200 < 0) {
    tags.push('Price below SMA200');
  }

  if (tags.length === 0) tags.push('Held — no dominant signal');
  return tags;
}


// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------


export default function Recommendations() {
  const [filter, setFilter] = useState<Filter>('all');

  const q = useStockCandidates({
    status: filter === 'all' ? undefined : filter,
    limit: 200,
  });
  const rej = useRejectionSummary();
  const intelQ = useIntelligenceSummary();

  // Derive candidates + ranked buys BEFORE any early return so every
  // downstream hook runs in a stable order.
  const cands = q.data?.candidates ?? [];
  const acceptedBuys = cands.filter(
    c => c.status === 'accepted' && c.action === 'Buy' && !c.rejection_reason,
  );
  const rejects = cands.filter(c => c.status === 'rejected');
  const otherAccepted = cands.filter(
    c => c.status === 'accepted' && c.action && c.action !== 'Buy',
  );

  const rankedBuys = useMemo(() => {
    return [...acceptedBuys].sort((a, b) => {
      const sa = num(a.composite_score) ?? -Infinity;
      const sb = num(b.composite_score) ?? -Infinity;
      return sb - sa;
    });
  }, [acceptedBuys]);

  const topBuySymbols = useMemo(
    () =>
      rankedBuys
        .slice(0, 6)
        .map(c => c.symbol)
        .filter((s): s is string => !!s),
    [rankedBuys],
  );
  const newsQ = useNewsSummaryBatch(topBuySymbols, 7);

  if (q.isLoading) return <LoadingState />;
  if (q.error) return <ErrorState message={String(q.error)} />;

  const topBuyComposite = num(rankedBuys[0]?.composite_score ?? null);
  const firstRegime =
    cands.length > 0 ? regimeFromCandidate(cands[0]) : { trend: null, vol: null };

  const buyRankById = new Map<string, number>();
  rankedBuys.forEach((c, i) => buyRankById.set(c.id, i + 1));

  const newsBySymbol = newsQ.data?.summaries ?? {};

  const explainCtxBase: Omit<ExplainCtx, 'buyRank'> = {
    topBuyComposite,
    volRegime: firstRegime.vol,
    marketTrend: firstRegime.trend,
  };

  return (
    <>
      <PageHeader
        title="Recommendations"
        subtitle={
          q.data?.as_of_date
            ? `Stock-swing candidates — ${q.data.as_of_date}`
            : 'Stock-swing candidates'
        }
        actions={
          <div className="flex items-center gap-3">
            <UpdatedLabel at={q.dataUpdatedAt} />
            <select
              value={filter}
              onChange={e => setFilter(e.target.value as Filter)}
              className="bg-surface-card border border-surface-border rounded-md text-sm px-3 py-1.5 text-text-primary"
            >
              <option value="all">All</option>
              <option value="accepted">Accepted only</option>
              <option value="rejected">Rejected only</option>
            </select>
          </div>
        }
      />

      <DecisionQualityRibbon intelligence={intelQ.data} className="mb-4" />

      {(() => {
        const hvOverflow = rej.data?.reasons?.high_vol_topn_overflow ?? 0;
        if (hvOverflow > 0) {
          return (
            <Card className="mb-4" contentClassName="px-5 py-3">
              <div className="text-sm text-warning">
                High-vol regime cap active — only top 3 Buys surfaced.{' '}
                <span className="text-text-muted">
                  {hvOverflow} candidate(s) with sufficient score rejected as{' '}
                  <code>high_vol_topn_overflow</code>.
                </span>
              </div>
            </Card>
          );
        }
        return null;
      })()}

      {cands.length === 0 ? (
        <Card>
          <EmptyState
            title="No candidates for this date"
            hint={
              rej.data && rej.data.total_evaluated === 0 ? (
                <>
                  The stock engine has not produced candidates yet. Trigger{' '}
                  <code className="text-text-secondary">
                    POST /api/jobs/generate_stock_candidates/run
                  </code>{' '}
                  after ingestion + regime + factor jobs.
                </>
              ) : (
                <>Stock engine idle for the selected date.</>
              )
            }
          />
        </Card>
      ) : (
        <>
          {acceptedBuys.length === 0 && rej.data && (
            <Card title="Why no Buys today?" className="mb-6">
              <p className="text-sm text-text-secondary mb-3">
                {rej.data.rejected} of {rej.data.total_evaluated} candidates were
                rejected.
              </p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(rej.data.reasons)
                  .sort(([, a], [, b]) => b - a)
                  .map(([reason, count]) => (
                    <Badge key={reason} tone="warning">
                      {prettyRejection(reason)}: {count}
                    </Badge>
                  ))}
              </div>
            </Card>
          )}

          <Card
            title={`Accepted Buys (${acceptedBuys.length})`}
            className="mb-6"
            contentClassName="p-0"
          >
            {acceptedBuys.length === 0 ? (
              <EmptyState title="No accepted Buy candidates" />
            ) : (
              <>
                <Table<StockCandidate>
                  rows={rankedBuys}
                  rowKey={r => r.id}
                  columns={BUY_COLUMNS}
                />
                <div className="px-5 py-4 border-t border-surface-border space-y-4">
                  {rankedBuys.slice(0, 6).map(c => {
                    const tags = explainBuy(c, {
                      ...explainCtxBase,
                      buyRank: buyRankById.get(c.id) ?? null,
                    });
                    const sym = c.symbol ?? '';
                    const newsSummary = sym ? newsBySymbol[sym] : null;
                    const latest = newsSummary?.latest ?? null;
                    const tier = convictionTier(c.composite_score, c.confidence);
                    const contribs = parseContributions(c.factor_breakdown);
                    const bucketStats = bucketForScore(
                      c.composite_score, intelQ.data,
                    );
                    return (
                      <div key={`exp-${c.id}`} className="space-y-1.5">
                        <div className="flex items-start gap-3">
                          <div className="w-20 font-medium text-sm flex items-center gap-2">
                            {sym || '—'}
                            <Badge tone={tierTone(tier)}>{tier}</Badge>
                          </div>
                          <div className="flex-1 flex flex-wrap gap-1.5">
                            {tags.map((t, i) => (
                              <Badge key={`${c.id}-${i}`} tone="positive">
                                {t}
                              </Badge>
                            ))}
                            {bucketStats && (
                              <Badge
                                tone={
                                  bucketStats.wr === 0 && bucketStats.n >= 3
                                    ? 'negative'
                                    : bucketStats.wr >= 0.5
                                    ? 'positive'
                                    : 'muted'
                                }
                              >
                                {bucketStats.label}: {bucketStats.wins}/{bucketStats.n} wins
                              </Badge>
                            )}
                          </div>
                        </div>
                        {contribs && (
                          <div className="pl-[5.25rem]">
                            <FactorContribBar contributions={contribs} />
                          </div>
                        )}
                        {sym && (
                          <div className="flex items-center gap-3 pl-[5.25rem]">
                            <span className="text-[10px] uppercase tracking-wider text-text-muted w-14">
                              News
                            </span>
                            <div className="flex-1 min-w-0">
                              <NewsSummaryBadges summary={newsSummary} />
                              {latest && (
                                <a
                                  href={latest.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="block text-xs text-text-secondary hover:text-accent truncate mt-1"
                                  title={latest.title}
                                >
                                  {latest.title}
                                </a>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </Card>

          {otherAccepted.length > 0 && (
            <Card
              title={`Other accepted (${otherAccepted.length})`}
              className="mb-6"
              contentClassName="p-0"
            >
              <Table<StockCandidate>
                rows={otherAccepted}
                rowKey={r => r.id}
                columns={BUY_COLUMNS}
              />
              <div className="px-5 py-4 border-t border-surface-border space-y-3">
                {otherAccepted.slice(0, 8).map(c => {
                  const tags = explainHold(c, {
                    ...explainCtxBase,
                    buyRank: null,
                  });
                  return (
                    <div key={`exph-${c.id}`} className="flex items-start gap-3">
                      <div className="w-20 font-medium text-sm">
                        {c.symbol ?? '—'} <Badge tone="muted">{c.action}</Badge>
                      </div>
                      <div className="flex-1 flex flex-wrap gap-1.5">
                        {tags.map((t, i) => (
                          <Badge key={`${c.id}-${i}`} tone="muted">
                            {t}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          )}

          <Card
            title={`Rejections (${rejects.length})`}
            contentClassName="p-0"
          >
            {rejects.length === 0 ? (
              <EmptyState title="No rejections" />
            ) : (
              <Table<StockCandidate>
                rows={rejects}
                rowKey={r => r.id}
                columns={REJECT_COLUMNS}
              />
            )}
          </Card>
        </>
      )}

      {/*
        Phase 11W (Phase B) — Research Intelligence tab. Mounted only
        when VITE_RESEARCH_RO_ENABLED === 'true'. Phase B = empty
        state shell with mandatory banner.
      */}
      {import.meta.env.VITE_RESEARCH_RO_ENABLED === 'true' && (
        <Card title="Research Intelligence (read-only)" className="mt-6">
          <ResearchIntelligenceTab />
        </Card>
      )}
    </>
  );
}


// ---------------------------------------------------------------------------
// Columns
// ---------------------------------------------------------------------------


const BUY_COLUMNS: Column<StockCandidate>[] = [
  {
    key: 'sym', label: 'Symbol',
    render: r => <span className="font-medium">{r.symbol ?? '—'}</span>,
  },
  {
    key: 'act', label: 'Action',
    render: r => (
      <Badge tone={actionTone(r.action ?? 'Hold')}>{r.action ?? '—'}</Badge>
    ),
  },
  {
    key: 'composite', label: 'Composite', align: 'right',
    render: r => (
      <span className="font-mono tabular-nums">
        {formatRatio(r.composite_score, 3)}
      </span>
    ),
  },
  {
    key: 'conf', label: 'Confidence', align: 'right',
    render: r => (
      <span className="font-mono tabular-nums">
        {formatRatio(r.confidence, 1)}
      </span>
    ),
  },
  {
    key: 'trend', label: 'Regime',
    render: r => {
      const { trend, vol } = regimeFromCandidate(r);
      return (
        <span className="text-xs text-text-muted">
          {trend ?? '—'} · {vol ?? '—'}
        </span>
      );
    },
  },
];

const REJECT_COLUMNS: Column<StockCandidate>[] = [
  {
    key: 'sym', label: 'Symbol',
    render: r => <span className="font-medium">{r.symbol ?? '—'}</span>,
  },
  {
    key: 'reason', label: 'Reason',
    render: r => (
      <Badge tone="warning">{prettyRejection(r.rejection_reason)}</Badge>
    ),
  },
  {
    key: 'composite', label: 'Composite', align: 'right',
    render: r => (
      <span className="font-mono tabular-nums">
        {formatRatio(r.composite_score, 3)}
      </span>
    ),
  },
  {
    key: 'conf', label: 'Confidence', align: 'right',
    render: r => (
      <span className="font-mono tabular-nums">
        {formatRatio(r.confidence, 1)}
      </span>
    ),
  },
];
