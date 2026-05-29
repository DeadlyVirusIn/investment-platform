// V2 Paper Book — practice portfolio detail.
//
// Phase A/B: reads the CANONICAL stock practice portfolio
// (useCanonicalStockPortfolio → /paper/canonical/stock) and REAL open
// positions (useExecutedPositions, scoped to the canonical portfolio_id).
// This is the same contract the homepage card reads, so the two can never
// disagree. The legacy localStorage PaperBook store is NO LONGER read
// here (full removal of the store file is Phase C).
//
// Read-only surface: no close/reset write actions (backend is the source
// of truth; mutations are out of scope for this phase). Per-position live
// P&L is not shown because the executed-positions contract exposes cost
// basis only — we never fabricate a mark.

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

export function PaperBook() {
  const { data: book, isLoading } = useCanonicalStockPortfolio();
  const portfolioId = book?.portfolio_id;
  const { data: posData } = useExecutedPositions(false, true, portfolioId);
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

      <section className="mb-20">
        <div className="flex items-baseline justify-between mb-8 flex-wrap gap-4">
          <MetaLabel>Open positions</MetaLabel>
          {positions.length > 0 && (
            <span className="text-meta ink-fainter">{positions.length} held</span>
          )}
        </div>

        {positions.length === 0 ? (
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

function PositionRow({ position }: { position: ExecutedPosition }) {
  const qty = position.quantity ?? 0;
  const units = Math.abs(qty) === 1 ? 'share' : 'shares';
  const opened = position.opened_at
    ? new Date(position.opened_at).toLocaleDateString('en-US', {
        month: 'short', day: 'numeric',
      })
    : '—';
  return (
    <li className="surface-base py-6">
      <div className="flex items-baseline justify-between gap-4 flex-wrap mb-1.5">
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-3 mb-1.5 flex-wrap">
            <span className="font-mono ink-primary text-[14px]">
              {position.symbol}
            </span>
            <span className="text-meta ink-fainter">
              {qty} {units}
            </span>
            {position.source !== 'live' && (
              <span className="text-meta ink-fainter">· {position.source}</span>
            )}
          </div>
          <div className="text-meta ink-fainter tabular-nums">
            Avg cost{' '}
            {position.avg_cost != null ? `$${position.avg_cost.toFixed(2)}` : '—'}
            {' '}· opened {opened}
          </div>
        </div>
      </div>
    </li>
  );
}
