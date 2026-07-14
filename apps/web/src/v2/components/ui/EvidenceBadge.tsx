// EvidenceBadge — the canonical presentation of ArthOS's six honesty labels
// (Trust Center spec): proven / preliminary / insufficient_data /
// not_yet_evaluated / degraded / unavailable. Never color-only: every state
// carries a distinct glyph + spelled-out text, and exposes a plain-English
// meaning via title/aria-label so a beginner (or a screen reader) gets the
// same information as a sighted expert.

export type EvidenceState =
  | 'proven' | 'preliminary' | 'insufficient_data'
  | 'not_yet_evaluated' | 'degraded' | 'unavailable';

const STATES: Record<EvidenceState, {
  text: string; glyph: string; color: string; meaning: string;
}> = {
  proven: {
    text: 'Proven', glyph: '✓', color: 'var(--brand)',
    meaning: 'Backed by verifiable evidence in this environment.',
  },
  preliminary: {
    text: 'Preliminary', glyph: '◐', color: 'oklch(0.70 0.14 75)',
    meaning: 'Early evidence only — research data, not a production statistic.',
  },
  insufficient_data: {
    text: 'Insufficient data', glyph: '○', color: 'oklch(0.62 0.19 25)',
    meaning: 'Not enough samples yet to say anything honest.',
  },
  not_yet_evaluated: {
    text: 'Not evaluated', glyph: '—', color: 'var(--muted-foreground)',
    meaning: 'No evaluation has been run for this yet.',
  },
  degraded: {
    text: 'Degraded', glyph: '⚠', color: 'oklch(0.62 0.19 25)',
    meaning: 'Working, but below the expected quality right now.',
  },
  unavailable: {
    text: 'Unavailable', glyph: '∅', color: 'var(--muted-foreground)',
    meaning: 'This source is not reachable right now.',
  },
};

/** Coerce unknown backend strings safely; unknown → not_yet_evaluated. */
export function toEvidenceState(raw: string | null | undefined): EvidenceState {
  const k = (raw ?? '').toLowerCase() as EvidenceState;
  return k in STATES ? k : 'not_yet_evaluated';
}

export function EvidenceBadge({ state, size = 'md' }: {
  state: EvidenceState | string; size?: 'sm' | 'md';
}) {
  const s = STATES[toEvidenceState(typeof state === 'string' ? state : state)];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full font-semibold shrink-0"
      title={s.meaning}
      aria-label={`${s.text} — ${s.meaning}`}
      style={{
        fontSize: size === 'sm' ? 10 : 11,
        letterSpacing: '0.04em',
        textTransform: 'uppercase',
        padding: size === 'sm' ? '2px 8px' : '3px 10px',
        color: s.color,
        backgroundColor: `color-mix(in oklch, ${s.color} 11%, transparent)`,
        border: `1px solid color-mix(in oklch, ${s.color} 30%, transparent)`,
      }}
    >
      <span aria-hidden>{s.glyph}</span>
      {s.text}
    </span>
  );
}
