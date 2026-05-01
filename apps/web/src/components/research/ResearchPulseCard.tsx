// Phase 11W (Phase F) - Research Pulse card on the Dashboard.
// Reads /api/research/runs (GET-only). Renders count + most-recent
// provenance stamp. NEVER includes action language. NEVER links to
// a trading surface.

import { useEffect, useState } from 'react';
import ResearchBanner from './ResearchBanner';
import ResearchByline from './ResearchByline';
import FreshnessBadge from './FreshnessBadge';

interface PulseRun {
  id: string;
  symbol: string;
  provider: string;
  model_id: string | null;
  model_version: string | null;
  prompt_hash: string | null;
  as_of: string | null;
  started_at: string | null;
  status: string;
  operator_id: string | null;
}

export default function ResearchPulseCard() {
  const [runs, setRuns] = useState<PulseRun[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/research/runs?limit=5', {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })
      .then((r) => r.json())
      .then((j) => {
        if (!cancelled) setRuns(Array.isArray(j?.runs) ? j.runs : []);
      })
      .catch(() => !cancelled && setRuns([]))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, []);

  return (
    <div
      className="research-pulse-card"
      style={{
        background: '#fff',
        border: '1px solid #e0e0e0',
        borderRadius: 4,
        padding: 16,
      }}
    >
      <h3 style={{ marginTop: 0, marginBottom: 12, fontSize: 14 }}>
        Research Pulse
      </h3>
      <ResearchBanner context="pulse" />
      {loading ? (
        <div style={{ color: '#9e9e9e', fontSize: 12 }}>
          Loading research activity…
        </div>
      ) : runs.length === 0 ? (
        <div style={{ color: '#616161', fontSize: 13 }}>
          0 research runs recorded.
          <div style={{ fontSize: 12, marginTop: 4, color: '#9e9e9e' }}>
            Research orchestration is read-only and operator-controlled.
          </div>
        </div>
      ) : (
        <div>
          <div style={{ fontSize: 13, color: '#424242', marginBottom: 8 }}>
            {runs.length} recent research run{runs.length === 1 ? '' : 's'}
          </div>
          {runs.slice(0, 3).map((r) => (
            <div
              key={r.id}
              style={{
                borderBottom: '1px dashed #eeeeee',
                paddingBottom: 8,
                marginBottom: 8,
              }}
            >
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                fontSize: 12, color: '#212121',
              }}>
                <strong>{r.symbol}</strong>
                <FreshnessBadge isoTimestamp={r.started_at} />
                <span style={{ color: '#9e9e9e' }}>{r.status}</span>
              </div>
              <ResearchByline
                provider={r.provider}
                modelId={r.model_id}
                modelVersion={r.model_version}
                promptHash={r.prompt_hash}
                asOf={r.as_of}
                operatorId={r.operator_id}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
