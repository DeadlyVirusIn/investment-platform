// Wave 1A — beginner-facing publication-preflight limitations.
// Renders ONLY the redacted public projection (beginner_text lines the API
// chose to publish). Never shows raw checks, hashes, verdict internals, or
// developer diagnostics — those live behind the owner /admin/preflight UI.

import { useState } from 'react';
import type { RecApi } from '@/lib/operator/hooks';

export function PreflightLimitations({ rec, compact = false }: {
  rec: RecApi; compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const pf = rec.preflight;
  if (!pf || pf.verdict !== 'READY_WITH_LIMITATIONS' || pf.limitations.length === 0) {
    return null;
  }
  const tone = 'oklch(0.70 0.14 75)';
  return (
    <div className={compact ? 'mt-2' : 'mt-3'}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-full font-semibold"
        style={{
          fontSize: 11, letterSpacing: '0.04em', padding: '3px 10px',
          color: tone,
          backgroundColor: `color-mix(in oklch, ${tone} 11%, transparent)`,
          border: `1px solid color-mix(in oklch, ${tone} 30%, transparent)`,
        }}
      >
        <span aria-hidden>◐</span>
        Published with limitations
        <span aria-hidden style={{ fontSize: 9 }}>{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <ul className="mt-2 space-y-1 pl-1">
          {pf.limitations.map((t) => (
            <li key={t} className="ink-muted flex items-start gap-2"
              style={{ fontSize: 12.5, lineHeight: 1.55 }}>
              <span aria-hidden style={{ color: tone }}>•</span>
              {t}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
