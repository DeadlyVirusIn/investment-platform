// Phase 11W (Phase F.1) — read-only research timeline for an asset.
// Reads `/api/research/runs?symbol=X`. Pro/Enterprise only.
// Free tier shows the locked preview.

import { useEffect, useState } from 'react';
import { getResearchTier, tierFetch } from '../../lib/research/tier';
import ResearchBanner from './ResearchBanner';
import ResearchByline from './ResearchByline';
import FreshnessBadge from './FreshnessBadge';
import ResearchLockedPreview from './ResearchLockedPreview';

interface RunRow {
  id: string;
  symbol?: string;
  as_of?: string | null;
  provider?: string;
  model_id?: string | null;
  model_version?: string | null;
  prompt_hash?: string | null;
  status?: string;
  started_at?: string | null;
  operator_id?: string | null;
  has_full_note?: boolean;
}

export interface ResearchTimelineProps {
  symbol?: string;
  limit?: number;
}

export default function ResearchTimeline({
  symbol, limit = 20,
}: ResearchTimelineProps) {
  const tier = getResearchTier();
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const sym = (symbol || '').trim().toUpperCase();
    const qs = sym
      ? `?symbol=${encodeURIComponent(sym)}&limit=${limit}`
      : `?limit=${limit}`;
    tierFetch(`/api/research/runs${qs}`)
      .then((r) => r.json())
      .then((j) => !cancelled && setRuns(Array.isArray(j?.runs) ? j.runs : []))
      .catch(() => !cancelled && setRuns([]))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [symbol, limit]);

  return (
    <div className="research-timeline">
      <ResearchBanner context="tab" />
      {tier === 'free' ? (
        <ResearchLockedPreview variant="history" />
      ) : loading ? (
        <div style={{ color: '#9e9e9e', fontSize: 12, padding: 16 }}>
          Loading research timeline…
        </div>
      ) : runs.length === 0 ? (
        <div
          style={{
            color: '#616161', fontSize: 13,
            textAlign: 'center', padding: 24,
          }}
        >
          No research notes recorded for this asset.
        </div>
      ) : (
        <div style={{ marginTop: 8 }}>
          {runs.map((r) => (
            <div
              key={r.id}
              style={{
                borderBottom: '1px dashed #eeeeee',
                paddingBottom: 8, marginBottom: 8,
              }}
            >
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                fontSize: 12,
              }}>
                {r.symbol && <strong>{r.symbol}</strong>}
                <FreshnessBadge isoTimestamp={r.started_at ?? null} />
                {r.status && (
                  <span style={{ color: '#9e9e9e' }}>{r.status}</span>
                )}
              </div>
              <ResearchByline
                provider={r.provider ?? '—'}
                modelId={r.model_id ?? null}
                modelVersion={r.model_version ?? null}
                promptHash={r.prompt_hash ?? null}
                asOf={r.as_of ?? null}
                operatorId={r.operator_id ?? null}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
