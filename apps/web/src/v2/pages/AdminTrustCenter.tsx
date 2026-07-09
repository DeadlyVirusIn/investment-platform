// Honest Numbers — owner Trust Center (real read-only feeds via
// /api/admin/trust-center; server-side owner guard 404s everyone else).
// Not linked from user navigation; reachable only inside the admin console.

import { useEffect, useState } from 'react';
import { apiGet } from '@/lib/api';
import { ArthosPage } from '../chrome/ArthosChrome';

type Section = { title: string; label: string; body: string; data: Record<string, unknown> };
type Payload = { generated_at: string; audience: string; sections: Section[] };

const LABEL_COLOR: Record<string, string> = {
  proven: 'var(--brand)',
  preliminary: 'oklch(0.70 0.14 75)',
  insufficient_data: 'oklch(0.62 0.19 25)',
  not_yet_evaluated: 'var(--muted-foreground)',
  degraded: 'oklch(0.62 0.19 25)',
  unavailable: 'var(--muted-foreground)',
};

export function AdminTrustCenter() {
  const [payload, setPayload] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Payload>('/admin/trust-center')
      .then(setPayload)
      .catch(() => setError('Not available (owner-only).'));
  }, []);

  return (
    <ArthosPage maxWidth="max-w-copy">
      <p className="text-meta ink-fainter mb-1 mt-8">ADMIN — OWNER-FACING</p>
      <h1 className="font-serif text-headline ink-primary mb-2">Trust Center</h1>
      <p className="ink-muted text-[13.5px] mb-8 max-w-narrative">
        What ArthOS knows about itself, with honest labels. Sections without
        evidence say so — nothing here is a marketing number.
      </p>
      {error && <p className="ink-muted text-[13px]">{error}</p>}
      {payload?.sections.map((s) => (
        <section key={s.title} className="mb-5 pb-4" style={{
          borderBottom: '1px solid color-mix(in oklch, var(--muted-foreground) 18%, transparent)',
        }}>
          <div className="flex items-center justify-between gap-3 mb-1">
            <h2 className="ink-primary text-[14px] font-semibold">{s.title}</h2>
            <span className="text-[10px] font-semibold tracking-wider shrink-0"
              style={{ color: LABEL_COLOR[s.label] ?? 'var(--muted-foreground)' }}>
              {s.label.replace(/_/g, ' ').toUpperCase()}
            </span>
          </div>
          <p className="ink-muted text-[12.5px] leading-relaxed">{s.body}</p>
          {Object.keys(s.data).length > 0 && (
            <pre className="ink-fainter text-[10.5px] mt-2 overflow-x-auto">
              {JSON.stringify(s.data, null, 1)}
            </pre>
          )}
        </section>
      ))}
      {payload && (
        <p className="ink-fainter text-[10.5px] tabular-nums">
          generated {payload.generated_at}
        </p>
      )}
    </ArthosPage>
  );
}
