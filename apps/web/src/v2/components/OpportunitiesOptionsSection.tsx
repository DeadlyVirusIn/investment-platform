// Opportunities — Options section. Phase A: leads with actionable setups,
// mirroring the stock desk. Answers "what are the best actionable options
// setups right now?"
//
//   Top options setup     — the strongest engine setup (featured)
//   Also actionable today — remaining engine setups (compact rows)
//   Research ideas        — directional structures the engine does NOT trade,
//                           collapsed + labelled educational
//
// REMOVED (moved to Options Diagnostics): universe / engine-compatible /
// engine-incompatible counts, per-structure table, "engine-tradeable" banner,
// raw rule_id, conviction-floor number, chain/provider telemetry. Read-only;
// no trade controls. UI-only.

import { SurfaceCard } from './ui/SurfaceCard';
import { useOptionsLanes } from '../lib/optionsLanes';
import { rankSetups } from '../lib/optionsPresent';
import { OptionsSetupCard, OptionsSetupRow } from './OptionsSetupCard';

const AMBER = 'oklch(0.70 0.14 75)';

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="font-semibold uppercase mb-3" style={{
      fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
    }}>{children}</p>
  );
}

function StatusCard({ tone, sentence }: { tone: 'muted' | 'warn'; sentence: string }) {
  return (
    <SurfaceCard variant={tone === 'warn' ? 'muted' : 'default'} className="p-5">
      <p
        className={tone === 'warn' ? '' : 'ink-primary'}
        style={{ fontSize: 13.5, lineHeight: 1.6, color: tone === 'warn' ? AMBER : undefined }}
      >
        {sentence}
      </p>
    </SurfaceCard>
  );
}

function RowList({ items }: { items: ReturnType<typeof rankSetups> }) {
  return (
    <SurfaceCard variant="default" className="p-5">
      <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
        {items.map((o) => (
          <li key={`${o.observationId}-${o.ruleId}`}>
            <OptionsSetupRow opt={o} />
          </li>
        ))}
      </ul>
    </SurfaceCard>
  );
}

export function OpportunitiesOptionsSection() {
  const lanes = useOptionsLanes();

  // Honest non-actionable states — trader copy, no telemetry.
  if (lanes.state === 'loading') return <StatusCard tone="muted" sentence="Loading options setups…" />;
  if (lanes.state === 'error') return <StatusCard tone="muted" sentence="Options unavailable right now." />;
  if (lanes.state === 'disabled') return <StatusCard tone="muted" sentence="Options are off right now." />;
  if (lanes.state === 'stale') {
    return (
      <StatusCard
        tone="warn"
        sentence="Options paused — quotes are stale. Setups aren't validated against fresh prices right now."
      />
    );
  }

  const engine = rankSetups(lanes.engine);
  const research = rankSetups(lanes.research);
  const top = engine[0];
  const also = engine.slice(1);

  if (!top && research.length === 0) {
    return <StatusCard tone="muted" sentence="No options setups today." />;
  }

  return (
    <div className="space-y-7">
      {top ? (
        <div>
          <GroupLabel>Top options setup</GroupLabel>
          <OptionsSetupCard opt={top} featured showCta={false} />
          {!top.qualified && (
            <p className="ink-muted mt-2" style={{ fontSize: 12, lineHeight: 1.5 }}>
              Strongest available today — conviction still building.
            </p>
          )}
        </div>
      ) : (
        <StatusCard tone="muted" sentence="No engine setups today — research ideas below." />
      )}

      {also.length > 0 && (
        <div>
          <GroupLabel>Also actionable today</GroupLabel>
          <RowList items={also} />
        </div>
      )}

      {research.length > 0 && (
        <details>
          <summary className="cursor-pointer select-none" style={{ listStyle: 'none' }}>
            <span className="font-semibold uppercase" style={{
              fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
            }}>
              Research ideas ({research.length}) — educational, not engine-traded ▾
            </span>
          </summary>
          <div className="mt-3">
            <RowList items={research.slice(0, 12)} />
            {research.length > 12 && (
              <p className="ink-muted mt-2" style={{ fontSize: 12 }}>
                +{research.length - 12} more research idea{research.length - 12 === 1 ? '' : 's'}.
              </p>
            )}
          </div>
        </details>
      )}
    </div>
  );
}
