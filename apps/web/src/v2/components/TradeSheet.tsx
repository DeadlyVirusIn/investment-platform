// V2 TradeSheet — modal that places a Recommendation in the paper
// book. Internal link points to /v2/portfolio.

import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { usePaperBook } from '../state/PaperBook';
import type { Recommendation } from '../data/arthosData';

interface TradeSheetProps {
  rec: Recommendation | null;
  onClose: () => void;
}

export function TradeSheet({ rec, onClose }: TradeSheetProps) {
  const { cash, openFromRec } = usePaperBook();
  const [quantity, setQuantity] = useState<number>(rec?.defaultQuantity ?? 1);
  const [status, setStatus] = useState<'compose' | 'placed' | 'error'>(
    'compose'
  );
  const [errorMsg, setErrorMsg] = useState<string>('');

  useEffect(() => {
    if (rec) {
      setQuantity(rec.defaultQuantity ?? 1);
      setStatus('compose');
      setErrorMsg('');
    }
  }, [rec?.symbol]);

  useEffect(() => {
    if (!rec) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [rec, onClose]);

  const computed = useMemo(() => {
    if (!rec || rec.entryPrice === undefined || !rec.side) return null;
    const multiplier = rec.kind === 'option' ? 100 : 1;
    let cashImpact = 0;
    let label = '';
    if (rec.side === 'long' || rec.side === 'short') {
      cashImpact = rec.entryPrice * quantity;
      label = rec.side === 'short' ? 'Margin reserved' : 'Cash deployed';
    } else if (rec.side === 'long-option') {
      cashImpact = rec.entryPrice * quantity * multiplier;
      label = 'Debit paid';
    } else {
      cashImpact =
        (rec.maxLossPerContract ?? rec.entryPrice * multiplier) * quantity;
      label = 'Max loss reserved';
    }
    const units = rec.kind === 'option' ? 'contracts' : 'shares';
    return { cashImpact, label, units, multiplier };
  }, [rec, quantity]);

  const insufficient = computed ? computed.cashImpact > cash : false;
  const canPlace = !!rec && !!computed && !insufficient && quantity > 0;

  const handlePlace = () => {
    if (!rec) return;
    const result = openFromRec(rec, quantity);
    if (result.ok) setStatus('placed');
    else {
      setErrorMsg(result.reason || 'Could not place.');
      setStatus('error');
    }
  };

  return (
    <AnimatePresence>
      {rec && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            onClick={onClose}
            className="fixed inset-0 z-50"
            style={{ backgroundColor: 'var(--backdrop)' }}
          />
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 40 }}
            transition={{ duration: 0.35, ease: [0.32, 0.72, 0, 1] }}
            className="fixed left-0 right-0 bottom-0 md:inset-0 md:flex md:items-center md:justify-center z-50 px-0 md:px-5 pointer-events-none"
          >
            <div
              className="surface-drawer w-full md:max-w-lg md:w-full md:rounded-2xl rounded-t-2xl p-7 sm:p-9 pointer-events-auto"
              style={{
                backgroundColor: 'var(--surface-drawer)',
                maxHeight: '90vh',
                overflowY: 'auto',
              }}
            >
              {status === 'compose' && (
                <ComposeView
                  rec={rec}
                  quantity={quantity}
                  setQuantity={setQuantity}
                  computed={computed}
                  cash={cash}
                  insufficient={insufficient}
                  canPlace={canPlace}
                  onPlace={handlePlace}
                  onCancel={onClose}
                />
              )}
              {status === 'placed' && (
                <PlacedView
                  rec={rec}
                  quantity={quantity}
                  units={computed?.units ?? 'units'}
                  onClose={onClose}
                />
              )}
              {status === 'error' && (
                <ErrorView
                  message={errorMsg}
                  onBack={() => setStatus('compose')}
                />
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

function ComposeView({
  rec,
  quantity,
  setQuantity,
  computed,
  cash,
  insufficient,
  canPlace,
  onPlace,
  onCancel,
}: any) {
  return (
    <>
      <div className="text-meta ink-fainter mb-3">Local practice simulation</div>
      <h2 className="font-serif text-[24px] ink-primary leading-snug mb-3">
        {rec.actionLabel}
      </h2>
      {rec.contract && (
        <div className="font-mono text-[13px] ink-muted mb-4 tabular-nums">
          {rec.contract}
        </div>
      )}
      <p className="ink-muted leading-relaxed text-[15px] mb-7 max-w-narrative">
        {rec.paragraph}
      </p>

      <div className="mb-7">
        <label htmlFor="qty" className="text-meta ink-fainter block mb-2.5">
          Quantity ({computed?.units})
        </label>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setQuantity(Math.max(1, quantity - 1))}
            aria-label="Decrease"
            className="w-9 h-9 ink-muted hover:ink-primary border border-hairline rounded-md transition-colors"
          >
            −
          </button>
          <input
            id="qty"
            type="number"
            min={1}
            value={quantity}
            onChange={(e) =>
              setQuantity(Math.max(1, parseInt(e.target.value) || 1))
            }
            className="w-20 text-center bg-transparent ink-primary font-mono text-[18px] tabular-nums border border-hairline rounded-md py-2 outline-none focus:border-ink-muted"
          />
          <button
            type="button"
            onClick={() => setQuantity(quantity + 1)}
            aria-label="Increase"
            className="w-9 h-9 ink-muted hover:ink-primary border border-hairline rounded-md transition-colors"
          >
            +
          </button>
          <span className="text-meta ink-fainter ml-2">
            Suggested {rec.defaultQuantity}
          </span>
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-y-3 gap-x-6 pt-6 border-t border-hairline mb-3 text-[13px]">
        <dt className="text-meta ink-fainter">{computed?.label}</dt>
        <dd className="ink-primary tabular-nums text-right">
          $
          {computed?.cashImpact.toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          })}
        </dd>
        <dt className="text-meta ink-fainter">Local sim cash</dt>
        <dd
          className={`tabular-nums text-right ${
            insufficient ? 'ink-muted' : 'ink-primary'
          }`}
        >
          $
          {cash.toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          })}
        </dd>
      </dl>

      {insufficient && (
        <p className="text-[13px] ink-muted italic mt-3 mb-1 leading-relaxed">
          Not enough cash for this size. Reduce the quantity or close another
          position first.
        </p>
      )}

      <div className="flex items-center gap-4 mt-8 pt-6 border-t border-hairline">
        <button
          onClick={onPlace}
          disabled={!canPlace}
          className="flex-1 py-3 px-5 rounded-md font-serif text-[16px] transition-opacity disabled:opacity-40"
          style={{
            backgroundColor: 'var(--ink-primary)',
            color: 'var(--surface-base)',
            cursor: canPlace ? 'pointer' : 'not-allowed',
          }}
        >
          Place in paper book
        </button>
        <button
          onClick={onCancel}
          className="text-meta ink-fainter hover:ink-muted transition-colors"
        >
          Cancel
        </button>
      </div>

      <p className="text-[12px] ink-fainter italic mt-5 leading-relaxed text-center">
        Local practice simulation only — a separate $100,000 sandbox in your
        browser. This is NOT the tracked practice portfolio and is not placed
        on the backend account.
      </p>
    </>
  );
}

