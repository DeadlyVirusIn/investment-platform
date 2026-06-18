// LiveTodayHero — Today's "THE ONE" rendered from the LIVE recommendation
// engine (GET /recommendations), NOT static TODAYS_DESK.
//
// Display-only (read-only). Does NOT reuse DecisionDeskHero (out of scope)
// and intentionally has no paper-trade/skip flow — it shows the real
// recommendation, confidence, freshness, generated_at and thesis. Fields
// the backend does not provide (entry/target/sizing) are simply omitted —
// never fabricated.

import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { SurfaceCard } from './ui/SurfaceCard';
import { CONFIDENCE_DOCTRINE } from '../lib/copy';
import {
  type RecApi,
  effectiveAction,
  confidenceNum,
} from '@/lib/operator/hooks';

function ageHours(iso: string | null): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  return (Date.now() - t) / 3600_000;
}

function freshness(rec: RecApi): { label: string; tone: 'good' | 'warn' } {
  const h = ageHours(rec.generated_at);
  if (rec.stale_data || (h != null && h > 30)) {
    return { label: 'Stale', tone: 'warn' };
  }
  return { label: 'Fresh', tone: 'good' };
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
  const conf = confidenceNum(rec);
  const fresh = freshness(rec);
  const freshColor = fresh.tone === 'good' ? 'var(--brand)' : 'oklch(0.70 0.14 75)';

  return (
    <SurfaceCard variant="highlight" className="p-6 lg:p-7">
      <div className="flex items-baseline gap-3 flex-wrap mb-1">
        <span className="px-2 py-0.5 rounded-full font-semibold uppercase"
          style={{
            fontSize: 10, letterSpacing: '0.14em',
            backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)',
          }}>★ Strongest setup today</span>
      </div>

      <div className="flex items-baseline gap-3 flex-wrap mt-2">
        <span className="font-mono ink-primary tabular-nums" style={{ fontSize: 24 }}>
          {rec.symbol ?? '—'}
        </span>
        <span className="ink-muted" style={{ fontSize: 14 }}>{action}</span>
      </div>

      <div className="flex items-center gap-2 flex-wrap mt-2">
        <Chip>{(rec.confidence_label ?? 'Medium')} confidence · {conf.toFixed(0)}</Chip>
        <Chip tone={fresh.tone}>{fresh.label}</Chip>
        {(rec.tags ?? []).slice(0, 3).map((t) => <Chip key={t}>{t}</Chip>)}
      </div>
      {/* P1.3 — confidence doctrine (shared SSOT) */}
      <p className="ink-fainter text-[12px] leading-relaxed mt-2 max-w-narrative">
        {CONFIDENCE_DOCTRINE}
      </p>

      {rec.thesis && (
        <p className="ink-primary leading-relaxed mt-4 max-w-narrative" style={{ fontSize: 15 }}>
          {rec.thesis}
        </p>
      )}

      <p className="ink-fainter mt-3 tabular-nums" style={{ fontSize: 11.5 }}>
        Generated {absTime(rec.generated_at)} from live market data
        {' · '}<span style={{ color: freshColor }}>{fresh.label.toLowerCase()}</span>
      </p>

      <div className="mt-5">
        <Link
          to={`/v2/today/pick/${rec.symbol}`}
          className="inline-flex items-center gap-2 h-10 px-4 rounded-full"
          style={{ fontSize: 13, fontWeight: 600, backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)' }}
        >
          See the full reasoning <ArrowRight className="size-3.5" aria-hidden />
        </Link>
      </div>

      {alsoConsider.length > 0 && (
        <div className="mt-6" style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
          <p className="font-semibold uppercase mb-3" style={{
            fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
          }}>Also actionable today</p>
          <ul className="space-y-2">
            {alsoConsider.slice(0, 4).map((r) => (
              <li key={r.id} className="flex items-baseline gap-3">
                <Link to={`/v2/today/pick/${r.symbol}`}
                  className="font-mono ink-primary" style={{ fontSize: 13.5 }}>
                  {r.symbol}
                </Link>
                <span className="ink-muted" style={{ fontSize: 12.5 }}>
                  {effectiveAction(r)} · {(r.confidence_label ?? '')} {confidenceNum(r).toFixed(0)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </SurfaceCard>
  );
}

function Chip({ children, tone }: { children: React.ReactNode; tone?: 'good' | 'warn' }) {
  const color = tone === 'warn' ? 'oklch(0.70 0.14 75)'
    : tone === 'good' ? 'var(--brand)' : 'var(--foreground)';
  return (
    <span className="px-2.5 py-0.5 rounded-full" style={{
      fontSize: 11.5, fontWeight: 500,
      backgroundColor: `color-mix(in oklch, ${tone ? color : 'var(--brand)'} 10%, transparent)`,
      color,
      border: `1px solid color-mix(in oklch, ${tone ? color : 'var(--brand)'} 20%, transparent)`,
    }}>{children}</span>
  );
}
