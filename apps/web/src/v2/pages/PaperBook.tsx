// V2 Paper Book — practice portfolio detail.
//
// Phase A/B: reads the CANONICAL stock practice portfolio
// (useCanonicalStockPortfolio → /paper/canonical/stock) and REAL open
// positions (useExecutedPositions, scoped to the canonical portfolio_id).
// This is the same contract the homepage card reads, so the two can never
// disagree. The legacy localStorage PaperBook store is NO LONGER read here.
//
// Per-position P&L is now shown: the executed-positions contract was
// enriched (display-only) with current_price / previous_close and the
// derived market_value / day_pnl / unrealized_pnl. Values are null (rendered
// "—") whenever no price is available — we never fabricate a mark.

import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  useCanonicalStockPortfolio,
  useExecutedPositions,
  type ExecutedPosition,
} from '@/lib/operator/hooks';

function freshnessNote(f: string | undefined): string | null {
  switch (f) {
    case 'fresh': return null;
    case 'degraded': return 'Snapshot slightly delayed.';
    case 'stale': return 'Snapshot is stale — awaiting the next refresh.';
    case 'unknown': return 'Snapshot timing unavailable.';
    default: return null;
  }
}

// ── display-only formatters (null → "—"; never fabricated) ──
const fmtMoney = (v: number | null | undefined): string =>
  v == null ? '—'
    : `$${Math.abs(v).toLocaleString(undefined, {
        minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtSignedMoney = (v: number | null | undefined): string =>
  v == null ? '—'
    : `${v >= 0 ? '+' : '−'}$${Math.abs(v).toLocaleString(undefined, {
        minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtSignedPct = (v: number | null | undefined): string =>
  v == null ? '—' : `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(2)}%`;
const toneCls = (v: number | null | undefined): string =>
  v == null ? 'ink-primary' : v > 0 ? 'text-success' : v < 0 ? 'text-danger' : 'ink-primary';

export function PaperBook() {
  const { data: book, isLoading } = useCanonicalStockPortfolio();
  const portfolioId = book?.portfolio_id;
  const {
    data: posData, isLoading: posLoading, isError: posError,
  } = useExecutedPositions(false, true, portfolioId);
  const positions = posData?.positions ?? [];

  const nav = book?.nav ?? null;
  const cash = book?.cash ?? null;
  const unreal = book?.unrealized_pnl ?? null;
  const real = book?.realized_pnl ?? null;
  const ret = book?.total_return_pct ?? null;
  const note = freshnessNote(book?.freshness);

  return (
    <ArthosPage maxWidth="max-w-copy">
      <header className="mb-16 sm:mb-20">
        <MetaLabel>Your practice portfolio</MetaLabel>
        <h1 className="font-serif text-masthead ink-primary mt-3 mb-6 max-w-[18ch]">
          Practice portfolio.
        </h1>
        <p className="ink-muted leading-relaxed max-w-narrative">
          A real practice account tracked on the backend — the same numbers
          the briefing and homepage show. No real money. Follow the briefing,
          and see what holds up over time.
        </p>
      </header>

      <motion.section
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="mb-20"
      >
        <MetaLabel>Book value</MetaLabel>
        {nav == null ? (
          <p className="ink-muted leading-relaxed max-w-narrative text-[15px] mt-3">
            {isLoading
              ? 'Loading the practice account…'
              : 'Practice account is unavailable right now.'}
          </p>
        ) : (
          <>
            <div className="font-serif text-headline ink-primary tabular-nums mt-3 mb-3">
              $
              {nav.toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </div>
            <p className="ink-muted leading-relaxed max-w-narrative text-[15px]">
              Of which{' '}
              <span className="ink-primary tabular-nums">
                ${(cash ?? 0).toLocaleString(undefined, {
                  minimumFractionDigits: 2, maximumFractionDigits: 2,
                })}
              </span>{' '}
              is cash. Unrealized{' '}
              <span className="ink-primary tabular-nums">
                {(unreal ?? 0) >= 0 ? '+' : '−'}$
                {Math.abs(unreal ?? 0).toFixed(2)}
              </span>
              . Realized{' '}
              <span className="ink-primary tabular-nums">
                {(real ?? 0) >= 0 ? '+' : '−'}${Math.abs(real ?? 0).toFixed(2)}
              </span>{' '}
              to date.
              {ret != null && (
                <span className="ink-fainter ml-2">
                  {ret >= 0 ? '+' : '−'}{Math.abs(ret).toFixed(2)}% since inception.
                </span>
              )}
            </p>
            <p className="ink-fainter text-[12px] mt-2 tabular-nums">
              As of{' '}
              {book?.as_of
                ? new Date(book.as_of).toLocaleString(undefined, {
                    month: 'short', day: 'numeric',
                    hour: '2-digit', minute: '2-digit',
                  })
                : '—'}
              {' '}· source: {book?.source ?? 'live'}
            </p>
            {note && (
              <p className="ink-fainter text-[12px] mt-2">{note}</p>
            )}
          </>
        )}
      </motion.section>

      {/* ── Attribution summary — what's moving the book ── */}
      {positions.length > 0 && <AttributionSummary positions={positions} />}

      <section className="mb-20">
        <div className="flex items-baseline justify-between mb-8 flex-wrap gap-4">
          <MetaLabel>Open positions</MetaLabel>
          {positions.length > 0 && (
            <span className="text-meta ink-fainter">{positions.length} held</span>
          )}
        </div>

        {posError ? (
          <div className="border-t border-hairline pt-12 pb-2">
            <p className="ink-muted leading-relaxed max-w-narrative text-[15px]">
              Couldn't load your holdings right now. They'll reappear on the
              next refresh.
            </p>
          </div>
        ) : posLoading && positions.length === 0 ? (
          <div className="border-t border-hairline pt-12 pb-2">
            <p className="ink-muted leading-relaxed max-w-narrative text-[15px]">
              Loading your holdings…
            </p>
          </div>
        ) : positions.length === 0 ? (
          <div className="border-t border-hairline pt-12 pb-2">
            <p className="font-serif italic ink-muted text-[18px] leading-relaxed max-w-narrative mb-6">
              No open positions yet.
            </p>
            <p className="ink-muted leading-relaxed max-w-narrative mb-6 text-[15px]">
              The briefing publishes a fresh desk of placements every weekday.
            </p>
            <Link
              to="/v2/today"
              className="text-meta ink-primary hover:opacity-70 transition-opacity inline-flex items-center gap-1.5"
            >
              Open today's briefing <span aria-hidden>→</span>
            </Link>
          </div>
        ) : (
          <ul className="space-y-px bg-hairline">
            {positions.map((p) => (
              <PositionRow key={p.position_id} position={p} />
            ))}
          </ul>
        )}
      </section>
    </ArthosPage>
  );
}

// ── per-holding attribution card ──
function Metric({ label, value, tone }: {
  label: string; value: string; tone?: string;
}) {
  return (
    <div className="min-w-0">
      <div className="text-meta ink-fainter mb-0.5">{label}</div>
      <div className={`tabular-nums text-[13px] ${tone ?? 'ink-primary'}`}>{value}</div>
    </div>
  );
}

function PositionRow({ position }: { position: ExecutedPosition }) {
  const qty = position.quantity ?? 0;
  const units = Math.abs(qty) === 1 ? 'share' : 'shares';
  const opened = position.opened_at
    ? new Date(position.opened_at).toLocaleDateString('en-US', {
        month: 'short', day: 'numeric',
      })
    : '—';
  const holdStatus = position.is_open ? 'Held' : 'Closed';
  return (
    <li className="surface-base py-6">
      <div className="flex items-baseline gap-3 mb-3 flex-wrap">
        <span className="font-mono ink-primary text-[14px]">{position.symbol}</span>
        <span className="text-meta ink-fainter">{qty} {units}</span>
        <span className="text-meta ink-fainter">· {holdStatus}</span>
        {position.source !== 'live' && (
          <span className="text-meta ink-fainter">· {position.source}</span>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-4">
        <Metric label="Avg cost" value={fmtMoney(position.avg_cost)} />
        <Metric label="Current" value={fmtMoney(position.current_price)} />
        <Metric label="Mkt value" value={fmtMoney(position.market_value)} />
        <Metric label="Day P&L"
          value={position.day_pnl == null ? '—'
            : `${fmtSignedMoney(position.day_pnl)} · ${fmtSignedPct(position.day_pnl_pct)}`}
          tone={toneCls(position.day_pnl)} />
        <Metric label="Unrealized"
          value={position.unrealized_pnl == null ? '—'
            : `${fmtSignedMoney(position.unrealized_pnl)} · ${fmtSignedPct(position.unrealized_pnl_pct)}`}
          tone={toneCls(position.unrealized_pnl)} />
        <Metric label="Total return"
          value={fmtSignedPct(position.total_return_pct)}
          tone={toneCls(position.total_return_pct)} />
        <Metric label="Opened" value={opened} />
      </div>
    </li>
  );
}

// ── ranked attribution lists (top movers today + biggest unrealized) ──
function rankLine(p: ExecutedPosition, metric: 'day' | 'unreal'): string {
  const v = metric === 'day' ? p.day_pnl : p.unrealized_pnl;
  const pct = metric === 'day' ? p.day_pnl_pct : p.unrealized_pnl_pct;
  return `${fmtSignedMoney(v)} · ${fmtSignedPct(pct)}`;
}

function RankCard({ title, rows, metric }: {
  title: string;
  rows: ExecutedPosition[];
  metric: 'day' | 'unreal';
}) {
  return (
    <div>
      <div className="text-meta ink-fainter mb-3">{title}</div>
      {rows.length === 0 ? (
        <p className="ink-fainter text-[13px]">No priced holdings.</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((p) => {
            const v = metric === 'day' ? p.day_pnl : p.unrealized_pnl;
            return (
              <li key={p.position_id} className="flex items-baseline justify-between gap-3">
                <span className="font-mono ink-primary text-[13px]">{p.symbol}</span>
                <span className={`tabular-nums text-[13px] ${toneCls(v)}`}>
                  {rankLine(p, metric)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function AttributionSummary({ positions }: { positions: ExecutedPosition[] }) {
  const dayPriced = positions.filter((p) => p.day_pnl != null);
  const unrealPriced = positions.filter((p) => p.unrealized_pnl != null);
  const byDay = [...dayPriced].sort((a, b) => (b.day_pnl ?? 0) - (a.day_pnl ?? 0));
  const byUnreal = [...unrealPriced].sort(
    (a, b) => (b.unrealized_pnl ?? 0) - (a.unrealized_pnl ?? 0));

  const topWinnersToday = byDay.filter((p) => (p.day_pnl ?? 0) > 0).slice(0, 5);
  const topLosersToday = byDay.filter((p) => (p.day_pnl ?? 0) < 0).slice(-5).reverse();
  const topUnrealWinners = byUnreal.filter((p) => (p.unrealized_pnl ?? 0) > 0).slice(0, 5);
  const topUnrealLosers = byUnreal.filter((p) => (p.unrealized_pnl ?? 0) < 0).slice(-5).reverse();

  // Nothing priced yet → don't render an empty/fabricated panel.
  if (dayPriced.length === 0 && unrealPriced.length === 0) return null;

  return (
    <section className="mb-20">
      <MetaLabel>What's moving the book</MetaLabel>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-10 gap-y-8 mt-6">
        <RankCard title="Top winners today" rows={topWinnersToday} metric="day" />
        <RankCard title="Top losers today" rows={topLosersToday} metric="day" />
        <RankCard title="Largest unrealized winners" rows={topUnrealWinners} metric="unreal" />
        <RankCard title="Largest unrealized losers" rows={topUnrealLosers} metric="unreal" />
      </div>
    </section>
  );
}
