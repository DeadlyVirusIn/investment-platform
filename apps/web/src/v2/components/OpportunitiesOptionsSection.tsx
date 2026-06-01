// Opportunities — Options section. Read-only candidate readiness.
// Honest split: universe / engine-compatible / engine-incompatible.
// No trade/open controls. Per-structure breakdown labelled research-only
// when nothing is engine-tradeable.

import { Link } from 'react-router-dom';
import { SurfaceCard } from './ui/SurfaceCard';
import { useOptionsAvailability, type AvailTone } from '../lib/optionsAvailability';
import { DualLaneOptions } from './DualLaneOptions';

const AMBER = 'oklch(0.70 0.14 75)';
function toneColor(t: AvailTone): string {
  if (t === 'good') return 'var(--brand)';
  if (t === 'warn') return AMBER;
  if (t === 'bad') return 'var(--destructive)';
  return 'var(--muted-foreground)';
}

export function OpportunitiesOptionsSection() {
  const a = useOptionsAvailability();
  const byStructure = a.data?.candidate_universe?.by_structure ?? [];
  const c = toneColor(a.tone);

  return (
    <div className="space-y-4">
      {/* Honest banner — sets expectation before any list */}
      <SurfaceCard variant={a.state === 'ready' ? 'highlight' : 'muted'} className="p-5">
        <div className="flex items-center justify-between gap-3 mb-1.5">
          <p className="font-semibold uppercase" style={{ fontSize: 11, letterSpacing: '0.14em', color: c }}>
            {a.compatible} engine-tradeable
          </p>
          <span
            className="px-2 py-0.5 rounded-full"
            style={{
              fontSize: 11, fontWeight: 600, color: c,
              backgroundColor: `color-mix(in oklch, ${c} 14%, transparent)`,
              border: `1px solid color-mix(in oklch, ${c} 28%, transparent)`,
            }}
          >
            {a.label}
          </span>
        </div>
        <p className="ink-primary" style={{ fontSize: 13.5, lineHeight: 1.6 }}>{a.sentence}</p>
        {a.compatible === 0 && a.universe > 0 && (
          <p className="ink-muted mt-2" style={{ fontSize: 12.5, lineHeight: 1.6 }}>
            The candidates below are <strong>research only</strong> — their structures aren’t in the
            engine’s supported set, so none are executable yet.
          </p>
        )}
        {a.providerVersion && (
          <p className="ink-muted mt-2 font-mono" style={{ fontSize: 11 }}>
            chain: {a.providerVersion}{a.chainStale ? ' · stale' : ''}
          </p>
        )}
      </SurfaceCard>

      {/* Dual-lane (Phase 3): Engine-Executable Setups + Research Ideas */}
      <DualLaneOptions />

      {/* Candidate universe split */}
      {a.universe > 0 && (
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: 'Universe', value: a.universe, tone: 'muted' as AvailTone, sub: 'emitted candidates' },
            { label: 'Engine-compatible', value: a.compatible, tone: (a.compatible > 0 ? 'good' : 'muted') as AvailTone, sub: 'defined-risk supported' },
            { label: 'Engine-incompatible', value: a.incompatible, tone: (a.incompatible > 0 ? 'warn' : 'good') as AvailTone, sub: 'not yet supported' },
          ].map((s) => (
            <SurfaceCard key={s.label} variant="default" className="p-4">
              <p className="font-semibold uppercase mb-1.5" style={{ fontSize: 10, letterSpacing: '0.14em', color: 'var(--muted-foreground)' }}>
                {s.label}
              </p>
              <p className="font-display leading-none" style={{ fontSize: 22, color: toneColor(s.tone) }}>
                {s.value}
              </p>
              <p className="ink-muted mt-1.5" style={{ fontSize: 12 }}>{s.sub}</p>
            </SurfaceCard>
          ))}
        </div>
      )}

      {/* Per-structure breakdown */}
      {byStructure.length > 0 && (
        <SurfaceCard variant="default" className="p-0 overflow-x-auto">
          <table className="w-full" style={{ fontSize: 12.5, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['Structure', 'Candidates', 'Engine-compatible'].map((h) => (
                  <th key={h} className="text-left font-semibold uppercase ink-muted px-3 py-2.5 whitespace-nowrap"
                    style={{ fontSize: 10, letterSpacing: '0.1em' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {byStructure.map((s) => (
                <tr key={s.structure} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td className="px-3 py-2.5 font-mono ink-primary">{s.structure}</td>
                  <td className="px-3 py-2.5 ink-primary tabular-nums">{s.count.toLocaleString()}</td>
                  <td className="px-3 py-2.5">
                    <span style={{
                      fontSize: 11, fontWeight: 600,
                      color: s.engine_compatible ? 'var(--brand)' : 'var(--muted-foreground)',
                    }}>
                      {s.engine_compatible ? 'yes' : 'no'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </SurfaceCard>
      )}

      {a.universe === 0 && a.state !== 'loading' && (
        <SurfaceCard variant="muted" className="p-5">
          <p className="ink-muted" style={{ fontSize: 13.5 }}>No options candidates emitted yet.</p>
        </SurfaceCard>
      )}

      <Link to="/v2/options" className="inline-flex items-center gap-1.5"
        style={{ fontSize: 12, color: 'var(--muted-foreground)' }}>
        Options diagnostics →
      </Link>
    </div>
  );
}
