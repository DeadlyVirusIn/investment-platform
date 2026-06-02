// TodayOptionsHero — "Best Options Setup Today", the options counterpart to
// LiveTodayHero. Answers "what is Arth's best options idea today?" in
// seconds: leads with the strongest engine setup, then a short "also
// actionable" list. ALWAYS renders (users must always know options exists),
// with honest, trader-framed states when nothing is actionable.
//
// NO operational metrics on this surface — no universe / engine-compatible /
// incompatible counts, no raw rule_id, no conviction-floor number, no
// pipeline diagnostics. Those live in Options Diagnostics only. Read-only;
// no trade controls. UI-only.

import { Link } from 'react-router-dom';
import { SurfaceCard } from './ui/SurfaceCard';
import { useOptionsLanes } from '../lib/optionsLanes';
import { rankSetups } from '../lib/optionsPresent';
import { OptionsSetupCard, OptionsSetupRow, OPTIONS_TAB_HREF } from './OptionsSetupCard';

const AMBER = 'oklch(0.70 0.14 75)';

function StatusCard({
  label, tone, sentence, cta,
}: {
  label: string;
  tone: 'muted' | 'warn';
  sentence: string;
  cta?: boolean;
}) {
  const c = tone === 'warn' ? AMBER : 'var(--muted-foreground)';
  return (
    <SurfaceCard variant={tone === 'warn' ? 'muted' : 'default'} className="p-5">
      <div className="flex items-center justify-between gap-3 mb-2">
        <p className="font-semibold uppercase" style={{
          fontSize: 11, letterSpacing: '0.16em', color: 'var(--muted-foreground)',
        }}>Options</p>
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full" style={{
          fontSize: 11, fontWeight: 600, color: c,
          backgroundColor: `color-mix(in oklch, ${c} 14%, transparent)`,
          border: `1px solid color-mix(in oklch, ${c} 28%, transparent)`,
        }}>
          <span aria-hidden className="inline-block rounded-full" style={{ width: 6, height: 6, backgroundColor: c }} />
          {label}
        </span>
      </div>
      <p className="ink-primary" style={{ fontSize: 13.5, lineHeight: 1.6 }}>{sentence}</p>
      {cta && (
        <Link to={OPTIONS_TAB_HREF} className="inline-flex items-center gap-1.5 mt-3"
          style={{ fontSize: 12.5, color: 'var(--brand)', fontWeight: 600 }}>
          See options in Opportunities →
        </Link>
      )}
    </SurfaceCard>
  );
}

export function TodayOptionsHero() {
  const lanes = useOptionsLanes();

  // Honest non-actionable states — trader copy, no telemetry.
  switch (lanes.state) {
    case 'loading':
      return <StatusCard label="Loading…" tone="muted" sentence="Checking today's options setups…" />;
    case 'error':
      return <StatusCard label="Unavailable" tone="muted" sentence="Couldn't reach the options engine right now." />;
    case 'disabled':
      return <StatusCard label="Off" tone="muted" sentence="Options are off right now." />;
    case 'stale':
      return (
        <StatusCard
          label="Paused"
          tone="warn"
          sentence="Options paused — quotes are stale. Setups aren't validated against fresh prices right now."
        />
      );
    case 'research_only':
      return (
        <StatusCard
          label="Research only"
          tone="muted"
          sentence={`No engine setups today. ${lanes.researchCount} research idea${lanes.researchCount === 1 ? '' : 's'} to explore.`}
          cta
        />
      );
    case 'no_setups':
      return <StatusCard label="No setups" tone="muted" sentence="No options setups today." />;
  }

  // ready_engine | engine_candidates_only — at least one engine setup exists.
  const ranked = rankSetups(lanes.engine);
  const top = ranked[0];
  if (!top) {
    return <StatusCard label="No setups" tone="muted" sentence="No options setups today." />;
  }
  const also = ranked.slice(1, 4);
  const building = !top.qualified; // engine_candidates_only

  return (
    <div className="space-y-3">
      <OptionsSetupCard opt={top} featured badge="★ Best options setup today" />

      {building && (
        <p className="ink-muted" style={{ fontSize: 12, lineHeight: 1.5 }}>
          Strongest available today — conviction still building.
        </p>
      )}

      {also.length > 0 && (
        <SurfaceCard variant="default" className="p-5">
          <p className="font-semibold uppercase mb-1" style={{
            fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
          }}>Also actionable today</p>
          <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
            {also.map((o) => (
              <li key={`${o.observationId}-${o.ruleId}`}>
                <OptionsSetupRow opt={o} />
              </li>
            ))}
          </ul>
        </SurfaceCard>
      )}
    </div>
  );
}
