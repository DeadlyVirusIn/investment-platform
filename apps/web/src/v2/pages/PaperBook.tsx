// V2 Paper Book — formerly Portfolio. $100k virtual cash, open
// positions, closed history, reset.

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import {
  usePaperBook,
  pnlForPosition,
  pnlPctForPosition,
  type PaperPosition,
} from '../state/PaperBook';

export function PaperBook() {
  const {
    cash,
    positions,
    history,
    startingCash,
    bookValue,
    unrealizedPnL,
    realizedPnL,
    closePosition,
    resetBook,
  } = usePaperBook();
  const [confirmReset, setConfirmReset] = useState(false);
  const lifetimePct = ((bookValue - startingCash) / startingCash) * 100;

  return (
    <ArthosPage maxWidth="max-w-copy">
      <header className="mb-16 sm:mb-20">
        <MetaLabel>Your paper book</MetaLabel>
        <h1 className="font-serif text-masthead ink-primary mt-3 mb-6 max-w-[18ch]">
          Paper book.
        </h1>
        <p className="ink-muted leading-relaxed max-w-narrative">
          One hundred thousand in virtual cash. No real money. Use it to
          follow along with the briefing, place your own ideas, and see what
          holds up over time.
        </p>
      </header>

      <motion.section
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="mb-20"
      >
        <MetaLabel>Book value</MetaLabel>
        <div className="font-serif text-headline ink-primary tabular-nums mt-3 mb-3">
          $
          {bookValue.toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          })}
        </div>
        <p className="ink-muted leading-relaxed max-w-narrative text-[15px]">
          Of which{' '}
          <span className="ink-primary tabular-nums">
            $
            {cash.toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>{' '}
          is cash. Unrealized{' '}
          <span className="ink-primary tabular-nums">
            {unrealizedPnL >= 0 ? '+' : '−'}$
            {Math.abs(unrealizedPnL).toFixed(2)}
          </span>
          . Realized{' '}
          <span className="ink-primary tabular-nums">
            {realizedPnL >= 0 ? '+' : '−'}${Math.abs(realizedPnL).toFixed(2)}
          </span>{' '}
          to date.
          <span className="ink-fainter ml-2">
            {lifetimePct >= 0 ? '+' : '−'}
            {Math.abs(lifetimePct).toFixed(2)}% since Day 1.
          </span>
        </p>
      </motion.section>

      <section className="mb-20">
        <div className="flex items-baseline justify-between mb-8 flex-wrap gap-4">
          <MetaLabel>Open positions</MetaLabel>
          {positions.length > 0 && (
            <span className="text-meta ink-fainter">
              {positions.length} held
            </span>
          )}
        </div>

        {positions.length === 0 ? (
          <div className="border-t border-hairline pt-12 pb-2">
            <p className="font-serif italic ink-muted text-[18px] leading-relaxed max-w-narrative mb-6">
              No open positions yet.
            </p>
            <p className="ink-muted leading-relaxed max-w-narrative mb-6 text-[15px]">
              The briefing publishes a fresh desk of placements every weekday.
              You can paper any of them with one tap.
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
              <PositionRow
                key={p.id}
                position={p}
                onClose={() => closePosition(p.id)}
              />
            ))}
          </ul>
        )}
      </section>

      {history.length > 0 && (
        <section className="mb-20">
          <MetaLabel>Closed</MetaLabel>
          <ul className="mt-8 space-y-px bg-hairline">
            {history.map((h) => (
              <li
                key={h.id}
                className="surface-base py-5 flex items-baseline justify-between gap-4 flex-wrap"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-3 mb-1">
                    <span className="font-mono ink-primary text-[14px]">
                      {h.symbol}
                    </span>
                    <span className="ink-muted text-[13px] truncate">
                      {h.actionLabel}
                    </span>
                  </div>
                  <div className="text-meta ink-fainter tabular-nums">
                    {new Date(h.closedAt).toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                    })}{' '}
                    · {h.daysHeld} {h.daysHeld === 1 ? 'day' : 'days'} held
                  </div>
                </div>
                <div className="text-right tabular-nums shrink-0">
                  <div className="ink-primary text-[14px]">
                    <span className="mr-1">{h.pnl >= 0 ? '▲' : '▼'}</span>
                    {h.pnl >= 0 ? '+' : '−'}${Math.abs(h.pnl).toFixed(2)}
                  </div>
                  <div className="text-meta ink-fainter mt-1">
                    {h.pnlPct >= 0 ? '+' : '−'}
                    {Math.abs(h.pnlPct).toFixed(2)}%
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="border-t border-hairline pt-12">
        {!confirmReset ? (
          <>
            <p className="font-serif italic ink-muted text-[17px] leading-relaxed max-w-narrative mb-5">
              The paper book is yours. Reset it any time and start the
              simulation over.
            </p>
            <button
              onClick={() => setConfirmReset(true)}
              className="text-meta ink-fainter hover:ink-muted transition-colors"
            >
              Reset the book
            </button>
          </>
        ) : (
          <div>
            <p className="ink-primary leading-relaxed max-w-narrative mb-5">
              This closes every open position and returns the book to
              $100,000. There is no undo.
            </p>
            <div className="flex items-center gap-5">
              <button
                onClick={() => {
                  resetBook();
                  setConfirmReset(false);
                }}
                className="text-meta ink-primary hover:opacity-70 transition-opacity"
                style={{
                  borderBottom: '1px solid var(--ink-primary)',
                  paddingBottom: '2px',
                }}
              >
                Yes, reset
              </button>
              <button
                onClick={() => setConfirmReset(false)}
                className="text-meta ink-fainter hover:ink-muted transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </ArthosPage>
  );
}

function PositionRow({
  position,
  onClose,
}: {
  position: PaperPosition;
  onClose: () => void;
}) {
  const pnl = pnlForPosition(position);
  const pnlPct = pnlPctForPosition(position);
  const units =
    position.kind === 'option'
      ? position.quantity === 1
        ? 'contract'
        : 'contracts'
      : position.quantity === 1
        ? 'share'
        : 'shares';
  const daysHeld = Math.max(
    0,
    Math.floor((Date.now() - position.openedAt) / (1000 * 60 * 60 * 24))
  );
  const sideLabel = (() => {
    switch (position.side) {
      case 'long':
        return 'Long';
      case 'short':
        return 'Short';
      case 'long-option':
        return 'Bought';
      case 'short-option':
        return 'Sold';
    }
  })();
  return (
    <li className="surface-base py-6">
      <div className="flex items-baseline justify-between gap-4 flex-wrap mb-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-3 mb-1.5 flex-wrap">
            <span className="font-mono ink-primary text-[14px]">
              {position.symbol}
            </span>
            <span className="text-meta ink-fainter">{sideLabel}</span>
            <span className="text-meta ink-fainter">
              {position.quantity} {units}
            </span>
          </div>
          {position.contract && (
            <div className="font-mono text-[12px] ink-muted tabular-nums mb-1">
              {position.contract}
            </div>
          )}
          <div className="text-meta ink-fainter tabular-nums">
            Entry ${position.entryPrice.toFixed(2)} · Now $
            {position.currentPrice.toFixed(2)} · Day {daysHeld + 1}
          </div>
        </div>
        <div className="text-right tabular-nums shrink-0">
          <div className="ink-primary text-[14px]">
            <span className="mr-1">{pnl >= 0 ? '▲' : '▼'}</span>
            {pnl >= 0 ? '+' : '−'}${Math.abs(pnl).toFixed(2)}
          </div>
          <div className="text-meta ink-fainter mt-1">
            {pnlPct >= 0 ? '+' : '−'}
            {Math.abs(pnlPct).toFixed(2)}%
          </div>
        </div>
      </div>

      <div className="flex items-baseline gap-5 flex-wrap text-[12px]">
        {position.target && (
          <span className="ink-fainter">
            <span className="mr-1">Target</span>
            <span className="ink-muted tabular-nums">{position.target}</span>
          </span>
        )}
        {position.invalidate && position.invalidate !== '—' && (
          <span className="ink-fainter">
            <span className="mr-1">Invalidate</span>
            <span className="ink-muted tabular-nums">
              {position.invalidate}
            </span>
          </span>
        )}
        <button
          onClick={onClose}
          className="text-meta ink-muted hover:ink-primary transition-colors ml-auto"
        >
          Close position
        </button>
      </div>
    </li>
  );
}
