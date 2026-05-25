// Phase X — TrustBanner reads the backend, not localStorage.
//   • "Arth's record"  = backend recommendations (published calls)
//   • "practice book"  = backend paper-portfolio return
//   • personal decisions/reflections stay local (Mentor Profile) and are
//     deliberately NOT counted here as Arth's record.
// Never shows "0 calls" when the engine has live recommendations — the
// count comes straight from /recommendations.

import { Link } from 'react-router-dom';
import { useRecommendations, usePaperSummary } from '@/lib/operator/hooks';

export function TrustBanner() {
  const { data: recs, isLoading: recsLoading } = useRecommendations();
  const { data: summary } = usePaperSummary();

  const callCount = recs?.recommendations?.length ?? null;
  const totalRet = summary?.total_return_pct ?? null;

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
              : "Arth's record is unavailable right now.")
          : callCount === 0
            ? 'No calls published yet.'
            : `${callCount} call${callCount === 1 ? '' : 's'} live — closed-outcome accuracy builds as positions resolve.`}
      </span>
      {totalRet != null && (
        <span className="font-mono ink-muted" style={{ fontSize: 12 }}>
          · practice book {totalRet >= 0 ? '+' : ''}{totalRet.toFixed(2)}%
        </span>
      )}
      <Link to="/v2/arth"
            className="ml-auto"
            style={{ fontSize: 12, color: 'var(--brand)', fontWeight: 600 }}>
        See the full record →
      </Link>
    </div>
  );
}
