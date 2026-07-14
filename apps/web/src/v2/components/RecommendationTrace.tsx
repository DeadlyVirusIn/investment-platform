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

// Plain label for a post-policy adjustment rule (no raw rule/reason debug).
const ADJ_LABELS: { match: RegExp; label: string }[] = [
  { match: /volatil/i, label: 'High-volatility trim' },
  { match: /invers|confidence/i, label: 'Recent-misses cap' },
  { match: /drawdown/i, label: 'Drawdown trim' },
  { match: /exposure|concentrat/i, label: 'Position-size cap' },
  { match: /stale|fresh/i, label: 'Freshness cap' },
];

interface Adj { label: string; before: number; after: number; }

function readAdjustments(policy: unknown): Adj[] {
  const adj = (policy as { adjustments?: unknown })?.adjustments;
  if (!Array.isArray(adj)) return [];
  const out: Adj[] = [];
  for (const a of adj) {
    const rule = (a as { rule?: string })?.rule ?? '';
    const reason = (a as { reason?: string })?.reason ?? '';
    const m = ADJ_LABELS.find((d) => d.match.test(`${rule} ${reason}`));
    out.push({
      label: m ? m.label : (rule.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) || 'Adjustment'),
      before: num((a as { score_before?: string })?.score_before),
      after: num((a as { score_after?: string })?.score_after),
    });
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
        <span className="tabular-nums text-[12px] font-medium" style={{ color }}>
          {Number.isFinite(score) ? (score > 0 ? '+' : '') + score.toFixed(2) : '—'}
        </span>
      </div>
      <div className="mt-2 h-[3px] w-full rounded-full" style={{ background: 'var(--hairline,#e5e5e5)' }}>
        <div className="h-[3px] rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
    </li>
  );
}

function Group({ title, color, children }: { title: string; color?: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[12px] font-semibold uppercase tracking-wide mb-3" style={color ? { color } : undefined}>{title}</div>
      <ul className="space-y-3">{children}</ul>
    </div>
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
  const action = rec.adjusted_action ?? rec.action ?? 'Hold';

  return (
    <section className="mb-12 max-w-narrative">
      <div className="flex items-center justify-between gap-3">
        <MetaLabel>See the working</MetaLabel>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="text-[11px] font-medium ink-muted border border-hairline rounded-full px-3 py-1 hover:ink-primary transition-colors"
        >
          {open ? 'Hide audit trail ▴' : 'Show audit trail ▾'}
        </button>
      </div>
      <p className="ink-muted text-[14px] leading-relaxed mt-2">
        {evidence.length} signals across {families.length} families went into this call.
        Nothing here is hidden — this is exactly what the engine weighed.
      </p>

      {open && (
        <div className="mt-5 rounded-xl border border-hairline p-5 sm:p-6 space-y-7">
          {helped.length > 0 && (
            <Group title="What helped the ranking" color={POS}>
              {helped.map((e) => <Row key={e.factor_key} e={e} color={POS} />)}
            </Group>
          )}

          {hurt.length > 0 && (
            <Group title="What hurt the ranking" color={NEG}>
              {hurt.map((e) => <Row key={e.factor_key} e={e} color={NEG} />)}
            </Group>
          )}

          {setAside.length > 0 && (
            <Group title="Considered but set aside">
              {setAside.map((e) => (
                <li key={e.factor_key} className="border-t border-hairline pt-3 ink-muted text-[14px] leading-snug">
                  {e.narrative ?? e.factor_key}
                </li>
              ))}
            </Group>
          )}

          {adjustments.length > 0 && (
            <Group title="Ranking adjustments">
              {adjustments.map((a, i) => {
                const both = Number.isFinite(a.before) && Number.isFinite(a.after);
                return (
                  <li key={`${a.label}-${i}`} className="border-t border-hairline pt-3 flex items-baseline justify-between gap-3">
                    <span className="ink-primary text-[14px] leading-snug">{a.label}</span>
                    <span className="ink-fainter tabular-nums text-[12px]">
                      {both ? `${a.before.toFixed(2)} → ${a.after.toFixed(2)}` : 'applied'}
                    </span>
                  </li>
                );
              })}
            </Group>
          )}

          <div className="border-t-2 border-hairline pt-3 flex items-baseline justify-between gap-3">
            <span className="ink-primary text-[13px] font-medium">Net composite score → {action}</span>
            <span className="ink-primary tabular-nums text-[15px] font-semibold">
              {Number.isFinite(net) ? net.toFixed(3) : '—'}
            </span>
          </div>
        </div>
      )}
    </section>
  );
}
