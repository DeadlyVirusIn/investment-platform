// MVP Phase A — FirstPositionPanel.
//
// Mounts on Today when the user has just placed their first paper trade.
// Visible while:
//   state.positions.length >= 1
//   state.history.length === 0           (no closed trade yet)
//   first open position is < 7 days old  (auto-dismiss after week 1)
//
// Auto-dismiss after either 7 days OR the user closes any position.

import { Link } from 'react-router-dom';
import { usePaperBook } from '../state/PaperBook';

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

export function FirstPositionPanel() {
  const { positions, history } = usePaperBook();

  // Gate: must have an open position, no closed history, and the
  // earliest open position is less than a week old.
  if (positions.length === 0) return null;
  if (history.length > 0) return null;

  const earliest = positions.reduce(
    (acc, p) => (p.openedAt < acc.openedAt ? p : acc),
    positions[0]
  );
  if (Date.now() - earliest.openedAt > WEEK_MS) return null;

  const days = Math.max(
    1,
    Math.floor((Date.now() - earliest.openedAt) / (1000 * 60 * 60 * 24)) + 1
  );

  return (
    <section
      aria-label="Your first position"
      className="mb-12 max-w-copy"
    >
      <div className="flex items-baseline gap-3 mb-4">
        <span aria-hidden className="ink-primary text-[14px]">✦</span>
        <span className="text-meta ink-fainter">Your first position</span>
      </div>
      <p className="ink-primary text-[15px] leading-relaxed mb-3">
        You just placed your first paper trade.
      </p>
      <p className="ink-muted text-[14px] leading-relaxed mb-5">
        <span className="font-mono ink-primary">{earliest.symbol}</span>
        {' · '}
        {earliest.side === 'short' || earliest.side === 'short-option'
          ? 'Short'
          : 'Long'}
        {' · '}
        {earliest.quantity}{' '}
        {earliest.kind === 'option'
          ? earliest.quantity === 1
            ? 'contract'
            : 'contracts'
          : earliest.quantity === 1
            ? 'share'
            : 'shares'}
        {' · '}
        entry ${earliest.entryPrice.toFixed(2)}. Day {days} of holding. We'll
        watch this with you.
      </p>
      <p className="ink-muted text-[14px] leading-relaxed mb-5 italic">
        The position will update through the session. You can close it any
        time from Paper book. Most positions are held longer than the first
        hour feels like.
      </p>
      <div className="flex items-baseline gap-6 flex-wrap">
        <Link
          to="/v2/portfolio"
          className="text-meta ink-primary hover:opacity-70 transition-opacity inline-flex items-center gap-1.5"
        >
          Open paper book <span aria-hidden>→</span>
        </Link>
        <Link
          to={`/v2/today/pick/${earliest.symbol}`}
          className="text-meta ink-muted hover:ink-primary transition-colors"
        >
          Read the thesis →
        </Link>
      </div>
    </section>
  );
}
