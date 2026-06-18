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
import { CompanyTitle } from '../components/CompanyTitle';
import { PracticeTabs } from './components/PracticeTabs';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  useCanonicalStockPortfolio,
  useExecutedPositions,
  type ExecutedPosition,
  type CanonicalStockPortfolio,
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
          This is your <strong>paper portfolio</strong> — practice money, nothing
          real at risk. Every idea you follow or add is tracked here with live
          prices, so you can see what actually holds up before you ever invest
          real money.
        </p>
      </header>

      <PracticeTabs />

      <motion.section
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="mb-20"
      >
        <MetaLabel>Book value</MetaLabel>
        {nav == null ? (
          isLoading ? (
            <p className="ink-muted leading-relaxed max-w-narrative text-[15px] mt-3">
              Loading the practice account…
            </p>
          ) : (book?.open_positions_count ?? 0) > 0 || positions.length > 0 ? (
            // Positions exist but no NAV snapshot yet (status=no_live_snapshot).
            // NEVER say "unavailable" here — the user's add succeeded.
            <div className="mt-3 max-w-narrative">
              <div className="flex items-center gap-2 mb-3 flex-wrap">
                <span className="px-2.5 py-0.5 rounded-full font-semibold uppercase"
                  style={{ fontSize: 10.5, letterSpacing: '0.1em',
                    backgroundColor: 'color-mix(in oklch, var(--brand) 12%, transparent)',
                    color: 'var(--brand)',
                    border: '1px solid color-mix(in oklch, var(--brand) 26%, transparent)' }}>
                  Practice money
                </span>
                <span className="ink-muted text-[13px]">
                  {(book?.open_positions_count ?? positions.length)} open position
                  {(book?.open_positions_count ?? positions.length) === 1 ? '' : 's'}
                </span>
              </div>
              <p className="font-serif text-subhead ink-primary leading-snug">
                Your practice portfolio is being prepared
              </p>
              <p className="ink-muted leading-relaxed text-[15px] mt-2">
                You've already added ideas to your practice account. Prices and
                portfolio values update with the next market snapshot.
              </p>
            </div>
          ) : (
            <p className="ink-muted leading-relaxed max-w-narrative text-[15px] mt-3">
              No practice positions yet — add an idea from Discover to start your
              practice book.
            </p>
          )
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
            {/* P1.2 — honest negative-cash narrative. Conditional copy only;
                no calculations touched. Self-removes once cash recovers. */}
            {(cash ?? 0) < 0 && (
              <p className="ink-muted leading-relaxed max-w-narrative text-[13px] mt-3">
                Cash is negative after a ledger correction on Jun 12. Arth
                pauses new buys until sales rebuild cash; your book value is
                unaffected.
              </p>
            )}
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

      {/* ── P&L explanation — reconcile the headline day P&L honestly ── */}
      {nav != null && book && (
        <PnlExplanation book={book} positions={positions} />
      )}

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
              Your portfolio is empty — let's fix that.
            </p>
            <p className="ink-muted leading-relaxed max-w-narrative mb-6 text-[15px]">
              Follow a model portfolio or add a single idea to paper. It starts
              tracking immediately and becomes your track record.
            </p>
            <div className="flex flex-wrap items-center gap-5">
              <Link
                to="/v2/discover"
                className="px-4 py-2 rounded-full inline-flex items-center gap-1.5"
                style={{ fontSize: 13, fontWeight: 600, color: 'var(--background)', backgroundColor: 'var(--brand)' }}
              >
                Browse ideas <span aria-hidden>→</span>
              </Link>
              <Link to="/v2/track-record" className="text-meta ink-muted hover:ink-primary transition-colors">
                See track record →
              </Link>
            </div>
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
        <CompanyTitle symbol={position.symbol} className="ink-primary text-[14px]" />
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
                <CompanyTitle symbol={p.symbol} className="ink-primary text-[13px]" />
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

// ── honest P&L reconciliation: today's holding move vs since-snapshot delta ──
function PnlExplanation({ book, positions }: {
  book: CanonicalStockPortfolio;
  positions: ExecutedPosition[];
}) {
  const priced = positions.filter((p) => p.day_pnl != null);
  const holdingMove = priced.reduce((a, p) => a + (p.day_pnl ?? 0), 0);
  const snapPnl = book.daily_pnl ?? null;
  const priorDate = book.daily_pnl_prior_snapshot_date ?? null;
  const asOf = book.as_of ? new Date(book.as_of) : null;
  const prior = priorDate ? new Date(priorDate) : null;
  const spanDays = asOf && prior
    ? Math.round((asOf.getTime() - prior.getTime()) / 86_400_000) : null;
  const multiDay = spanDays != null && spanDays > 1;
  const fmtDate = (d: string | null) => d
    ? new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    : 'the last snapshot';

  return (
    <section className="mb-20">
      <MetaLabel>Where the P&amp;L comes from</MetaLabel>
      <ul className="mt-6 space-y-3 max-w-narrative">
        <li className="flex items-baseline justify-between gap-4">
          <span className="ink-muted text-[14px]">
            Today's holding move
            <span className="ink-fainter text-[12px] ml-2">
              {priced.length}/{positions.length} priced
            </span>
          </span>
          <span className={`tabular-nums text-[14px] ${toneCls(holdingMove)}`}>
            {priced.length === 0 ? '—' : fmtSignedMoney(holdingMove)}
          </span>
        </li>
        <li className="flex items-baseline justify-between gap-4">
          <span className="ink-muted text-[14px]">Open unrealized (cost vs current)</span>
          <span className={`tabular-nums text-[14px] ${toneCls(book.unrealized_pnl)}`}>
            {fmtSignedMoney(book.unrealized_pnl)}
          </span>
        </li>
        <li className="flex items-baseline justify-between gap-4 border-t border-hairline pt-3">
          <span className="ink-muted text-[14px]">
            Account change since {fmtDate(priorDate)}
            {multiDay && (
              <span className="ink-fainter text-[12px] ml-2">spans {spanDays} days</span>
            )}
          </span>
          <span className={`tabular-nums text-[14px] ${toneCls(snapPnl)}`}>
            {fmtSignedMoney(snapPnl)}
          </span>
        </li>
      </ul>
      <p className="ink-fainter text-[12px] mt-4 max-w-narrative leading-relaxed">
        The headline “day P&amp;L” is the account-equity change since{' '}
        {fmtDate(priorDate)}
        {multiDay ? ` — ${spanDays} days, not a single session` : ''}. It includes
        realized trades, cash moves, and positions opened or closed, so it won't
        equal today's open-holding move above.
      </p>
    </section>
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
