// Sprint 6 (Elite ArthOS) — dev-only Thesis Card prototype, fixtures only.
// Renders ONLY when VITE_DEV_THESIS === '1' (absent by default). Implements
// the five beginner blocks from THESIS_LEDGER_SPEC.md. No API, no
// migration — the fixture below mirrors the proposed schema shape.

type EvidenceRow = {
  stance: 'supports' | 'contradicts';
  summary: string;
  source: string;
  observed_at: string;
  review_status: 'approved' | 'pending';
};

export type ThesisFixture = {
  statement: string;
  status: 'forming' | 'active' | 'strengthened' | 'weakened' | 'invalidated' | 'closed';
  status_reason: string;
  wrong_if: string;
  evidence: EvidenceRow[];
  changed_since_published: string[];
  lesson: string | null;
  as_of: string;
};

export const THESIS_FIXTURE: ThesisFixture = {
  statement:
    'Ryder System keeps benefiting from steady freight demand while its price trend stays above its long-term average.',
  status: 'active',
  status_reason: 'Signals that created this idea are still true on the latest data.',
  wrong_if:
    'Price closes below $250.18, or the long-term trend turns down for two straight weeks.',
  evidence: [
    { stance: 'supports', summary: 'Trading well above its long-term average price', source: 'ArthOS price signals', observed_at: '2026-07-07', review_status: 'approved' },
    { stance: 'supports', summary: 'Short-term trend rising faster than the long-term trend', source: 'ArthOS price signals', observed_at: '2026-07-07', review_status: 'approved' },
    { stance: 'contradicts', summary: 'Day-to-day price swings are larger than usual', source: 'ArthOS volatility signals', observed_at: '2026-07-07', review_status: 'approved' },
  ],
  changed_since_published: ['No signal reversals since Jul 7.'],
  lesson: null,
  as_of: '2026-07-09',
};

export function thesisDevEnabled(): boolean {
  return import.meta.env.VITE_DEV_THESIS === '1';
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <p className="text-meta ink-muted mb-1.5">{title}</p>
      {children}
    </div>
  );
}

export function ThesisCardDev({ thesis = THESIS_FIXTURE }: { thesis?: ThesisFixture }) {
  if (!thesisDevEnabled()) return null;
  const supports = thesis.evidence.filter((e) => e.stance === 'supports' && e.review_status === 'approved');
  const contradicts = thesis.evidence.filter((e) => e.stance === 'contradicts' && e.review_status === 'approved');
  return (
    <section className="mt-8 rounded-xl px-5 py-4 max-w-narrative" style={{
      border: '1px dashed color-mix(in oklch, var(--brand) 35%, transparent)',
    }}>
      <p className="text-meta ink-fainter mb-1">
        DEV PREVIEW — THESIS LEDGER · status: {thesis.status.toUpperCase()} · as of {thesis.as_of}
      </p>

      <Block title="What ArthOS currently believes">
        <p className="ink-primary text-[14px] leading-relaxed">{thesis.statement}</p>
        <p className="ink-fainter text-[12px] mt-1">{thesis.status_reason}</p>
      </Block>

      <Block title="What supports this">
        {supports.map((e) => (
          <p key={e.summary} className="text-[12.5px] ink-primary mb-1">
            • {e.summary}{' '}
            <span className="ink-fainter text-[10.5px]">({e.source}, {e.observed_at})</span>
          </p>
        ))}
      </Block>

      <Block title="What could prove it wrong">
        <p className="text-[12.5px] ink-primary">{thesis.wrong_if}</p>
        {contradicts.map((e) => (
          <p key={e.summary} className="text-[12.5px] ink-muted mt-1">
            • Working against it: {e.summary}{' '}
            <span className="ink-fainter text-[10.5px]">({e.source}, {e.observed_at})</span>
          </p>
        ))}
      </Block>

      <Block title="What changed since the idea was published">
        {thesis.changed_since_published.map((c) => (
          <p key={c} className="text-[12.5px] ink-primary">• {c}</p>
        ))}
      </Block>

      <Block title="What we learned after the outcome">
        <p className="text-[12.5px] ink-muted">
          {thesis.lesson ?? 'This idea is still open — the lesson is written after the outcome resolves.'}
        </p>
      </Block>
    </section>
  );
}
