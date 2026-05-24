// Phase 2B — Arth's Report Card at /v2/arth.
// First-class trust surface. 8 sections + voiced summary + honesty modes.

import { useEffect, useMemo, useState } from 'react';
import { ArthosPage } from '../chrome/ArthosChrome';
import { PageHeader } from '../components/ui/PageHeader';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import { ArthVoice } from '../chrome/ArthVoice';
import { useDecisions, type Decision } from '../lib/arth/decisions';
import {
  computeTrustMetrics, accuracyPhrase, expectancyPhrase,
  TH_BEST_WORST, TH_USER_OUTCOMES, type CalibrationRow,
} from '../lib/arth/trustMetrics';
import { allCohortStats, sufficientSample, type CohortStats } from '../lib/arth/cohort';
import { ARTH_LESSONS_SEED } from '../lib/arth/lessonsLearned';
import { seedReportCardDemo } from '../lib/arth/demoSeed';
import { buildAuditTrace } from '../lib/arth/auditTrace';
import { TODAYS_DESK } from '../data/arthosData';

export function ArthReportCard() {
  // Demo seed via ?seedReportCard=1
  useEffect(() => {
    try {
      const seed = new URLSearchParams(window.location.search).get('seedReportCard');
      if (seed === '1') seedReportCardDemo();
    } catch { /* ignore */ }
  }, []);

  const decisions = useDecisions();
  const metrics = useMemo(() => computeTrustMetrics(), [decisions]);
  const cohorts = useMemo(() => allCohortStats(), [decisions]);

  return (
    <ArthosPage topBarEyebrow="Arth's Report Card">
      <PageHeader
        eyebrow="Arth's Report Card"
        title={<>The work I'm asking<br />you to trust.</>}
        description="Every call I've made. What worked, what didn't. How my confidence held up. The mistakes I've updated my own thinking from. This page updates after every trade closes — past entries are never edited."
      />

      <VoicedSummary metrics={metrics} />

      <Section1History decisions={decisions} />
      <Section2WinsLosses metrics={metrics} />
      <Section2bExpectancy metrics={metrics} cohorts={cohorts} />
      <Section3Calibration metrics={metrics} />
      <Section4OverTime decisions={decisions} />
      <Section5BestWorst metrics={metrics} />
      <Section6LessonsLearned />
      <Section7UserOutcomes metrics={metrics} />
      <Section8Transparency />
    </ArthosPage>
  );
}

// ---------------------------------------------------------------------
// Header: voiced summary
// ---------------------------------------------------------------------

function VoicedSummary({ metrics }: { metrics: ReturnType<typeof computeTrustMetrics> }) {
  let line = '';
  if (metrics.total_closed === 0) {
    line = `Too early to claim anything. ${metrics.total_calls} call${metrics.total_calls === 1 ? '' : 's'} so far, none closed. I'm publishing this anyway because you should see how I think — not so you can score me yet.`;
  } else if (metrics.total_closed < 10) {
    line = `Small sample so far: ${metrics.total_closed} closed call${metrics.total_closed === 1 ? '' : 's'}. Accuracy reads ${Math.round(metrics.overall.win_rate * 100)}% but I wouldn't trust that number until 30 closes. Read the losses first — they're more honest than the wins.`;
  } else {
    const wr = Math.round(metrics.overall.win_rate * 100);
    const e = metrics.overall.expectancy_pct;
    line = `Last 30 days: ${metrics.overall.closes} calls, ${metrics.overall.wins} wins, ${metrics.overall.losses} losses, ${metrics.overall.expired} expired. Accuracy ${wr}%. Expectancy ${e >= 0 ? '+' : ''}${e.toFixed(2)}% per call. ${e > 0 ? "I'm edge-positive on the closed sample — but read the losses, they're more honest than the wins." : "I'm edge-negative on the closed sample. Stop following me until I either ship a process update or my expectancy turns."}`;
  }

  return (
    <SurfaceCard variant="highlight" className="mb-8 p-5 lg:p-6">
      <ArthVoice mode="opening">{line}</ArthVoice>
      <div className="flex items-baseline gap-6 mt-4 ml-9 flex-wrap">
        <Stat label="Total calls" value={String(metrics.total_calls)} />
        <Stat label="Closed" value={String(metrics.total_closed)} />
        <Stat label="Open" value={String(metrics.total_open)} />
        {metrics.has_accuracy && (
          <Stat label="Accuracy" value={`${Math.round(metrics.overall.win_rate * 100)}%`} />
        )}
        {metrics.total_closed > 0 && (
          <Stat label="Expectancy" value={`${metrics.overall.expectancy_pct >= 0 ? '+' : ''}${metrics.overall.expectancy_pct.toFixed(2)}%`} />
        )}
      </div>
    </SurfaceCard>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="leading-tight">
      <p className="font-semibold uppercase" style={{
        fontSize: 10, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
      }}>{label}</p>
      <p className="font-mono ink-primary tabular-nums" style={{
        fontSize: 16, marginTop: 2,
      }}>{value}</p>
    </div>
  );
}

// ---------------------------------------------------------------------
// 1. Recommendation history
// ---------------------------------------------------------------------

function Section1History({ decisions }: { decisions: Decision[] }) {
  type Filter = 'all' | 'followed' | 'skipped' | 'wins' | 'losses';
  const [filter, setFilter] = useState<Filter>('all');

  const filtered = useMemo(() => {
    const sorted = [...decisions].sort((a, b) => b.ts.localeCompare(a.ts));
    switch (filter) {
      case 'followed': return sorted.filter((d) => d.action === 'paper_traded' || d.action === 'followed');
      case 'skipped':  return sorted.filter((d) => d.action === 'skipped');
      case 'wins':     return sorted.filter((d) => d.outcome && d.outcome.pnl_pct > 0);
      case 'losses':   return sorted.filter((d) => d.outcome && d.outcome.pnl_pct < 0);
      default:         return sorted;
    }
  }, [decisions, filter]);

  return (
    <SectionWrap n={1} title="Recommendation history">
      <div className="flex gap-2 mb-4 flex-wrap">
        {(['all', 'followed', 'skipped', 'wins', 'losses'] as Filter[]).map((f) => (
          <Chip key={f} active={filter === f} onClick={() => setFilter(f)}>{f}</Chip>
        ))}
      </div>
      {filtered.length === 0 ? (
        <p className="ink-muted italic" style={{ fontSize: 14 }}>No entries yet.</p>
      ) : (
        <div className="space-y-px">
          {filtered.slice(0, 24).map((d) => <HistoryRow key={d.id} d={d} />)}
        </div>
      )}
    </SectionWrap>
  );
}

function HistoryRow({ d }: { d: Decision }) {
  const day = d.ts.slice(0, 10);
  const o = d.outcome;
  const actionLabel =
    d.action === 'paper_traded' || d.action === 'followed' ? 'followed' :
    d.action === 'skipped' ? 'skipped' :
    d.action === 'held_cash' ? 'cash' : 'saved';
  const status = o
    ? (o.pnl_pct > 0
        ? `CLOSED +${o.pnl_pct.toFixed(1)}% in ${o.days_held}d ✓`
        : o.pnl_pct < 0
        ? `CLOSED ${o.pnl_pct.toFixed(1)}% in ${o.days_held}d ✗`
        : `Expired in ${o.days_held}d`)
    : d.action === 'paper_traded' || d.action === 'followed'
      ? 'open'
      : (d.skip_reason ? `(${d.skip_reason})` : '');
  return (
    <div className="grid grid-cols-[80px_60px_90px_80px_1fr] gap-2 items-baseline py-2"
         style={{ borderTop: '1px solid var(--border)' }}>
      <span className="font-mono ink-muted" style={{ fontSize: 12 }}>{day}</span>
      <span className="font-mono ink-primary" style={{ fontSize: 13 }}>{d.symbol}</span>
      <span className="ink-muted" style={{ fontSize: 12 }}>{d.arth_confidence ?? '—'}</span>
      <span className="ink-muted" style={{ fontSize: 12 }}>{actionLabel}</span>
      <span className="ink-primary" style={{ fontSize: 12.5 }}>{status}</span>
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} className="px-3 py-1 rounded-full" style={{
      fontSize: 12, fontWeight: 600,
      backgroundColor: active ? 'var(--brand)' : 'var(--card)',
      color: active ? 'var(--brand-foreground)' : 'var(--foreground)',
      border: '1px solid var(--border)',
    }}>{children}</button>
  );
}

