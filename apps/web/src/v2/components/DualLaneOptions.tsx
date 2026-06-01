// Dual-lane options surface (Phase 3, UI-only). Two honest lanes:
//   1. Engine-Executable Setups — defined-risk credit/IC the paper engine
//      can open + risk-manage. Sparse by design; honest empty state.
//   2. Research Ideas — directional structures the engine does NOT trade,
//      labelled research/educational.
// Reads family-tagged opportunities (additive API fields). Read-only — no
// trade/open controls, no flag flip, no backend change.

import { useOptionsLanes, type OptionsOpportunity, type OptionsLaneState }
  from '../lib/optionsLanes';
import { SurfaceCard } from './ui/SurfaceCard';

const AMBER = 'oklch(0.70 0.14 75)';

const STATE_BADGE: Record<OptionsLaneState, { label: string; color: string }> = {
  loading: { label: 'Loading…', color: 'var(--muted-foreground)' },
  error: { label: 'Unavailable', color: 'var(--muted-foreground)' },
  disabled: { label: 'Engine off', color: 'var(--muted-foreground)' },
  stale: { label: 'Data stale', color: AMBER },
  ready_engine: { label: 'Engine setups ready', color: 'var(--brand)' },
  engine_candidates_only: { label: 'Below conviction', color: AMBER },
  research_only: { label: 'Research only', color: 'var(--muted-foreground)' },
  no_setups: { label: 'No setups', color: 'var(--muted-foreground)' },
};

function pct(score: number): string {
  return `${Math.round(score * 100)}%`;
}

function OppCard({ o }: { o: OptionsOpportunity }) {
  const conviction = pct(o.composite_score);
  return (
    <div
      className="flex items-start justify-between gap-3 px-3.5 py-3 rounded-lg"
      style={{ border: '1px solid var(--border)' }}
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-semibold ink-primary" style={{ fontSize: 13 }}>
            {o.underlying}
          </span>
          <span className="font-mono ink-muted" style={{ fontSize: 11 }}>
            {o.rule_id}
          </span>
        </div>
        <p className="ink-muted mt-1" style={{ fontSize: 12, lineHeight: 1.5 }}>
          {o.directional_view}
        </p>
      </div>
      <div className="text-right shrink-0">
        <p
          className="font-display leading-none"
          style={{ fontSize: 16, color: o.above_floor ? 'var(--brand)' : 'var(--muted-foreground)' }}
        >
          {conviction}
        </p>
        <p className="ink-muted mt-1" style={{ fontSize: 10.5 }}>
          {o.dte}d{o.above_floor ? ' · qualified' : ''}
        </p>
      </div>
    </div>
  );
}

function LaneHeader({ title, sub, count }: { title: string; sub: string; count: number }) {
  return (
    <div className="flex items-baseline justify-between gap-3 mb-2">
      <div>
        <p className="font-semibold uppercase ink-primary"
          style={{ fontSize: 11.5, letterSpacing: '0.12em' }}>
          {title}
        </p>
        <p className="ink-muted" style={{ fontSize: 11.5 }}>{sub}</p>
      </div>
      <span className="font-display ink-muted" style={{ fontSize: 18 }}>{count}</span>
    </div>
  );
}

export function DualLaneOptions() {
  const lanes = useOptionsLanes();
  const badge = STATE_BADGE[lanes.state];

  if (lanes.isLoading) {
    return (
      <SurfaceCard variant="muted" className="p-5">
        <p className="ink-muted" style={{ fontSize: 13 }}>Loading options lanes…</p>
      </SurfaceCard>
    );
  }
  if (lanes.isError) {
    return (
      <SurfaceCard variant="muted" className="p-5">
        <p className="ink-muted" style={{ fontSize: 13 }}>Options surface unavailable.</p>
      </SurfaceCard>
    );
  }

  const engineTop = lanes.engine.slice(0, 8);
  const researchTop = [...lanes.research]
    .sort((a, b) => b.composite_score - a.composite_score)
    .slice(0, 8);

  return (
    <div className="space-y-5">
      {/* State chip */}
      <div className="flex items-center justify-end">
        <span
          className="px-2 py-0.5 rounded-full"
          style={{
            fontSize: 11, fontWeight: 600, color: badge.color,
            backgroundColor: `color-mix(in oklch, ${badge.color} 14%, transparent)`,
            border: `1px solid color-mix(in oklch, ${badge.color} 28%, transparent)`,
          }}
        >
          {badge.label}
        </span>
      </div>

      {/* ── Lane 1: Engine-Executable Setups ── */}
      <SurfaceCard
        variant={lanes.engineAboveFloor > 0 ? 'highlight' : 'default'}
        className="p-5"
      >
        <LaneHeader
          title="Engine-Executable Setups"
          sub="defined-risk · tradeable in practice"
          count={lanes.engineCount}
        />
        {lanes.engineCount === 0 ? (
          <p className="ink-muted" style={{ fontSize: 13, lineHeight: 1.6 }}>
            No engine-executable setups today. Credit/Iron-Condor structures
            aren’t being generated in the current mode — the engine lane
            activates when the generator emits defined-risk structures.
          </p>
        ) : (
          <>
            {lanes.engineAboveFloor === 0 && (
              <p className="ink-muted mb-3" style={{ fontSize: 12.5, lineHeight: 1.6 }}>
                {lanes.engineCount} candidate{lanes.engineCount === 1 ? '' : 's'} below
                the {pct(lanes.convictionFloor)} conviction floor (thin premium / low IV).
                Shown for transparency.
              </p>
            )}
            <div className="space-y-2">
              {engineTop.map((o) => <OppCard key={`${o.observation_id}-${o.rule_id}`} o={o} />)}
            </div>
          </>
        )}
      </SurfaceCard>

      {/* ── Lane 2: Research Ideas ── */}
      <SurfaceCard variant="default" className="p-5">
        <LaneHeader
          title="Research Ideas"
          sub="not engine-traded · educational"
          count={lanes.researchCount}
        />
        {lanes.researchCount === 0 ? (
          <p className="ink-muted" style={{ fontSize: 13 }}>No research ideas today.</p>
        ) : (
          <>
            <div className="space-y-2">
              {researchTop.map((o) => <OppCard key={`${o.observation_id}-${o.rule_id}`} o={o} />)}
            </div>
            {lanes.researchCount > researchTop.length && (
              <p className="ink-muted mt-3" style={{ fontSize: 12 }}>
                +{lanes.researchCount - researchTop.length} more research idea
                {lanes.researchCount - researchTop.length === 1 ? '' : 's'}.
              </p>
            )}
          </>
        )}
      </SurfaceCard>
    </div>
  );
}
