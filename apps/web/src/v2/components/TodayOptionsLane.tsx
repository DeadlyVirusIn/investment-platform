// Today — Options lane. ALWAYS rendered (per product decision): users
// must always know options exists, even when stale/disabled/no setups.
// Read-only. No trade/open controls. Honest state from useOptionsAvailability.

import { Link } from 'react-router-dom';
import { SurfaceCard } from './ui/SurfaceCard';
import { useOptionsAvailability, type AvailTone } from '../lib/optionsAvailability';

const AMBER = 'oklch(0.70 0.14 75)';
function toneColor(t: AvailTone): string {
  if (t === 'good') return 'var(--brand)';
  if (t === 'warn') return AMBER;
  if (t === 'bad') return 'var(--destructive)';
  return 'var(--muted-foreground)';
}

function Pill({ label, tone }: { label: string; tone: AvailTone }) {
  const c = toneColor(tone);
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full"
      style={{
        fontSize: 11, fontWeight: 600, color: c,
        backgroundColor: `color-mix(in oklch, ${c} 14%, transparent)`,
        border: `1px solid color-mix(in oklch, ${c} 28%, transparent)`,
      }}
    >
      <span aria-hidden className="inline-block rounded-full" style={{ width: 6, height: 6, backgroundColor: c }} />
      {label}
    </span>
  );
}

export function TodayOptionsLane() {
  const a = useOptionsAvailability();

  return (
    <SurfaceCard variant="default" className="p-5">
      <div className="flex items-center justify-between gap-3 mb-2">
        <p
          className="font-semibold uppercase"
          style={{ fontSize: 11, letterSpacing: '0.16em', color: 'var(--muted-foreground)' }}
        >
          Options
        </p>
        <Pill label={a.label} tone={a.tone} />
      </div>

      <p className="ink-primary" style={{ fontSize: 13.5, lineHeight: 1.6 }}>
        {a.sentence}
      </p>

      {/* Honest universe split — visible whenever we have candidate data */}
      {a.universe > 0 && (
        <div className="flex flex-wrap gap-x-5 gap-y-1 mt-3" style={{ fontSize: 12 }}>
          <span className="ink-muted">universe <span className="ink-primary">{a.universe}</span></span>
          <span className="ink-muted">engine-compatible{' '}
            <span style={{ color: a.compatible > 0 ? 'var(--brand)' : 'var(--muted-foreground)' }}>{a.compatible}</span>
          </span>
          <span className="ink-muted">incompatible <span className="ink-primary">{a.incompatible}</span></span>
        </div>
      )}

      {a.providerVersion && (
        <p className="ink-muted mt-2 font-mono" style={{ fontSize: 11 }}>
          chain: {a.providerVersion}{a.chainStale ? ' · stale' : ''}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-4 mt-4">
        <Link
          to="/v2/opportunities"
          className="inline-flex items-center gap-1.5"
          style={{ fontSize: 12.5, color: 'var(--brand)', fontWeight: 600 }}
        >
          See options in Opportunities →
        </Link>
        <Link
          to="/v2/options"
          className="inline-flex items-center gap-1.5"
          style={{ fontSize: 12, color: 'var(--muted-foreground)' }}
        >
          Diagnostics →
        </Link>
      </div>
    </SurfaceCard>
  );
}