// ---------------------------------------------------------------------
// 2. Wins and Losses
// ---------------------------------------------------------------------

function Section2WinsLosses({ metrics }: { metrics: ReturnType<typeof computeTrustMetrics> }) {
  const o = metrics.overall;
  if (o.closes === 0) {
    return (
      <SectionWrap n={2} title="Wins and losses">
        <ArthVoice mode="advisory">No closed positions yet. Counts will appear here once trades resolve.</ArthVoice>
      </SectionWrap>
    );
  }
  return (
    <SectionWrap n={2} title="Wins and losses">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Pane label="Wins" value={`${o.wins}`} sub={`avg +${o.avg_win_pct.toFixed(1)}%`} tone="pos" />
        <Pane label="Losses" value={`${o.losses}`} sub={`avg ${o.avg_loss_pct.toFixed(1)}%`} tone="neg" />
        <Pane label="Expired" value={`${o.expired}`} sub="theta-bleed" tone="muted" />
      </div>
      <p className="ink-muted mt-3" style={{ fontSize: 13 }}>
        Win/loss ratio {o.losses === 0 ? '—' : (o.wins / o.losses).toFixed(2)}
        {o.current_streak.direction !== 'none' && (
          <>  ·  current streak: {o.current_streak.count} {o.current_streak.direction === 'win' ? 'wins' : 'losses'}</>
        )}
      </p>
    </SectionWrap>
  );
}

