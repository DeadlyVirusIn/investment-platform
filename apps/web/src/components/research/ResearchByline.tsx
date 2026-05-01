// Phase 11W (Phase F) — provenance "byline" rendered next to every
// surfaced research artifact. Provider, model id (with version),
// prompt hash (truncated), and as-of date.
//
// PROVENANCE-ONLY. NEVER renders the artifact body. NEVER renders
// any action language. NEVER renders ticker buy/sell judgment.

export interface ResearchBylineProps {
  provider: string;
  modelId?: string | null;
  modelVersion?: string | null;
  promptHash?: string | null;
  asOf?: string | null;            // ISO date
  startedAt?: string | null;       // ISO datetime
  operatorId?: string | null;
}

function _truncHash(h?: string | null, n = 10): string | null {
  if (!h) return null;
  return h.length <= n ? h : `${h.slice(0, n)}…`;
}

export default function ResearchByline(props: ResearchBylineProps) {
  const items: Array<[string, string | null | undefined]> = [
    ['provider', props.provider],
    ['model', props.modelId ? (
      props.modelVersion
        ? `${props.modelId}@${props.modelVersion}`
        : props.modelId
    ) : null],
    ['prompt_hash', _truncHash(props.promptHash)],
    ['as_of', props.asOf],
    ['operator', props.operatorId],
  ];
  return (
    <div
      className="research-byline"
      role="contentinfo"
      aria-label="Research artifact provenance"
      style={{
        color: '#616161',
        fontSize: 11,
        lineHeight: 1.5,
        marginTop: 4,
      }}
    >
      {items
        .filter(([, v]) => v !== null && v !== undefined && v !== '')
        .map(([k, v], i, arr) => (
          <span key={k} data-byline-key={k}>
            <span style={{ color: '#9e9e9e' }}>{k}=</span>
            <span style={{ color: '#424242' }}>{String(v)}</span>
            {i < arr.length - 1 ? (
              <span style={{ margin: '0 6px', color: '#bdbdbd' }}>·</span>
            ) : null}
          </span>
        ))}
    </div>
  );
}
