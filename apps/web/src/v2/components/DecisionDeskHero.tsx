// Phase 2C — Decision Desk hero card.
//
// Every rec must explicitly answer the 6 mandated questions. The card is
// laid out so a novice can grasp the recommendation in ~10 seconds:
//
//   1. Ticker + structure + ★ Arth's pick badge + risk + confidence
//   2. One-sentence Arth take (the thesis paragraph, voiced)
//   3. Why this idea? · Why now? · Why not the alternatives?
//   4. What would invalidate it?
//   5. How similar ideas performed historically (with honesty mode)
//   6. Why not cash? (always present)
//   7. Confidence explained (supporting + limiting evidence)
//   8. Decision row + Why-for-you + audit-trace link

import { useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { SurfaceCard } from './ui/SurfaceCard';
import { ArthVoice } from '../chrome/ArthVoice';
import { useUserPrefs } from '../state/UserPrefsContext';
import { usePaperBook } from '../state/PaperBook';
import { saveReflection } from '../lib/reflections';
import { dispatch } from '../lib/arth/dispatcher';
import { addMemory, useMemoryNotes } from '../lib/arth/memory';
import { recordDecision, decisionForToday } from '../lib/arth/decisions';
import { resolveWhyForYou } from '../lib/arth/whyForYou';
import { resolveWhyNotCash } from '../lib/arth/whyNotCash';
import { classifyCohort, cohortStats, sufficientSample } from '../lib/arth/cohort';
import { lessonForSkipReason } from '../lib/arth/lessonRecommender';
import { InlineLessonCard } from './InlineLessonCard';
import type { Recommendation } from '../data/arthosData';
import type { LessonHit } from '../lib/arth/lessonRecommender';

const SKIP_REASONS = [
  'Too risky',
  "Don't understand the structure",
  'Already too exposed here',
  'Earnings risk',
  'Not interested in this name',
  'Bad timing',
];

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function DecisionDeskHero({
  rec,
}: {
  rec: Recommendation;
  allRecs?: Recommendation[];
}) {
  const { watchlist, topics, level } = useUserPrefs();
  const memory = useMemoryNotes();
  const paper = usePaperBook();

  const existing = decisionForToday(rec.symbol);
  const [stage, setStage] = useState<'idle' | 'skip' | 'reflect' | 'done'>(
    existing ? 'done' : 'idle',
  );
  const [skipFree, setSkipFree] = useState('');
  const [reflectionText, setReflectionText] = useState('');
  const [doneAction, setDoneAction] = useState<string | null>(
    existing?.action ?? null,
  );
  // Phase 2D — contextual lesson surfaced after skip-with-reason.
  const [lessonHit, setLessonHit] = useState<LessonHit | null>(null);

  const why = resolveWhyForYou({ rec, watchlist, topics, level, memory });
  const cash = resolveWhyNotCash(rec);
  const cohortKey = classifyCohort(rec);
  const cohort = cohortStats(cohortKey);

  // ── Action handlers ─────────────────────────────────────────────
  function onFollow() {
    const result = paper.openFromRec(rec);
    if (!result.ok) {
      setDoneAction('error:' + (result.reason ?? 'unknown'));
      setStage('done');
      return;
    }
    recordDecision({
      rec,
      rec_id: rec.symbol,
      symbol: rec.symbol,
      action: 'paper_traded',
      thesis_snapshot: rec.paragraph,
      arth_confidence: rec.confidence_level,
    });
    dispatch('decide', 'card_paper_traded', rec.symbol, undefined,
      { idempotency_key: `paper-${rec.symbol}-${today()}` });
    addMemory({
      category: 'seen',
      text: `You opened a paper trade on ${rec.symbol} (${rec.actionLabel}).`,
      source: 'decision',
    });
    setDoneAction('paper_traded');
    setStage('reflect');
  }
  function onSave() {
    recordDecision({
      rec, rec_id: rec.symbol, symbol: rec.symbol,
      action: 'saved', thesis_snapshot: rec.paragraph,
      arth_confidence: rec.confidence_level,
    });
    dispatch('decide', 'card_saved', rec.symbol, undefined,
      { idempotency_key: `saved-${rec.symbol}-${today()}` });
    setDoneAction('saved');
    setStage('done');
  }
  function onSkipSubmit(reason: string) {
    recordDecision({
      rec, rec_id: rec.symbol, symbol: rec.symbol,
      action: 'skipped', skip_reason: reason,
      thesis_snapshot: rec.paragraph,
      arth_confidence: rec.confidence_level,
    });
    dispatch('decide', 'card_skipped', rec.symbol, { reason },
      { idempotency_key: `skip-${rec.symbol}-${today()}` });
    saveReflection({
      kind: 'thesis-review',
      targetId: `skip-${rec.symbol}-${Date.now()}`,
      prompt: `Why I skipped ${rec.symbol}`,
      body: reason,
    });
    dispatch('reflect', 'reflection_written', rec.symbol);
    // Phase 2D — surface a contextual lesson tied to the skip reason.
    const hit = lessonForSkipReason(reason);
    if (hit) setLessonHit(hit);
    setDoneAction('skipped');
    setStage('done');
  }
  function onReflectSubmit() {
    if (!reflectionText.trim()) { setStage('done'); return; }
    saveReflection({
      kind: 'paper-trade-review',
      targetId: `follow-${rec.symbol}-${Date.now()}`,
      prompt: `What I expect from ${rec.symbol}`,
      body: reflectionText.trim(),
    });
    dispatch('reflect', 'reflection_written', rec.symbol);
    setStage('done');
  }

  // ── Header chips ────────────────────────────────────────────────
  const confLabel = rec.confidence_level ?? 'medium';

  return (
    <SurfaceCard variant="highlight" className="p-6 lg:p-7">
      {/* 1. Title + chips */}
      <div className="flex items-baseline gap-3 flex-wrap mb-1">
        {rec.is_arth_pick && (
          <span className="px-2 py-0.5 rounded-full font-semibold uppercase"
            style={{
              fontSize: 10, letterSpacing: '0.14em',
              backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)',
            }}>★ My favorite idea today</span>
        )}
      </div>
      <div className="flex items-baseline gap-3 flex-wrap mt-1">
        <span className="font-mono ink-primary tabular-nums" style={{ fontSize: 22 }}>
          {rec.symbol}
        </span>
        <span className="ink-muted" style={{ fontSize: 13.5 }}>{rec.actionLabel}</span>
      </div>
      <div className="flex items-center gap-2 flex-wrap mt-2">
        <Chip>{confLabel} confidence</Chip>
        {rec.hold_estimate_days_min && rec.hold_estimate_days_max && (
          <Chip>hold ~{rec.hold_estimate_days_min}-{rec.hold_estimate_days_max}d</Chip>
        )}
        {rec.maxLossPerContract && (
          <Chip>max loss ${rec.maxLossPerContract}/contract</Chip>
        )}
      </div>

      {/* 2. Thesis */}
      <p className="ink-primary leading-relaxed mt-4 max-w-narrative" style={{ fontSize: 15 }}>
        {rec.paragraph}
      </p>

      {/* 3-4-5-6-7. Answer blocks */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mt-6"
           style={{ borderTop: '1px solid var(--border)', paddingTop: 20 }}>
        <AnswerBlock title="Why this idea" bullets={rec.why_this_idea} />
        <AnswerBlock title="Why now"        bullets={rec.why_now} />
        <AnswerBlock title="Why not the alternatives"
          bullets={(rec.why_not_others ?? []).map((o) => `${o.rec_id}: ${o.reason}`)} />
      </div>

      <div className="mt-5" style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
        <AnswerBlock title="What would invalidate it" bullets={rec.invalidate_conditions} />
      </div>

      <div className="mt-5" style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
        <p className="font-semibold uppercase mb-2" style={{
          fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
        }}>How similar ideas have performed</p>
        {sufficientSample(cohort) ? (
          <p className="ink-primary" style={{ fontSize: 13.5, lineHeight: 1.55 }}>
            My last {cohort.closes} {cohortKey.replace(/_/g, ' ')} setups:&nbsp;
            <strong>{cohort.wins} wins</strong> (avg +{cohort.avg_win_pct.toFixed(1)}%)
            · <strong>{cohort.losses} losses</strong> (avg {cohort.avg_loss_pct.toFixed(1)}%)
            {cohort.expired > 0 && <> · {cohort.expired} expired</>}.
            &nbsp;Avg hold {cohort.avg_hold_days.toFixed(1)} days. Expectancy&nbsp;
            <strong>{cohort.expectancy_pct >= 0 ? '+' : ''}{cohort.expectancy_pct.toFixed(2)}%</strong>
            &nbsp;per call.
          </p>
        ) : (
          <p className="ink-muted italic" style={{ fontSize: 13 }}>
            I've only made {cohort.closes} call{cohort.closes === 1 ? '' : 's'} like this so far.
            Too early to claim a pattern.
          </p>
        )}
      </div>

      <div className="mt-5" style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
        <p className="font-semibold uppercase mb-2" style={{
          fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
        }}>Why not cash?</p>
        <p className="ink-primary" style={{ fontSize: 13.5, lineHeight: 1.55 }}>
          {cash.line}
        </p>
      </div>

      {/* Confidence explained */}
      <div className="mt-5" style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
        <p className="font-semibold uppercase mb-3" style={{
          fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
        }}>Confidence explained — {confLabel}</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <ConfPanel title="What backs it up" tone="pos" bullets={rec.confidence_supporting} />
          <ConfPanel title="What limits it"   tone="neg" bullets={rec.confidence_limiting} />
        </div>
      </div>

      {/* Why for you (existing) */}
      <div className="mt-5" style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
        <ArthVoice mode="advisory">{why.line}</ArthVoice>
      </div>

      {/* Decision row + skip flow + reflection */}
      <div className="mt-5">
        {stage === 'idle' && (
          <div className="flex items-center gap-2 flex-wrap">
            <PrimaryBtn onClick={onFollow}>
              Paper trade this <ArrowRight className="size-3.5" aria-hidden />
            </PrimaryBtn>
            <SecondaryBtn onClick={onSave}>Save for later</SecondaryBtn>
            <SecondaryBtn onClick={() => setStage('skip')}>Skip — tell me why</SecondaryBtn>
          </div>
        )}
        {stage === 'skip' && (
          <div>
            <p className="ink-muted mb-3" style={{ fontSize: 13 }}>
              Pick the one that fits best — or type your own:
            </p>
            <div className="flex flex-wrap gap-2 mb-3">
              {SKIP_REASONS.map((r) => (
                <button key={r} onClick={() => onSkipSubmit(r)} className="px-3 py-1.5 rounded-full" style={{
                  fontSize: 12.5,
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--card)',
                  color: 'var(--foreground)',
                }}>{r}</button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <input type="text" value={skipFree} onChange={(e) => setSkipFree(e.target.value)}
                placeholder="…tell Arth more" className="flex-1 px-3 py-2 rounded-md" style={{
                  fontSize: 13, border: '1px solid var(--border)',
                  backgroundColor: 'var(--background)', color: 'var(--foreground)',
                }} />
              <PrimaryBtn onClick={() => skipFree.trim() && onSkipSubmit(skipFree.trim())}>
                Tell Arth
              </PrimaryBtn>
            </div>
          </div>
        )}
        {stage === 'reflect' && (
          <div>
            <ArthVoice mode="responsive">
              Logged. I'll check in when this resolves. One sentence — what do
              you expect from {rec.symbol}? Helps me read you.
            </ArthVoice>
            <div className="flex items-start gap-2 mt-3">
              <textarea value={reflectionText} onChange={(e) => setReflectionText(e.target.value)}
                placeholder="I expect…" rows={2} className="flex-1 px-3 py-2 rounded-md" style={{
                  fontSize: 14, border: '1px solid var(--border)',
                  backgroundColor: 'var(--background)', color: 'var(--foreground)',
                  fontFamily: "'Inter', ui-sans-serif, system-ui, sans-serif", resize: 'vertical',
                }} />
              <PrimaryBtn onClick={onReflectSubmit}>
                {reflectionText.trim() ? 'Save' : 'Skip'}
              </PrimaryBtn>
            </div>
          </div>
        )}
        {stage === 'done' && (
          <DoneState action={doneAction} symbol={rec.symbol} />
        )}
      </div>

      {/* Phase 2D — contextual lesson chained after skip-with-reason. */}
      {lessonHit && stage === 'done' && (
        <div className="mt-5">
          <InlineLessonCard hit={lessonHit} onDismiss={() => setLessonHit(null)} />
        </div>
      )}
    </SurfaceCard>
  );
}

// ── Sub-components ────────────────────────────────────────────────

function AnswerBlock({ title, bullets }: { title: string; bullets?: string[] }) {
  return (
    <div>
      <p className="font-semibold uppercase mb-2" style={{
        fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
      }}>{title}</p>
      <ul className="space-y-1.5">
        {(bullets ?? []).map((b, i) => (
          <li key={i} className="ink-primary leading-relaxed" style={{
            fontSize: 13, paddingLeft: 14, position: 'relative',
          }}>
            <span aria-hidden style={{
              position: 'absolute', left: 0, top: 8, width: 5, height: 5,
              borderRadius: 999, backgroundColor: 'var(--brand)',
            }} />
            {b}
          </li>
        ))}
        {(!bullets || bullets.length === 0) && (
          <li className="ink-muted italic" style={{ fontSize: 12.5 }}>(not specified)</li>
        )}
      </ul>
    </div>
  );
}

function ConfPanel({ title, tone, bullets }: {
  title: string; tone: 'pos' | 'neg'; bullets?: string[];
}) {
  const accent = tone === 'pos' ? 'var(--brand)' : 'var(--destructive)';
  return (
    <SurfaceCard variant="muted" className="p-4">
      <p className="font-semibold uppercase mb-2" style={{
        fontSize: 10, letterSpacing: '0.14em', color: accent,
      }}>{title}</p>
      <ul className="space-y-1.5">
        {(bullets ?? []).map((b, i) => (
          <li key={i} className="ink-primary leading-snug" style={{
            fontSize: 12.5, paddingLeft: 12, position: 'relative',
          }}>
            <span aria-hidden style={{
              position: 'absolute', left: 0, top: 7, width: 4, height: 4,
              borderRadius: 999, backgroundColor: accent,
            }} />
            {b}
          </li>
        ))}
      </ul>
    </SurfaceCard>
  );
}

function DoneState({ action, symbol }: { action: string | null; symbol: string }) {
  let line = '';
  if (action === 'paper_traded') {
    line = `Open in your paper book. I'll watch ${symbol} and check in when it resolves.`;
  } else if (action === 'saved') {
    line = `Saved. I'll surface ${symbol} again tomorrow if the setup still holds.`;
  } else if (action === 'skipped') {
    line = `Got it. I'll bias against setups like this tomorrow.`;
  } else if (action?.startsWith('error:')) {
    line = `Couldn't open the trade — ${action.slice(6)}.`;
  } else {
    line = 'Logged.';
  }
  return <ArthVoice mode="responsive">{line}</ArthVoice>;
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="px-2.5 py-0.5 rounded-full" style={{
      fontSize: 11.5, fontWeight: 500,
      backgroundColor: 'color-mix(in oklch, var(--brand) 10%, transparent)',
      color: 'var(--foreground)',
      border: '1px solid color-mix(in oklch, var(--brand) 20%, transparent)',
    }}>{children}</span>
  );
}

function PrimaryBtn({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} className="inline-flex items-center justify-center gap-2 h-10 px-4 rounded-full" style={{
      fontSize: 13, fontWeight: 600,
      backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)',
    }}>{children}</button>
  );
}

function SecondaryBtn({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} className="inline-flex items-center justify-center gap-2 h-10 px-4 rounded-full" style={{
      fontSize: 13, fontWeight: 500,
      border: '1px solid var(--border)', backgroundColor: 'transparent',
      color: 'var(--foreground)',
    }}>{children}</button>
  );
}
