// Phase 11W (Phase F) - Research Job Health card on the existing
// JobsHealth page. Internal-ops surface. Reads `/api/research/usage`
// (GET-only). Shows accept/reject/cost rollup for the day plus a
// neutral status indicator. NEVER includes action language.

import { useEffect, useState } from 'react';
import ResearchBanner from './ResearchBanner';

interface UsageSummary {
  accepted: number;
  duplicate: number;
  rejected: number;
  in_flight: number;
  errored: number;
  cost_usd_today: number;
}

interface UsageResp {
  audit_table: 'present' | 'absent';
  summary: UsageSummary;
}

export default function ResearchJobHealthCard() {
  const [data, setData] = useState<UsageResp | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/research/usage', {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })
      .then((r) => r.json())
      .then((j) => !cancelled && setData(j))
      .catch(() => !cancelled && setData(null))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, []);

  return (
    <div
      className="research-job-health-card"
      style={{
        background: '#fff',
        border: '1px solid #e0e0e0',
        borderRadius: 4,
        padding: 16,
      }}
    >
      <h3 style={{ marginTop: 0, marginBottom: 12, fontSize: 14 }}>
        Research Intelligence Job Health
      </h3>
      <ResearchBanner context="jobs-health" />
      {loading ? (
        <div style={{ color: '#9e9e9e', fontSize: 12 }}>
          Loading usage rollup…
        </div>
      ) : !data || data.audit_table === 'absent' ? (
        <div style={{ color: '#616161', fontSize: 13 }}>
          Research subsystem: <strong>read-only mode</strong>.
          <div style={{ fontSize: 12, marginTop: 4, color: '#9e9e9e' }}>
            Audit table not yet provisioned.
          </div>
        </div>
      ) : (
        <UsageGrid summary={data.summary} />
      )}
    </div>
  );
}


function UsageGrid({ summary }: { summary: UsageSummary }) {
  const items: Array<[string, number | string]> = [
    ['accepted',  summary.accepted],
    ['duplicate', summary.duplicate],
    ['rejected',  summary.rejected],
    ['in_flight', summary.in_flight],
    ['errored',   summary.errored],
    ['cost_usd',  `$${summary.cost_usd_today.toFixed(4)}`],
  ];
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
        gap: 8,
        marginTop: 4,
      }}
    >
      {items.map(([k, v]) => (
        <div
          key={k}
          style={{
            background: '#fafafa',
            border: '1px solid #eeeeee',
            borderRadius: 3,
            padding: '8px 10px',
            fontSize: 12,
          }}
        >
          <div style={{ color: '#9e9e9e' }}>{k}</div>
          <div style={{ color: '#212121', fontWeight: 600 }}>{v}</div>
        </div>
      ))}
    </div>
  );
}
