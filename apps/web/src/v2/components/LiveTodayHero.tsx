// LiveTodayHero — Today's "THE ONE" rendered from the LIVE recommendation
// engine (GET /recommendations). Beginner-first (Sprint H–J): plain language
// only — Why this idea exists / What supports it / Key risk / Confidence level.
// No composite/momentum/volatility scores, no raw confidence numbers, no
// engine vocabulary. Fields the backend lacks (entry/target) are omitted.

import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { SurfaceCard } from './ui/SurfaceCard';
import { plainThesis, ideaSignals } from '../lib/plainText';
import { type RecApi, effectiveAction } from '@/lib/operator/hooks';

function ageHours(iso: string | null): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  return (Date.now() - t) / 3600_000;
}

function freshness(rec: RecApi): { label: string; tone: 'good' | 'warn' } {
  const h = ageHours(rec.generated_at);
  if (rec.stale_data || (h != null && h > 30)) {
    return { label: 'Older', tone: 'warn' };
  }
  return { label: 'Updated today', tone: 'good' };
}

function absTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export function LiveTodayHero({
  rec, alsoConsider = [],
}: {
  rec: RecApi;
  alsoConsider?: RecApi[];
}) {
  const action = effectiveAction(rec) ?? 'Hold';
  const fresh = freshness(rec);
  const freshColor = fresh.tone === 'good' ? 'var(--brand)' : 'oklch(0.70 0.14 75)';
  const sig = ideaSignals(rec.family_scores);
  const why = plainThesis(rec.thesis);
  const support = sig.why.slice(0, 3);
  const keyRisk = sig.risks[0] ?? null;
  const confLabel = (rec.confidence_label ?? 'Medium').toLowerCase();

  return (
    <SurfaceCard variant="highlight" className="p-6 lg:p-7">
      <div className="flex items-baseline gap-3 flex-wrap mb-1">
        <span className="px-2 py-0.5 rounded-full font-semibold uppercase"
          style={{
            fontSize: 10, letterSpacing: '0.14em',
            backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)',
          }}>★ Today's top idea</span>
      </div>

      <div className="flex items-baseline gap-3 flex-wrap mt-2">
        <span className="font-mono ink-primary tabular-nums" style={{ fontSize: 24 }}>
          {rec.symbol ?? '—'}
        </span>
        <span className="ink-muted" style={{ fontSize: 14 }}>{action}</span>
      </div>

      {/* Confidence level — plain word, no number. */}
      <div className="flex items-center gap-2 flex-wrap mt-2">
        <Chip>{confLabel} confidence</Chip>
        <Chip tone={fresh.tone}>{fresh.label}</Chip>
      </div>

      {/* Why this idea exists */}
      <div className="mt-4 max-w-narrative">
        <Label>Why this idea exists</Label>
        <p className="ink-primary leading-relaxed mt-1" style={{ fontSize: 15 }}>
          {why ?? `ArthOS rates ${rec.symbol} a ${action.toLowerCase()} based on what's working in its favor.`}
        </p>
      </div>

      {/* What supports it */}
      {support.length > 0 && (
        <div className="mt-4 max-w-narrative">
          <Label>What supports it</Label>
          <ul className="mt-1 space-y-1.5">
            {support.map((s) => (
              <li key={s} className="flex items-baseline gap-2 ink-primary" style={{ fontSize: 13.5 }}>
                <span aria-hidden style={{ color: 'var(--brand)', fontSize: 11 }}>▲</span>{s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Key risk */}
      <div className="mt-4 max-w-narrative">
        <Label>Key risk</Label>
        <p className="ink-muted leading-relaxed mt-1" style={{ fontSize: 13.5 }}>
          {keyRisk ?? 'Markets can fall as well as rise — practice it in paper first.'}
        </p>
      </div>

      <p className="ink-fainter mt-4" style={{ fontSize: 11.5 }}>
        Updated {absTime(rec.generated_at)}
        {' · '}<span style={{ color: freshColor }}>{fresh.label.toLowerCase()}</span>
      </p>

      <div className="mt-5">
        <Link
          to={`/v2/today/pick/${rec.symbol}`}
          className="inline-flex items-center gap-2 h-10 px-4 rounded-full"
          style={{ fontSize: 13, fontWeight: 600, backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)' }}
        >
          See the full idea <ArrowRight className="size-3.5" aria-hidden />
        </Link>
      </div>

      {alsoConsider.length > 0 && (
        <div className="mt-6" style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
          <p className="font-semibold uppercase mb-3" style={{
            fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
          }}>Also worth a look</p>
          <ul className="space-y-2">
            {alsoConsider.slice(0, 4).map((r) => (
              <li key={r.id} className="flex items-baseline gap-3">
                <Link to={`/v2/today/pick/${r.symbol}`}
                  className="font-mono ink-primary" style={{ fontSize: 13.5 }}>
                  {r.symbol}
                </Link>
                <span className="ink-muted" style={{ fontSize: 12.5 }}>
                  {effectiveAction(r)} · {(r.confidence_label ?? 'Medium').toLowerCase()} confidence
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </SurfaceCard>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-semibold uppercase" style={{
      fontSize: 10.5, letterSpacing: '0.12em', color: 'var(--muted-foreground)',
    }}>{children}</span>
  );
}

function Chip({ children, tone }: { children: React.ReactNode; tone?: 'good' | 'warn' }) {
  const color = tone === 'warn' ? 'oklch(0.70 0.14 75)'
    : tone === 'good' ? 'var(--brand)' : 'var(--foreground)';
  return (
    <span className="px-2.5 py-0.5 rounded-full" style={{
      fontSize: 11.5, fontWeight: 500, textTransform: 'capitalize',
      backgroundColor: `color-mix(in oklch, ${tone ? color : 'var(--brand)'} 10%, transparent)`,
      color,
      border: `1px solid color-mix(in oklch, ${tone ? color : 'var(--brand)'} 20%, transparent)`,
    }}>{children}</span>
  );
}
