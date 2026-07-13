// Wave 1C — "What changed since the previous update" (beginner narrative).
//
// Reads GET /api/recommendations/:symbol/delta (flag-mounted; 404 → the
// feature is off or the symbol is unknown → render nothing / unavailable).
// Direction is never color-only (glyph + text); no raw metrics; disclosure
// is a real <details> for keyboard support; no animation.

import { useEffect, useState } from 'react';
import { MetaLabel } from '../chrome/ArthosChrome';
import { freshnessInfo } from '../lib/freshness';

export type DeltaChange = {
  id: string; kind: string;
  direction: 'positive' | 'negative' | 'cautious' | 'neutral' | 'informational';
  significance: 'small' | 'meaningful' | 'large';
  beginner_text: string;
  source: string;
};

export type RecDelta = {
  symbol: string;
  rule_set_version: string;
  current_as_of: string;
  prior_as_of: string | null;
  first_seen: boolean;
  summary: string;
  changes: DeltaChange[];
  evidence_balance: string;
  price_context: string | null;
  freshness_context: string | null;
  limitations: string[];
};

const DIR_GLYPH: Record<DeltaChange['direction'], { glyph: string; color: string; label: string }> = {
  positive: { glyph: '▲', color: 'var(--brand)', label: 'supportive change' },
  negative: { glyph: '▼', color: 'oklch(0.62 0.19 25)', label: 'negative change' },
  cautious: { glyph: '▼', color: 'oklch(0.70 0.14 75)', label: 'cautionary change' },
  neutral: { glyph: '◆', color: 'var(--muted-foreground)', label: 'neutral change' },
  informational: { glyph: '•', color: 'var(--muted-foreground)', label: 'informational change' },
};

const deltaCache = new Map<string, { at: number; value: RecDelta | null }>();

export function useRecDelta(symbol: string | undefined): RecDelta | null | undefined {
  // undefined = loading/unknown · null = unavailable/off · value = delta
  const [state, setState] = useState<RecDelta | null | undefined>(() => {
    const hit = symbol ? deltaCache.get(symbol.toUpperCase()) : undefined;
    return hit && Date.now() - hit.at < 60_000 ? hit.value : undefined;
  });

  useEffect(() => {
    if (!symbol) { setState(null); return; }
    const key = symbol.toUpperCase();
    const hit = deltaCache.get(key);
    if (hit && Date.now() - hit.at < 60_000) { setState(hit.value); return; }
    let alive = true;
    fetch(`/api/recommendations/${encodeURIComponent(key)}/delta`,
      { headers: { Accept: 'application/json' } })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        deltaCache.set(key, { at: Date.now(), value: j });
        if (alive) setState(j);
      })
      .catch(() => { if (alive) setState(null); });
    return () => { alive = false; };
  }, [symbol]);

  return state;
}

function ChangeRow({ c }: { c: DeltaChange }) {
  const d = DIR_GLYPH[c.direction];
  return (
    <li className="flex items-start gap-2.5 py-1.5">
      <span aria-hidden style={{ color: d.color, fontSize: 11, lineHeight: '1.6rem' }}>
        {d.glyph}
      </span>
      <span className="ink-primary" style={{ fontSize: 13.5, lineHeight: 1.6 }}>
        <span className="sr-only">{d.label}: </span>
        {c.beginner_text}
      </span>
    </li>
  );
}

export function WhatChangedSection({ symbol }: { symbol: string | undefined }) {
  const delta = useRecDelta(symbol);
  if (delta === null) return null;                 // feature off / unavailable

  return (
    <section className="mb-12 max-w-narrative">
      <MetaLabel>What changed since the previous update</MetaLabel>
      {delta === undefined ? (
        <p className="ink-fainter text-[13px] mt-3" role="status">
          Checking for changes…
        </p>
      ) : (
        <>
          <p className="ink-primary text-[15px] leading-relaxed mt-3">
            {delta.summary}
          </p>
          {delta.prior_as_of && (
            <p className="ink-fainter text-[11.5px] tabular-nums mt-1">
              Compared with the update from{' '}
              {freshnessInfo(delta.prior_as_of).label.toLowerCase().replace('updated ', '')}
              {' '}({delta.prior_as_of.slice(0, 10)}).
            </p>
          )}
          {delta.changes.length > 0 && (
            <>
              <ul className="mt-3">
                {delta.changes.slice(0, 3).map((c) => <ChangeRow key={c.id} c={c} />)}
              </ul>
              {delta.changes.length > 3 && (
                <details className="mt-1.5">
                  <summary className="ink-fainter text-[12px] cursor-pointer select-none">
                    See all {delta.changes.length} changes
                  </summary>
                  <ul className="mt-1.5">
                    {delta.changes.slice(3).map((c) => <ChangeRow key={c.id} c={c} />)}
                  </ul>
                </details>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}

/** Compact one-liner for cards/strips. Returns null unless the delta is
 *  genuinely worth a line (new idea, or a meaningful+ top change). */
export function compactChangeNote(delta: RecDelta | null | undefined): string | null {
  if (!delta) return null;
  if (delta.first_seen) return 'New idea';
  const top = delta.changes[0];
  if (!top || top.significance === 'small') return null;
  if (top.kind === 'action_change') {
    return top.direction === 'cautious'
      ? 'More cautious than the previous update'
      : 'More constructive than the previous update';
  }
  if (top.kind === 'evidence_balance' && top.direction === 'cautious') {
    return 'Risk signals increased';
  }
  if (top.kind === 'evidence_balance' && top.direction === 'positive') {
    return 'Evidence strengthened';
  }
  if (top.kind === 'outcome_status') return top.beginner_text;
  return null;
}

/** Reusable formatter for Research Inbox supersedes context (Wave 2 hook —
 *  not wired into Inbox workflow in this slice). */
export function formatSupersedesNote(delta: RecDelta | null | undefined): string | null {
  if (!delta || delta.first_seen || !delta.prior_as_of) return null;
  return `Supersedes the ${delta.prior_as_of.slice(0, 10)} update — ${delta.summary}`;
}
