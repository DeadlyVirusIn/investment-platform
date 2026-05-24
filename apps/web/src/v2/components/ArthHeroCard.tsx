// Arth hero card — the See → Decide bridge.
// Wraps a Recommendation with: Arth advisory, Why-for-you, decision row,
// skip-reason inline capture, reflection prompt on follow.
//
// MVP scope (Phase 1): wires Decide → Practice → Reflect → Remember
// directly. The smallest end-to-end loop is here.

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
import type { Recommendation } from '../data/arthosData';

const SKIP_REASONS = [
  'Too risky',
  'Don\'t understand the structure',
  'Already too exposed here',
  'Earnings risk',
  'Not interested in this name',
  'Bad timing',
];

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function ArthHeroCard({ rec }: { rec: Recommendation }) {
  const { watchlist, topics, level } = useUserPrefs();
  const memory = useMemoryNotes();
  const paper = usePaperBook();

  const existing = decisionForToday(rec.symbol);
  const [stage, setStage] = useState<'idle' | 'skip' | 'reflect' | 'done'>(
    existing ? 'done' : 'idle',
  );
  const [skipReason, setSkipReason] = useState('');
  const [reflectionText, setReflectionText] = useState('');
  const [doneAction, setDoneAction] = useState<string | null>(
    existing?.action ?? null,
  );

  const why = resolveWhyForYou({ rec, watchlist, topics, level, memory });

  function onFollow() {
    const result = paper.openFromRec(rec);
    if (!result.ok) {
      // surface as a responsive Arth line; user can retry
      setDoneAction('error:' + (result.reason ?? 'unknown'));
      setStage('done');
      return;
    }
    recordDecision({
      rec,                                   // M1: cohort derived from rec
      rec_id: rec.symbol,
      symbol: rec.symbol,
      action: 'paper_traded',
      thesis_snapshot: rec.paragraph,
    });
    dispatch('decide', 'card_paper_traded', rec.symbol, undefined,
      { idempotency_key: `paper-${rec.symbol}-${today()}` });   // M2
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
      rec,
      rec_id: rec.symbol,
      symbol: rec.symbol,
      action: 'saved',
      thesis_snapshot: rec.paragraph,
    });
    dispatch('decide', 'card_saved', rec.symbol, undefined,
      { idempotency_key: `saved-${rec.symbol}-${today()}` });
    addMemory({
      category: 'seen',
      text: `You saved ${rec.symbol} for later — I'll surface it again tomorrow if it still holds.`,
      source: 'decision',
    });
    setDoneAction('saved');
    setStage('done');
  }

  function onSkipStart() {
    setStage('skip');
  }

  function onSkipSubmit(reason: string) {
    recordDecision({
      rec,
      rec_id: rec.symbol,
      symbol: rec.symbol,
      action: 'skipped',
      skip_reason: reason,
      thesis_snapshot: rec.paragraph,
    });
    dispatch('decide', 'card_skipped', rec.symbol, { reason },
      { idempotency_key: `skip-${rec.symbol}-${today()}` });
    addMemory({
      category: 'patterns',
      text: `You skipped ${rec.symbol} — reason: ${reason}.`,
      source: 'decision',
    });
    saveReflection({
      kind: 'thesis-review',
      targetId: `skip-${rec.symbol}-${Date.now()}`,
      prompt: `Why I skipped ${rec.symbol}`,
      body: reason,
    });
    dispatch('reflect', 'reflection_written', rec.symbol);
    setSkipReason(reason);
    setDoneAction('skipped');
    setStage('done');
  }

  function onReflectSubmit() {
    if (!reflectionText.trim()) {
      setStage('done');
      return;
    }
    saveReflection({
      kind: 'paper-trade-review',
      targetId: `follow-${rec.symbol}-${Date.now()}`,
      prompt: `What I expect from ${rec.symbol}`,
      body: reflectionText.trim(),
    });
    dispatch('reflect', 'reflection_written', rec.symbol);
    addMemory({
      category: 'seen',
      text: `You wrote a one-line reflection when opening ${rec.symbol}.`,
      source: 'reflection',
    });
    setStage('done');
  }

  return (
    <SurfaceCard variant="highlight">
      {/* Eyebrow */}
      <div className="flex items-center gap-2 mb-4">
        <p
          className="font-semibold uppercase"
          style={{
            fontSize: 11,
            letterSpacing: '0.16em',
            color: 'var(--brand)',
          }}
        >
          Arth's call today
        </p>
      </div>

      {/* Ticker + structure */}
      <div className="flex items-baseline gap-3 mb-3 flex-wrap">
        <span
          className="font-mono ink-primary tabular-nums"
          style={{ fontSize: 20 }}
        >
          {rec.symbol}
        </span>
        <span className="ink-muted" style={{ fontSize: 13 }}>
          {rec.actionLabel}
        </span>
      </div>

      {/* Thesis paragraph */}
      <p
        className="ink-primary leading-relaxed mb-4 max-w-narrative"
        style={{ fontSize: 15 }}
      >
        {rec.paragraph}
      </p>

      {/* Entry / Target / Invalidate strip */}
      <div className="grid grid-cols-3 gap-4 mb-5 py-3"
           style={{ borderTop: '1px solid var(--border)',
                    borderBottom: '1px solid var(--border)' }}>
        <Cell label="Entry"      value={rec.entry} />
        <Cell label="Target"     value={rec.target} />
        <Cell label="Invalidate" value={rec.invalidate} />
      </div>

      {/* Why for you — Arth advisory */}
      <div className="mb-5">
        <ArthVoice mode="advisory">{why.line}</ArthVoice>
      </div>

      {/* Decision row OR skip flow OR reflection OR done */}
      {stage === 'idle' && (
        <div className="flex items-center gap-2 flex-wrap">
          <PrimaryBtn onClick={onFollow}>
            Paper trade this <ArrowRight className="size-3.5" aria-hidden />
          </PrimaryBtn>
          <SecondaryBtn onClick={onSave}>Save for later</SecondaryBtn>
          <SecondaryBtn onClick={onSkipStart}>Skip — tell me why</SecondaryBtn>
        </div>
      )}

      {stage === 'skip' && (
        <div>
          <p className="ink-muted mb-3" style={{ fontSize: 13 }}>
            Pick the one that fits best — or type your own:
          </p>
          <div className="flex flex-wrap gap-2 mb-3">
            {SKIP_REASONS.map((r) => (
              <button
                key={r}
                onClick={() => onSkipSubmit(r)}
                className="px-3 py-1.5 rounded-full"
                style={{
                  fontSize: 12.5,
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--card)',
                  color: 'var(--foreground)',
                }}
              >
                {r}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={skipReason}
              onChange={(e) => setSkipReason(e.target.value)}
              placeholder="…tell Arth more"
              className="flex-1 px-3 py-2 rounded-md"
              style={{
                fontSize: 13,
                border: '1px solid var(--border)',
                backgroundColor: 'var(--background)',
                color: 'var(--foreground)',
              }}
            />
            <PrimaryBtn
              onClick={() => skipReason.trim() && onSkipSubmit(skipReason.trim())}
            >
              Tell Arth
            </PrimaryBtn>
          </div>
        </div>
      )}

      {stage === 'reflect' && (
        <div>
          <div className="mb-3">
            <ArthVoice mode="responsive">
              Logged. I'll check in when this resolves. One sentence — what
              do you expect from {rec.symbol}? Helps me read you.
            </ArthVoice>
          </div>
          <div className="flex items-start gap-2">
            <textarea
              value={reflectionText}
              onChange={(e) => setReflectionText(e.target.value)}
              placeholder={`I expect…`}
              rows={2}
              className="flex-1 px-3 py-2 rounded-md"
              style={{
                fontSize: 14,
                border: '1px solid var(--border)',
                backgroundColor: 'var(--background)',
                color: 'var(--foreground)',
                fontFamily: "'Inter', ui-sans-serif, system-ui, sans-serif",
                resize: 'vertical',
              }}
            />
            <PrimaryBtn onClick={onReflectSubmit}>
              {reflectionText.trim() ? 'Save' : 'Skip'}
            </PrimaryBtn>
          </div>
        </div>
      )}

      {stage === 'done' && (
        <DoneState action={doneAction} symbol={rec.symbol} />
      )}
    </SurfaceCard>
  );
}

function DoneState({ action, symbol }: {
  action: string | null; symbol: string;
}) {
  let line = '';
  if (action === 'paper_traded') {
    line = `Open in your paper book. I'll watch ${symbol} for you and check in when it resolves.`;
  } else if (action === 'saved') {
    line = `Saved. I'll surface ${symbol} again tomorrow if the setup still holds.`;
  } else if (action === 'skipped') {
    line = `Got it. I'll bias against setups like this tomorrow.`;
  } else if (action?.startsWith('error:')) {
    line = `Couldn't open the trade — ${action.slice(6)}. Worth checking your paper book.`;
  } else {
    line = `Logged.`;
  }
  return <ArthVoice mode="responsive">{line}</ArthVoice>;
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p
        className="font-semibold uppercase mb-1"
        style={{
          fontSize: 10,
          letterSpacing: '0.14em',
          color: 'var(--muted-foreground)',
        }}
      >
        {label}
      </p>
      <p
        className="ink-primary font-mono tabular-nums"
        style={{ fontSize: 13 }}
      >
        {value}
      </p>
    </div>
  );
}

function PrimaryBtn({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center justify-center gap-2 h-10 px-4 rounded-full"
      style={{
        fontSize: 13,
        fontWeight: 600,
        backgroundColor: 'var(--brand)',
        color: 'var(--brand-foreground)',
      }}
    >
      {children}
    </button>
  );
}

function SecondaryBtn({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center justify-center gap-2 h-10 px-4 rounded-full transition-colors"
      style={{
        fontSize: 13,
        fontWeight: 500,
        border: '1px solid var(--border)',
        backgroundColor: 'transparent',
        color: 'var(--foreground)',
      }}
    >
      {children}
    </button>
  );
}