// ---------------------------------------------------------------------
// 2b. Expectancy
// ---------------------------------------------------------------------

function Section2bExpectancy({
  metrics, cohorts,
}: {
  metrics: ReturnType<typeof computeTrustMetrics>;
  cohorts: CohortStats[];
}) {
  const o = metrics.overall;
  if (o.closes === 0) return null;

  return (
    <SectionWrap n="2b" title="Recommendation expectancy">
      <ArthVoice mode="advisory">
        Expectancy is the number to watch. If this stays positive across enough samples, my recommendations have edge. If it turns negative, stop following me regardless of what win rate says. Currently {o.expectancy_pct >= 0 ? 'positive' : 'negative'} on a {o.closes}-close sample.
      </ArthVoice>
      <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
        <Pane label="Win rate" value={`${Math.round(o.win_rate * 100)}%`} sub={`${o.wins}/${o.closes}`} tone="muted" />
        <Pane label="Avg winner" value={`+${o.avg_win_pct.toFixed(2)}%`} sub="across wins" tone="pos" />
        <Pane label="Avg loser" value={`${o.avg_loss_pct.toFixed(2)}%`} sub="across losses" tone="neg" />
        <Pane label="Expectancy" value={`${o.expectancy_pct >= 0 ? '+' : ''}${o.expectancy_pct.toFixed(2)}%`} sub="per call" tone={o.expectancy_pct >= 0 ? 'pos' : 'neg'} />
      </div>

      <div className="mt-6">
        <p className="font-semibold uppercase mb-2" style={{
          fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
        }}>By confidence bucket</p>
        {metrics.by_confidence.map((row) => <CalibBucketRow key={row.confidence} row={row} />)}
      </div>

      <div className="mt-6">
        <p className="font-semibold uppercase mb-2" style={{
          fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
        }}>By historical cohort</p>
        {cohorts.length === 0 ? (
          <p className="ink-muted italic" style={{ fontSize: 13 }}>No closed cohorts yet.</p>
        ) : (
          cohorts.map((c) => <CohortRow key={c.cohort} c={c} />)
        )}
      </div>
    </SectionWrap>
  );
}

function CalibBucketRow({ row }: { row: ReturnType<typeof computeTrustMetrics>['by_confidence'][number] }) {
  return (
    <div className="grid grid-cols-[100px_80px_80px_120px_1fr] gap-3 items-baseline py-2"
         style={{ borderTop: '1px solid var(--border)' }}>
      <span className="ink-primary uppercase" style={{ fontSize: 11.5, letterSpacing: '0.1em' }}>{row.confidence}</span>
      <span className="font-mono ink-muted tabular-nums" style={{ fontSize: 12 }}>{row.calls} calls</span>
      <span className="font-mono ink-muted tabular-nums" style={{ fontSize: 12 }}>{row.closes} closed</span>
      <span className="font-mono ink-primary tabular-nums" style={{ fontSize: 12 }}>
        {row.accuracy === null
          ? `${row.closes}/${row.closes < 5 ? '5 needed' : 'closes'}`
          : `${Math.round(row.accuracy * 100)}%`}
      </span>
      <span className="ink-muted" style={{ fontSize: 12 }}>target {row.target}</span>
    </div>
  );
}