function PlacedView({ rec, quantity, units, onClose }: any) {
  return (
    <div className="py-2">
      <div className="text-meta ink-fainter mb-3">Placed</div>
      <h2 className="font-serif text-[22px] ink-primary leading-snug mb-4">
        {quantity} {units} of {rec.symbol} added to your paper book.
      </h2>
      <p className="ink-muted leading-relaxed text-[15px] mb-8 max-w-narrative">
        The position will update as the simulation moves. You can close it any
        time from the paper book.
      </p>
      <div className="flex items-center gap-5 pt-6 border-t border-hairline">
        <Link
          to="/v2/portfolio"
          onClick={onClose}
          className="text-meta ink-primary hover:opacity-80 transition-opacity inline-flex items-center gap-1.5"
        >
          Open paper book <span aria-hidden>→</span>
        </Link>
        <button
          onClick={onClose}
          className="text-meta ink-fainter hover:ink-muted transition-colors ml-auto"
        >
          Stay on the briefing
        </button>
      </div>
    </div>
  );
}

function ErrorView({
  message,
  onBack,
}: {
  message: string;
  onBack: () => void;
}) {
  return (
    <div className="py-2">
      <div className="text-meta ink-fainter mb-3">Could not place</div>
      <p className="ink-primary leading-relaxed text-[16px] mb-7 max-w-narrative">
        {message}
      </p>
      <button
        onClick={onBack}
        className="text-meta ink-muted hover:ink-primary transition-colors inline-flex items-center gap-1.5"
      >
        <span aria-hidden>←</span> Back
      </button>
    </div>
  );
}
