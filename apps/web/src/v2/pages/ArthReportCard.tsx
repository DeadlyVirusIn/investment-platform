// Arth's Report Card — P1 honest rewire (Option B).
//
// There is NO audited published-call outcome lineage yet, so this page must
// NOT present win-rate / expectancy / accuracy / calibration as "Arth's
// record". Those were previously computed from LOCAL browser decisions
// (computeTrustMetrics / allCohortStats) and are removed. Instead:
//   • an honest "experimental — track record not yet established" banner;
//   • REAL backend engine activity (recommendations published today, via
//     /recommendations + /recommendations/diagnostics);
//   • the user's OWN decisions, clearly labelled local-only, with NO
//     win-rate/expectancy claims.
// No localStorage performance metrics, no fabricated cohort statistics.

import { ArthosPage } from '../chrome/ArthosChrome';
import { MeTabs } from './components/MeTabs';
import { PageHeader } from '../components/ui/PageHeader';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import { ArthVoice } from '../chrome/ArthVoice';
import { useDecisions, type Decision } from '../lib/arth/decisions';
import {
  useTodaysRecommendations,
  useRecommendationDiagnostics,
  effectiveAction,
} from '@/lib/operator/hooks';

export function ArthReportCard() {
  const { data: recsData } = useTodaysRecommendations();
  const { data: diag } = useRecommendationDiagnostics();
  const decisions = useDecisions();

  const recs = recsData?.recommendations ?? [];
  const liveBuys = recs.filter((r) => effectiveAction(r) === 'Buy').length;
  const evaluated = diag?.total ?? null;
  const dist = diag?.action_distribution ?? {};

  return (
    <ArthosPage topBarEyebrow="Arth's Report Card">
      <PageHeader
        eyebrow="Arth's Report Card"
        title={<>The work, in<br />the open.</>}
        description="Honest status of the engine. There is not yet an audited published-call track record — so this page shows what the engine is actually doing today and what is still accruing, not an accuracy score I can't back."
      />

      <MeTabs />

      {/* Honest experimental banner — replaces the old fabricated accuracy summary */}
      <SurfaceCard variant="highlight" className="mb-8 p-5 lg:p-6">
        <ArthVoice mode="opening">
          Experimental. There is no verified win-rate or expectancy yet because
          no published calls have a resolved, audited outcome lineage. I won't
          manufacture an accuracy number from local activity. When real closed
          outcomes exist, this page will show them — losses first.
        </ArthVoice>
      </SurfaceCard>

      {/* 1. Real engine activity (backend) */}
      <SectionWrap n={1} title="What the engine did today (live)">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Pane label="Evaluated" value={evaluated != null ? String(evaluated) : '—'} sub="recommendations" tone="muted" />
          <Pane label="Actionable Buys" value={String(liveBuys)} sub="effective" tone={liveBuys > 0 ? 'pos' : 'muted'} />
          <Pane label="Hold" value={String(dist['Hold'] ?? 0)} sub="this batch" tone="muted" />
          <Pane label="Trim" value={String(dist['Trim'] ?? 0)} sub="this batch" tone="muted" />
        </div>
        <p className="ink-fainter italic mt-4 max-w-narrative" style={{ fontSize: 12.5 }}>
          Live from the recommendation engine. These are activity counts, not a performance claim.
        </p>
      </SectionWrap>

      {/* 2. Outcome lineage status — explicitly not-yet-established */}
      <SectionWrap n={2} title="Published-call accuracy">
        <ArthVoice mode="advisory">
          Not established yet. Accuracy, expectancy, and calibration require
          resolved outcomes tied to published calls — that lineage isn't wired
          to a backend source of truth. Until it is, no number appears here.
        </ArthVoice>
      </SectionWrap>

      {/* 3. The user's OWN decisions — clearly local, no performance claims */}
      <SectionWrap n={3} title="Your decisions (saved on this device)">
        <p className="ink-muted leading-relaxed max-w-narrative mb-4" style={{ fontSize: 13.5 }}>
          These are decisions you logged in this browser. They are local to you
          and are NOT Arth's track record — no win-rate is computed from them.
        </p>
        {decisions.length === 0 ? (
          <p className="ink-muted italic" style={{ fontSize: 14 }}>No decisions logged yet.</p>
        ) : (
          <div className="space-y-px">
            {[...decisions].sort((a, b) => b.ts.localeCompare(a.ts)).slice(0, 20).map((d) => (
              <DecisionRow key={d.id} d={d} />
            ))}
          </div>
        )}
      </SectionWrap>

      {/* 4. Process transparency — explanatory, no fabricated metrics */}
      <SectionWrap n={4} title="How recommendations are produced">
        <ul className="space-y-2 ink-primary" style={{ fontSize: 13.5, lineHeight: 1.5 }}>
          <li>Each recommendation is scored by the engine (composite + family scores) and carries a thesis.</li>
          <li>Policy adjustments (e.g. volatility damping) can change the effective action — both are shown on the pick.</li>
          <li>Recommendations expose confidence, generated_at, and stale/fresh state.</li>
          <li>An audited closed-outcome track record is not yet established; this page will surface it honestly when it is.</li>
        </ul>
      </SectionWrap>
    </ArthosPage>
  );
}

function DecisionRow({ d }: { d: Decision }) {
  const day = d.ts.slice(0, 10);
  const actionLabel =
    d.action === 'paper_traded' || d.action === 'followed' ? 'followed (local)' :
    d.action === 'skipped' ? 'skipped' :
    d.action === 'held_cash' ? 'cash' : 'saved';
  return (
    <div className="grid grid-cols-[90px_70px_1fr] gap-2 items-baseline py-2"
         style={{ borderTop: '1px solid var(--border)' }}>
      <span className="font-mono ink-muted" style={{ fontSize: 12 }}>{day}</span>
      <span className="font-mono ink-primary" style={{ fontSize: 13 }}>{d.symbol}</span>
      <span className="ink-muted" style={{ fontSize: 12.5 }}>{actionLabel}</span>
    </div>
  );
}

function SectionWrap({ n, title, children }: {
  n: number | string; title: string; children: React.ReactNode;
}) {
  return (
    <section className="mb-12">
      <div className="flex items-baseline gap-3 mb-4">
        <span className="font-mono ink-muted" style={{ fontSize: 12 }}>{String(n).padStart(2, '0')}</span>
        <h2 className="font-display ink-primary" style={{
          fontSize: 22, lineHeight: 1.2,
          fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
        }}>{title}</h2>
      </div>
      {children}
    </section>
  );
}

function Pane({ label, value, sub, tone }: {
  label: string; value: string; sub: string; tone: 'pos' | 'neg' | 'muted';
}) {
  const valColor = tone === 'pos' ? 'var(--brand)' : tone === 'neg' ? 'var(--destructive)' : 'var(--foreground)';
  return (
    <SurfaceCard variant="default" className="p-4">
      <p className="font-semibold uppercase" style={{ fontSize: 10, letterSpacing: '0.14em', color: 'var(--muted-foreground)' }}>{label}</p>
      <p className="font-mono tabular-nums mt-1" style={{ fontSize: 22, color: valColor, lineHeight: 1.1 }}>{value}</p>
      <p className="ink-muted" style={{ fontSize: 12, marginTop: 4 }}>{sub}</p>
    </SurfaceCard>
  );
}
