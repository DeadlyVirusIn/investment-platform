// Phase 11M — Lane badge.
// Small descriptive label identifying which information class a
// section belongs to. NEVER an action label. Frontend-only.

export type OptionsLaneType =
  | 'OBSERVATION'
  | 'EVALUATION'
  | 'ATTRIBUTION'
  | 'SYSTEM_STATE';

const LANE_LABELS: Record<OptionsLaneType, string> = {
  OBSERVATION:  'Observation',
  EVALUATION:   'Evaluation',
  ATTRIBUTION:  'Attribution',
  SYSTEM_STATE: 'System State',
};

export function laneLabel(lane: OptionsLaneType): string {
  return LANE_LABELS[lane];
}

export default function OptionsLaneBadge({
  lane,
}: { lane: OptionsLaneType }) {
  return (
    <span
      className="inline-flex items-center rounded-full border px-2 py-0.5
                   text-[10px] font-semibold uppercase tracking-[0.14em]"
      style={{
        color: 'var(--color-muted)',
        borderColor: 'var(--color-border)',
        background: 'var(--color-surface)',
      }}
    >
      {LANE_LABELS[lane]}
    </span>
  );
}
