// Phase X — TrustBanner reads the backend, not localStorage.
//   • "Arth's record"  = backend recommendations (published calls)
//   • "practice book"  = backend paper-portfolio return
//   • personal decisions/reflections stay local (Mentor Profile) and are
//     deliberately NOT counted here as Arth's record.
// Never shows "0 calls" when the engine has live recommendations — the
// count comes straight from /recommendations.

import { Link } from 'react-router-dom';
import {
  useRecommendations,
  useCanonicalStockPortfolio,
  useExecutedTrades,
} from '@/lib/operator/hooks';

// P1.3 — accuracy publishes once this many real closed outcomes exist
// (same threshold + closed-trade definition as Track Record).
const ACCURACY_THRESHOLD = 10;

export function TrustBanner() {
  const { data: recs, isLoading: recsLoading } = useRecommendations();
  // Phase A/B — practice-book return now comes from the canonical
  // portfolio (single source of truth), not the aggregate summary.
  const { data: book } = useCanonicalStockPortfolio();
  // P1.3 — closed outcomes = sells with realized P&L (Track Record's
  // exact definition). Drives the honest accuracy-publish meter.
  const { data: tradesData } = useExecutedTrades(false, book?.portfolio_id, { enabled: !!book?.portfolio_id });

  const callCount = recs?.recommendations?.length ?? null;
  const totalRet = book?.total_return_pct ?? null;
  const closedCount = (tradesData?.trades ?? []).filter(
    (t) => t.side === 'sell' && t.realized_pnl != null,
  ).length;

  return (
    <div className="flex items-baseline gap-3 flex-wrap mb-6 py-3 px-4 rounded-2xl"
         style={{
           backgroundColor: 'color-mix(in oklch, var(--brand) 6%, transparent)',
           border: '1px solid color-mix(in oklch, var(--brand) 16%, transparent)',
         }}>
      <span className="font-semibold uppercase" style={{
        fontSize: 10, letterSpacing: '0.16em', color: 'var(--brand)',
      }}>Arth's record</span>
      <span className="ink-primary" style={{ fontSize: 13 }}>
        {callCount == null
          ? (recsLoading
              ? "Loading Arth's published calls…"
              : "Arth's published calls will appear here shortly.")
          : callCount === 0
            ? 'No calls published yet.'
            : `${callCount} call${callCount === 1 ? '' : 's'} live · accuracy publishes at ${ACCURACY_THRESHOLD} closed outcomes (${Math.min(closedCount, ACCURACY_THRESHOLD)}/${ACCURACY_THRESHOLD} so far).`}
      </span>
      {totalRet != null && (
        <span className="font-mono ink-muted" style={{ fontSize: 12 }}>
          · practice book {totalRet >= 0 ? '+' : ''}{totalRet.toFixed(2)}%
        </span>
      )}
      <Link to="/arth"
            className="ml-auto"
            style={{ fontSize: 12, color: 'var(--brand)', fontWeight: 600 }}>
        See the full record →
      </Link>
    </div>
  );
}
