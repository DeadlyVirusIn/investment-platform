// Phase 11M — Information lane wrapper.
// Visually groups a page section under one of the 4 lane types
// (Observation / Evaluation / Attribution / System State) with a
// small descriptive badge + muted top separator.
//
// Frontend-only. NEVER changes wording. NEVER controls behaviour.

import OptionsLaneBadge, { type OptionsLaneType } from './OptionsLaneBadge';

export default function OptionsLane({
  lane,
  title,
  children,
  caption,
}: {
  lane: OptionsLaneType;
  title?: string;
  caption?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className="space-y-2 pt-3"
      style={{ borderTop: '1px solid var(--color-border)' }}
    >
      <header className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <OptionsLaneBadge lane={lane} />
          {title ? (
            <h2 className="text-sm font-semibold text-zinc-100">{title}</h2>
          ) : null}
        </div>
        {caption ? (
          <span className="text-[11px] text-zinc-500">{caption}</span>
        ) : null}
      </header>
      <div>{children}</div>
    </section>
  );
}
