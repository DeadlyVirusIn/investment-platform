// Phase 2B — Compact trust banner for Today.
// Voiced + honest about sample size.

import { Link } from 'react-router-dom';
import { computeTrustMetrics, accuracyPhrase, expectancyPhrase } from '../lib/arth/trustMetrics';
import { useDecisions } from '../lib/arth/decisions';

export function TrustBanner() {
  useDecisions();                  // subscribe so it re-renders on decisions
  const m = computeTrustMetrics();

  return (
    <div className="flex items-baseline gap-3 flex-wrap mb-6 py-3 px-4 rounded-2xl"
         style={{
           backgroundColor: 'color-mix(in oklch, var(--brand) 6%, transparent)',
           border: '1px solid color-mix(in oklch, var(--brand) 16%, transparent)',
         }}>
      <span className="font-semibold uppercase" style={{
        fontSize: 10, letterSpacing: '0.16em', color: 'var(--brand)',
      }}>Arth's last 30 days</span>
      <span className="ink-primary" style={{ fontSize: 13 }}>
        {accuracyPhrase(m)}
      </span>
      {m.total_closed > 0 && (
        <span className="font-mono ink-muted" style={{ fontSize: 12 }}>
          · {expectancyPhrase(m)}
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
