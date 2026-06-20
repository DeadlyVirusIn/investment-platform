// Recommendation Trace — "See the working" (P0-2, investor-demo).
//
// A concise, investor-grade AUDIT TRAIL for one recommendation (NOT
// chain-of-thought). Layer-3 surface: it is explicitly the place where the
// real engine detail is allowed to show — every factor considered, what
// helped the ranking, what hurt it, what was set aside, and any post-policy
// ranking adjustments. Every value is read from the recommendation's REAL
// stored evidence + policy (already returned by GET /recommendations).

import { useState } from 'react';
import { MetaLabel } from '../chrome/ArthosChrome';
import type { RecApi, RecEvidence } from '@/lib/operator/hooks';

const POS = 'var(--brand)';
const NEG = 'oklch(0.70 0.14 75)';

function num(s: string | null | undefined): number {
  const v = s == null ? NaN : Number(s);
  return Number.isFinite(v) ? v : NaN;
}

interface Adj { rule: string; before: number; after: number; }

function readAdjustments(policy: unknown): Adj[] {
  const adj = (policy as { adjustments?: unknown })?.adjustments;
  if (!Array.isArray(adj)) return [];
  const out: Adj[] = [];
  for (const a of adj) {
    const rule = (a as { rule?: string })?.rule ?? 'adjustment';
    const before = num((a as { score_before?: string })?.score_before);
    const after = num((a as { score_after?: string })?.score_after);
    out.push({ rule: rule.replace(/_/g, ' '), before, after });
  }
  return out;
}

function Row({ e, color }: { e: RecEvidence; color: string }) {
  const score = num(e.score);
  const pct = Number.isFinite(score) ? Math.min(100, Math.abs(score) * 100) : 0;
  return (
    <li className="border-t border-hairline pt-3">
      <div className="flex items-baseline justify-between gap-3">
        <span className="ink-primary text-[14px] leading-snug">{e.narrative ?? e.factor_key}</span>
        <span className="ink-fainter tabular-nums text-[12px]">
          {Number.isFinite(score) ? (score > 0 ? '+' : '') + score.toFixed(2) : '—'}
        </span>
      </div>
      <div className="mt-2 h-[3px] w-full rounded-full" style={{ background: 'var(--hairline,#e5e5e5)' }}>
        <div className="h-[3px] rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
    </li>
  );
}

export function RecommendationTrace({ rec }: { rec: RecApi }) {
  const [open, setOpen] = useState(false);
  const evidence = rec.evidence ?? [];
  if (evidence.length === 0) return null;

  const helped = evidence.filter((e) => num(e.score) > 0.02).sort((a, b) => num(b.score) - num(a.score));
  const hurt = evidence.filter((e) => num(e.score) < -0.02).sort((a, b) => num(a.score) - num(b.score));
  const setAside = evidence.filter((e) => {
    const s = num(e.score);
    return !Number.isFinite(s) || Math.abs(s) <= 0.02;
  });
  const adjustments = readAdjustments(rec.policy);
  const net = num(rec.adjusted_composite_score ?? rec.composite_score);
  const families = Array.from(new Set(evidence.map((e) => e.family).filter(Boolean)));

  return (
    <section className="mb-12 max-w-narrative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 text-left"
        aria-expanded={open}
      >
        <MetaLabel>See the working</MetaLabel>
        <span className="ink-fainter text-[12px]">{open ? '▲ hide' : '▼ show the audit trail'}</span>
      </button>
      <p className="ink-muted text-[14px] leading-relaxed mt-2">
        {evidence.length} signals across {families.length} families went into this call.
        Nothing here is hidden — this is exactly what the engine weighed.
      </p>

      {open && (
        <div className="mt-5 space-y-7">
          {helped.length > 0 && (
            <div>
              <div className="text-[13px] font-medium mb-3" style={{ color: POS }}>What helped the ranking</div>
              <ul className="space-y-3">{helped.map((e) => <Row key={e.factor_key} e={e} color={POS} />)}</ul>
            </div>
          )}

          {hurt.length > 0 && (
            <div>
              <div className="text-[13px] font-medium mb-3" style={{ color: NEG }}>What hurt the ranking</div>
              <ul className="space-y-3">{hurt.map((e) => <Row key={e.factor_key} e={e} color={NEG} />)}</ul>
            </div>
          )}

          {setAside.length > 0 && (
            <div>
              <div className="text-[13px] font-medium ink-muted mb-3">Considered but set aside</div>
              <ul className="space-y-3">
                {setAside.map((e) => (
                  <li key={e.factor_key} className="border-t border-hairline pt-3 ink-muted text-[14px] leading-snug">
                    {e.narrative ?? e.factor_key}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {adjustments.length > 0 && (
            <div>
              <div className="text-[13px] font-medium ink-muted mb-3">Ranking adjustments</div>
              <ul className="space-y-3">
                {adjustments.map((a, i) => (
                  <li key={`${a.rule}-${i}`} className="border-t border-hairline pt-3 flex items-baseline justify-between gap-3">
                    <span className="ink-primary text-[14px] leading-snug">{a.rule}</span>
                    <span className="ink-fainter tabular-nums text-[12px]">
                      {Number.isFinite(a.before) ? a.before.toFixed(2) : '—'} → {Number.isFinite(a.after) ? a.after.toFixed(2) : '—'}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="border-t border-hairline pt-3 flex items-baseline justify-between gap-3">
            <span className="ink-muted text-[13px]">Net composite score → {(rec.adjusted_action ?? rec.action ?? 'Hold')}</span>
            <span className="ink-primary tabular-nums text-[13px] font-medium">
              {Number.isFinite(net) ? net.toFixed(3) : '—'}
            </span>
          </div>
        </div>
      )}
    </section>
  );
}
