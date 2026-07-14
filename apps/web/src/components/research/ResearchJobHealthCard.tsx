// Phase 11W (Phase F + E.2) - Research Job Health card.
//
// Phase F: shows audit summary from /api/research/usage.
// Phase E.2: extended to also show open alert count, operator
// enforcement state counts, and last-alert timestamp via
// /api/research/usage/summary. NEVER includes action language.
// NEVER renders an action button.

import { useEffect, useState } from 'react';
import ResearchBanner from './ResearchBanner';
import FreshnessBadge from './FreshnessBadge';

interface UsageSummary {
  accepted: number;
  duplicate: number;
  rejected: number;
  in_flight: number;
  errored: number;
  cost_usd_today: number;
}

interface AlertSummary {
  open: number;
  critical_open: number;
  high_open: number;
  last_alert_at: string | null;
}

interface OperatorSummary {
  blocked: number;
  restricted: number;
  watch: number;
  clear: number;
}

interface SummaryResp {
  audit_today: UsageSummary;
  alerts: AlertSummary;
  operators: OperatorSummary;
}

export default function ResearchJobHealthCard() {
  const [data, setData] = useState<SummaryResp | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/research/usage/summary', {
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
      ) : !data || !data.audit_today || !data.alerts || !data.operators ? (
        // Fail closed on malformed payloads (partial provider outage /
        // error-shaped JSON) instead of crashing the whole card tree.
        <div style={{ color: '#616161', fontSize: 13 }}>
          Research subsystem: <strong>unavailable</strong>.
        </div>
      ) : (
        <SummaryView data={data} />
      )}
    </div>
  );
}


function SummaryView({ data }: { data: SummaryResp }) {
  return (
    <div>
      <Section title="Audit (today)">
        <Grid items={[
          ['accepted',  data.audit_today.accepted],
          ['duplicate', data.audit_today.duplicate],
          ['rejected',  data.audit_today.rejected],
          ['in_flight', data.audit_today.in_flight],
          ['errored',   data.audit_today.errored],
          ['cost_usd',  `$${data.audit_today.cost_usd_today.toFixed(4)}`],
        ]} />
      </Section>
      <Section title="Alerts">
        <Grid items={[
          ['open',          data.alerts.open],
          ['critical_open', data.alerts.critical_open],
          ['high_open',     data.alerts.high_open],
        ]} />
        {data.alerts.last_alert_at && (
          <div style={{ fontSize: 11, color: '#616161', marginTop: 6 }}>
            last alert: <FreshnessBadge isoTimestamp={data.alerts.last_alert_at} />
          </div>
        )}
      </Section>
      <Section title="Operators">
        <Grid items={[
          ['blocked',    data.operators.blocked],
          ['restricted', data.operators.restricted],
          ['watch',      data.operators.watch],
          ['clear',      data.operators.clear],
        ]} />
      </Section>
    </div>
  );
}


function Section({ title, children }: {
  title: string; children: React.ReactNode;
}) {
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{
        fontSize: 12, color: '#616161', textTransform: 'uppercase',
        letterSpacing: 0.4, marginBottom: 6,
      }}>{title}</div>
      {children}
    </div>
  );
}


function Grid({ items }: { items: Array<[string, number | string]> }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
        gap: 8,
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