function CohortRow({ c }: { c: CohortStats }) {
  const sufficient = sufficientSample(c);
  return (
    <div className="grid grid-cols-[2fr_70px_70px_120px] gap-3 items-baseline py-2"
         style={{ borderTop: '1px solid var(--border)' }}>
      <span className="ink-primary font-mono" style={{ fontSize: 12 }}>{c.cohort}</span>
      <span className="font-mono ink-muted" style={{ fontSize: 12 }}>{c.wins}/{c.closes}</span>
      <span className="font-mono ink-muted" style={{ fontSize: 12 }}>{c.avg_hold_days.toFixed(1)}d</span>
      <span className="font-mono ink-primary" style={{ fontSize: 12 }}>
        {sufficient ? `${c.expectancy_pct >= 0 ? '+' : ''}${c.expectancy_pct.toFixed(2)}%` : '(too early)'}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------
// 3. Confidence calibration table (denormalized of §2b)
// ---------------------------------------------------------------------

function Section3Calibration({ metrics }: { metrics: ReturnType<typeof computeTrustMetrics> }) {
  return (
    <SectionWrap n={3} title="Confidence calibration">
      <ArthVoice mode="advisory">
        Calibration tells you whether to trust my confidence labels. If I say "medium" and I'm wrong half the time, "medium" isn't medium — it's "low with confidence inflation." This is where I get held accountable for what my labels actually mean.
      </ArthVoice>
      <div className="mt-4">
        {metrics.by_confidence.map((row) => <CalibBucketRow key={row.confidence} row={row} />)}
      </div>
    </SectionWrap>
  );
}

// ---------------------------------------------------------------------
// 4. Confidence accuracy over time (weekly sparkline)
// ---------------------------------------------------------------------

function Section4OverTime({ decisions }: { decisions: Decision[] }) {
  // Bucket by ISO week.
  const buckets = useMemo(() => {
    const closes = decisions.filter((d) => d.outcome);
    const byWeek = new Map<string, Decision[]>();
    for (const d of closes) {
      const wk = isoWeek(d.outcome!.closed_at);
      const arr = byWeek.get(wk) ?? [];
      arr.push(d);
      byWeek.set(wk, arr);
    }
    return [...byWeek.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(-8);
  }, [decisions]);

  if (buckets.length === 0) {
    return (
      <SectionWrap n={4} title="Confidence accuracy over time">
        <ArthVoice mode="advisory">No weekly closes yet to plot.</ArthVoice>
      </SectionWrap>
    );
  }

  return (
    <SectionWrap n={4} title="Confidence accuracy over time">
      <div className="space-y-px">
        {buckets.map(([wk, ds]) => {
          const wins = ds.filter((d) => d.outcome!.pnl_pct > 0).length;
          const pct = ds.length === 0 ? 0 : Math.round((wins / ds.length) * 100);
          return (
            <div key={wk} className="grid grid-cols-[110px_70px_1fr_60px] gap-3 items-center py-2"
                 style={{ borderTop: '1px solid var(--border)' }}>
              <span className="font-mono ink-muted" style={{ fontSize: 12 }}>{wk}</span>
              <span className="ink-muted" style={{ fontSize: 12 }}>{ds.length} closes</span>
              <div className="h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--sage-light)' }}>
                <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: 'var(--brand)' }} />
              </div>
              <span className="font-mono ink-primary tabular-nums" style={{ fontSize: 12 }}>{pct}%</span>
            </div>
          );
        })}
      </div>
    </SectionWrap>
  );
}

function isoWeek(iso: string): string {
  const d = new Date(iso);
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil((((d.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`;
}

// ---------------------------------------------------------------------
// 5. Best and worst calls
// ---------------------------------------------------------------------

function Section5BestWorst({ metrics }: { metrics: ReturnType<typeof computeTrustMetrics> }) {
  if (metrics.total_closed < TH_BEST_WORST) {
    return (
      <SectionWrap n={5} title="Best and worst calls">
        <ArthVoice mode="advisory">Need {TH_BEST_WORST} closes before I'll call out best/worst. So far: {metrics.total_closed}.</ArthVoice>
      </SectionWrap>
    );
  }
  return (
    <SectionWrap n={5} title="Best and worst calls">
      {metrics.worst_call && (
        <SurfaceCard variant="muted" className="p-5 mb-3">
          <p className="font-semibold uppercase mb-1" style={{
            fontSize: 11, letterSpacing: '0.14em', color: 'var(--destructive)',
          }}>Worst call (showing first — honesty mandate)</p>
          <p className="font-mono ink-primary" style={{ fontSize: 14 }}>
            {metrics.worst_call.symbol}  ·  {metrics.worst_call.arth_confidence ?? '—'} confidence
          </p>
          <p className="ink-primary mt-1" style={{ fontSize: 13 }}>
            Closed {metrics.worst_call.outcome!.pnl_pct.toFixed(1)}% in {metrics.worst_call.outcome!.days_held}d
          </p>
          <p className="ink-muted mt-2 italic" style={{ fontSize: 12.5 }}>
            Thesis at the time: "{metrics.worst_call.thesis_snapshot}"
          </p>
        </SurfaceCard>
      )}
      {metrics.best_call && (
        <SurfaceCard variant="default" className="p-5">
          <p className="font-semibold uppercase mb-1" style={{
            fontSize: 11, letterSpacing: '0.14em', color: 'var(--brand)',
          }}>Best call</p>
          <p className="font-mono ink-primary" style={{ fontSize: 14 }}>
            {metrics.best_call.symbol}  ·  {metrics.best_call.arth_confidence ?? '—'} confidence
          </p>
          <p className="ink-primary mt-1" style={{ fontSize: 13 }}>
            Closed +{metrics.best_call.outcome!.pnl_pct.toFixed(1)}% in {metrics.best_call.outcome!.days_held}d
          </p>
          <p className="ink-muted mt-2 italic" style={{ fontSize: 12.5 }}>
            Thesis at the time: "{metrics.best_call.thesis_snapshot}"
          </p>
        </SurfaceCard>
      )}
    </SectionWrap>
  );
}

// ---------------------------------------------------------------------
// 6. Lessons Arth learned from mistakes
// ---------------------------------------------------------------------

function Section6LessonsLearned() {
  return (
    <SectionWrap n={6} title="Lessons I learned from mistakes">
      <ArthVoice mode="advisory">
        Visible record of how I updated my own thinking. This is the section that should earn the most trust — it proves I change my process, not just optimize my metrics.
      </ArthVoice>
      <div className="mt-4 space-y-3">
        {ARTH_LESSONS_SEED.map((l) => (
          <SurfaceCard key={l.id} variant="muted" className="p-5">
            <p className="font-mono ink-muted" style={{ fontSize: 11.5 }}>{l.date}</p>
            <p className="font-semibold ink-primary mt-1" style={{ fontSize: 13.5 }}>{l.trigger_summary}</p>
            <p className="ink-primary mt-2" style={{ fontSize: 13.5, lineHeight: 1.55 }}>{l.what_i_changed}</p>
          </SurfaceCard>
        ))}
      </div>
    </SectionWrap>
  );
}

// ---------------------------------------------------------------------
// 7. Your outcomes vs hypothetical
// ---------------------------------------------------------------------

function Section7UserOutcomes({ metrics }: { metrics: ReturnType<typeof computeTrustMetrics> }) {
  if (!metrics.has_user_outcomes) {
    return (
      <SectionWrap n={7} title="Your outcomes vs hypothetical">
        <ArthVoice mode="advisory">
          Need {TH_USER_OUTCOMES} closes before I'll compare your follow-rate to a hypothetical "follow-everything" portfolio. So far: {metrics.total_closed}.
        </ArthVoice>
      </SectionWrap>
    );
  }
  const followed = metrics.closed_decisions.filter(
    (d) => d.action === 'paper_traded' || d.action === 'followed',
  );
  const followedPnl = followed.reduce((s, d) => s + d.outcome!.pnl_pct, 0);
  const hypothetical = metrics.closed_decisions.reduce(
    (s, d) => s + d.outcome!.pnl_pct, 0,
  );
  return (
    <SectionWrap n={7} title="Your outcomes vs hypothetical">
      <p className="ink-primary" style={{ fontSize: 14, lineHeight: 1.6 }}>
        When you followed me: <strong className="font-mono">{followedPnl >= 0 ? '+' : ''}{followedPnl.toFixed(2)}%</strong> across {followed.length} trades.
        <br />
        If you'd followed every call: <strong className="font-mono">{hypothetical >= 0 ? '+' : ''}{hypothetical.toFixed(2)}%</strong> across {metrics.closed_decisions.length} trades.
      </p>
      <ArthVoice mode="advisory" className="mt-3">
        Follow rate: {Math.round(metrics.follow_rate * 100)}%. If your "follow-everything" line is higher, your skip filter is too tight — read the skip column in section 1 and decide if any of those should have stayed in.
      </ArthVoice>
    </SectionWrap>
  );
}

// ---------------------------------------------------------------------
// 8. Process transparency
// ---------------------------------------------------------------------

function Section8Transparency() {
  const [showTrace, setShowTrace] = useState(false);
  const sampleRec = TODAYS_DESK.stocks.find((r) => r.placeable) ?? TODAYS_DESK.stocks[0];
  const trace = useMemo(() => sampleRec ? buildAuditTrace(sampleRec) : null, [sampleRec]);
  return (
    <SectionWrap n={8} title="Process transparency">
      <ul className="space-y-2 ink-primary" style={{ fontSize: 13.5, lineHeight: 1.5 }}>
        <li>Every recommendation carries an audit trace — the 7 stages from raw data to recommendation.</li>
        <li>Mind changes are logged with before/after signals.</li>
        <li>Filtered candidates are visible — what I left out today.</li>
        <li>This page updates after every trade closes. Past entries are never edited.</li>
      </ul>
      <button onClick={() => setShowTrace((s) => !s)} className="mt-4 inline-flex items-center gap-2 px-4 h-10 rounded-full" style={{
        fontSize: 13, fontWeight: 600,
        backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)',
      }}>
        {showTrace ? 'Hide example audit trace' : 'Show me an example audit trace'}
      </button>
      {showTrace && trace && (
        <SurfaceCard variant="muted" className="p-5 mt-4">
          <p className="font-semibold uppercase mb-3" style={{
            fontSize: 11, letterSpacing: '0.14em', color: 'var(--brand)',
          }}>Audit trace · {trace.symbol}</p>
          <div className="space-y-3">
            {trace.stages.map((s) => (
              <div key={s.num}>
                <p className="font-semibold ink-primary" style={{ fontSize: 13 }}>
                  {s.num}. {s.title}
                </p>
                <ul className="mt-1 ml-4 ink-muted" style={{ fontSize: 12.5, lineHeight: 1.5, listStyle: 'disc' }}>
                  {s.bullets.map((b, i) => <li key={i}>{b}</li>)}
                </ul>
              </div>
            ))}
          </div>
          {trace.uncertainty_signals.length > 0 && (
            <>
              <p className="font-semibold ink-primary mt-4" style={{ fontSize: 13 }}>What I might be wrong about</p>
              <ul className="mt-1 ml-4 ink-muted" style={{ fontSize: 12.5, lineHeight: 1.5, listStyle: 'disc' }}>
                {trace.uncertainty_signals.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </>
          )}
        </SurfaceCard>
      )}
    </SectionWrap>
  );
}

// ---------------------------------------------------------------------
// Section wrapper + Pane
// ---------------------------------------------------------------------

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
  label: string; value: string; sub: string;
  tone: 'pos' | 'neg' | 'muted';
}) {
  const valColor =
    tone === 'pos' ? 'var(--brand)' :
    tone === 'neg' ? 'var(--destructive)' :
    'var(--foreground)';
  return (
    <SurfaceCard variant="default" className="p-4">
      <p className="font-semibold uppercase" style={{
        fontSize: 10, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
      }}>{label}</p>
      <p className="font-mono tabular-nums mt-1" style={{
        fontSize: 22, color: valColor, lineHeight: 1.1,
      }}>{value}</p>
      <p className="ink-muted" style={{ fontSize: 12, marginTop: 4 }}>{sub}</p>
    </SurfaceCard>
  );
}
