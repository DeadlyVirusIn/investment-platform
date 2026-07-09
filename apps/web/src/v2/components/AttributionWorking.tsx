// Sprint 2 (Elite ArthOS) — dev-only "See the working" attribution card.
// Renders ONLY when VITE_DEV_ATTRIBUTION === '1' (absent by default: this
// never appears in any normal build). It supplements — never replaces —
// the existing narrative explanation, and it is honest about scope: the
// attributions come from the research (shadow) model, not the rule engine
// that published the idea (see docs/research/ATTRIBUTION_PROTOTYPE.md).

type InfluenceRow = { label: string; relative_influence: number };

export type AttributionPayload = {
  headline: string;
  supporting: InfluenceRow[];
  cautionary: InfluenceRow[];
  model_version: string;
  feature_schema_version: string;
  as_of: string;
  limitations: string;
  scope_note: string;
};

export function attributionDevEnabled(): boolean {
  return import.meta.env.VITE_DEV_ATTRIBUTION === '1';
}

function Bar({ share, tone }: { share: number; tone: 'up' | 'down' }) {
  return (
    <div className="h-1.5 rounded-full" style={{
      width: `${Math.max(4, Math.round(share * 100))}%`,
      backgroundColor: tone === 'up' ? 'var(--brand)' : 'oklch(0.62 0.19 25)',
      opacity: 0.85,
    }} />
  );
}

export function AttributionWorking({ payload }: { payload: AttributionPayload }) {
  if (!attributionDevEnabled()) return null;
  return (
    <section className="mt-8 rounded-xl px-5 py-4 max-w-narrative" style={{
      border: '1px dashed color-mix(in oklch, var(--brand) 35%, transparent)',
    }}>
      <p className="text-meta ink-fainter mb-1">DEV PREVIEW — {payload.scope_note}</p>
      <h3 className="ink-primary text-[14px] font-semibold mb-3">{payload.headline}</h3>

      <p className="text-meta ink-muted mb-1.5">Strongest supporting factors</p>
      {payload.supporting.map((r) => (
        <div key={r.label} className="mb-2">
          <p className="text-[12.5px] ink-primary mb-1">{r.label}</p>
          <Bar share={r.relative_influence} tone="up" />
        </div>
      ))}

      <p className="text-meta ink-muted mb-1.5 mt-4">Strongest cautionary factors</p>
      {payload.cautionary.map((r) => (
        <div key={r.label} className="mb-2">
          <p className="text-[12.5px] ink-primary mb-1">{r.label}</p>
          <Bar share={r.relative_influence} tone="down" />
        </div>
      ))}

      <p className="ink-fainter text-[11.5px] leading-relaxed mt-4">{payload.limitations}</p>
      <p className="ink-fainter text-[10.5px] mt-2 tabular-nums">
        model {payload.model_version} · features {payload.feature_schema_version} · as of {payload.as_of}
      </p>
    </section>
  );
}
