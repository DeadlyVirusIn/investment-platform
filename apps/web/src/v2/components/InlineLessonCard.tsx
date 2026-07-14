// Phase 2D — Inline lesson card.
//
// Three-tier disclosure (per direction):
//   - primer  (30s)  — opening view, always visible
//   - lesson  (2min) — "give me more" expands inline
//   - deep    (5min) — links to /v2/learn archive (out of scope to expand inline)
//
// Honesty mode: marking "Learned" is gated by a one-question check
// (1 of N multiple-choice). The user must pick the correct answer to
// promote competence from 'read' → 'learned'. No mastery without
// evidence.
//
// Per direction-reset #2: every card displays an explicit trigger
// reason — the user knows exactly why Arth surfaced this.

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, X } from 'lucide-react';
import { SurfaceCard } from './ui/SurfaceCard';
import { ArthVoice, ArthGlyph } from '../chrome/ArthVoice';
import { dispatch } from '../lib/arth/dispatcher';
import { markEncountered, markRead, markLearned, getCompetence } from '../lib/arth/competence';
import type { LessonHit } from '../lib/arth/lessonRecommender';

export function InlineLessonCard({
  hit, onDismiss,
}: {
  hit: LessonHit;
  onDismiss?: () => void;
}) {
  const initial = getCompetence(hit.lesson.slug);
  const [tier, setTier] = useState<'primer' | 'lesson' | 'check'>('primer');
  const [picked, setPicked] = useState<string | null>(null);
  const [status, setStatus] = useState(initial.status);
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  function onOpenPrimer() {
    markEncountered(hit.lesson.slug);
    dispatch('learn', 'lesson_opened', hit.lesson.slug,
      { tier: 'primer', trigger: hit.trigger_reason },
      { idempotency_key: `lesson-primer-${hit.lesson.slug}` });
  }
  // Run once on mount.
  if (initial.status === 'untaught') onOpenPrimer();

  function onGoDeeper() {
    setTier('lesson');
    markRead(hit.lesson.slug);
    dispatch('learn', 'lesson_opened', hit.lesson.slug,
      { tier: 'lesson' },
      { idempotency_key: `lesson-full-${hit.lesson.slug}` });
  }

  function onShowCheck() {
    setTier('check');
  }

  function onSubmitCheck() {
    if (!picked) return;
    const correct = picked === hit.lesson.check_answer_correct;
    if (correct) {
      markLearned(hit.lesson.slug);
      setStatus('learned');
      dispatch('learn', 'lesson_opened', hit.lesson.slug,
        { tier: 'learned' },
        { idempotency_key: `lesson-learned-${hit.lesson.slug}` });
    }
  }

  return (
    <SurfaceCard variant="muted" className="p-5 lg:p-6 relative">
      {onDismiss && (
        <button onClick={() => { setDismissed(true); onDismiss(); }}
          aria-label="Dismiss" className="absolute" style={{
            top: 14, right: 14, padding: 4,
            color: 'var(--muted-foreground)', background: 'transparent',
          }}>
          <X className="size-4" aria-hidden />
        </button>
      )}

      {/* Trigger reason — every lesson explains its own surfacing */}
      <div className="flex items-start gap-2 mb-3">
        <ArthGlyph size={20} />
        <p className="ink-muted italic" style={{ fontSize: 12.5, lineHeight: 1.45 }}>
          {hit.trigger_reason}
        </p>
      </div>

      {/* Title + tier indicator */}
      <div className="flex items-baseline justify-between gap-3 flex-wrap mb-2">
        <h3 className="font-display ink-primary" style={{
          fontSize: 19, lineHeight: 1.25,
          fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
        }}>{hit.lesson.title}</h3>
        <TierChip tier={tier} reads={hit.lesson.reads_in} />
      </div>

      {/* Primer */}
      {tier === 'primer' && (
        <>
          <p className="ink-primary mt-2" style={{ fontSize: 14, lineHeight: 1.55 }}>
            {hit.lesson.primer_body}
          </p>
          <div className="mt-4 flex items-center gap-2 flex-wrap">
            <button onClick={onGoDeeper} className="inline-flex items-center gap-2 h-9 px-3 rounded-full" style={{
              fontSize: 12.5, fontWeight: 600,
              backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)',
            }}>
              Give me the full 2-min lesson <ArrowRight className="size-3" />
            </button>
            <button onClick={onShowCheck} className="inline-flex items-center gap-2 h-9 px-3 rounded-full" style={{
              fontSize: 12.5, fontWeight: 500,
              border: '1px solid var(--border)', backgroundColor: 'transparent',
              color: 'var(--foreground)',
            }}>
              I've got it — quick check
            </button>
            <span className="ink-fainter" style={{ fontSize: 11, marginLeft: 'auto' }}>
              {status === 'learned' || status === 'recalled' ? '✓ Learned'
                : status === 'read' ? 'Read' : 'New'}
            </span>
          </div>
        </>
      )}

      {/* 2-min lesson */}
      {tier === 'lesson' && (
        <>
          <div className="mt-2 space-y-3 ink-primary" style={{ fontSize: 14, lineHeight: 1.65 }}>
            {hit.lesson.lesson_body.split('\n\n').map((para, i) => (
              <p key={i} style={{ whiteSpace: 'pre-line' }}>{para}</p>
            ))}
          </div>
          <div className="mt-4 flex items-center gap-2 flex-wrap">
            <button onClick={onShowCheck} className="inline-flex items-center gap-2 h-9 px-3 rounded-full" style={{
              fontSize: 12.5, fontWeight: 600,
              backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)',
            }}>
              Quick check
            </button>
            {hit.lesson.deep_body && (
              <Link to={`/learn/lesson/${hit.lesson.slug}`}
                    className="inline-flex items-center gap-2 h-9 px-3 rounded-full" style={{
                      fontSize: 12.5, fontWeight: 500,
                      border: '1px solid var(--border)', backgroundColor: 'transparent',
                      color: 'var(--foreground)',
                    }}>
                Read the 5-min deep version →
              </Link>
            )}
          </div>
        </>
      )}

      {/* One-question check */}
      {tier === 'check' && (
        <>
          <p className="ink-primary mt-2" style={{ fontSize: 14, fontWeight: 500 }}>
            {hit.lesson.check_question}
          </p>
          <div className="mt-3 space-y-2">
            {hit.lesson.check_answer_options.map((opt) => {
              const isCorrect = opt === hit.lesson.check_answer_correct;
              const isPicked = opt === picked;
              const wasSubmitted = status === 'learned' || (picked !== null && !isCorrect && isPicked);
              let bg = 'var(--card)';
              let bord = 'var(--border)';
              let color = 'var(--foreground)';
              if (wasSubmitted) {
                if (isCorrect) { bg = 'color-mix(in oklch, var(--brand) 18%, transparent)'; bord = 'var(--brand)'; color = 'var(--brand)'; }
                else if (isPicked) { bg = 'color-mix(in oklch, var(--destructive) 14%, transparent)'; bord = 'var(--destructive)'; color = 'var(--destructive)'; }
              } else if (isPicked) {
                bord = 'var(--brand)';
              }
              return (
                <button key={opt} onClick={() => !wasSubmitted && setPicked(opt)}
                  disabled={wasSubmitted}
                  className="w-full text-left px-3 py-2.5 rounded-md transition-colors"
                  style={{
                    fontSize: 13, fontWeight: 500,
                    border: `1px solid ${bord}`, backgroundColor: bg, color,
                    cursor: wasSubmitted ? 'default' : 'pointer',
                  }}>
                  {opt}
                </button>
              );
            })}
          </div>
          {status !== 'learned' && (
            <div className="mt-3">
              <button onClick={onSubmitCheck}
                disabled={!picked}
                className="inline-flex items-center gap-2 h-9 px-3 rounded-full" style={{
                  fontSize: 12.5, fontWeight: 600,
                  backgroundColor: picked ? 'var(--brand)' : 'var(--card)',
                  color: picked ? 'var(--brand-foreground)' : 'var(--muted-foreground)',
                  opacity: picked ? 1 : 0.6,
                  cursor: picked ? 'pointer' : 'not-allowed',
                }}>
                Submit
              </button>
              {picked && picked !== hit.lesson.check_answer_correct && (
                <span className="ink-muted ml-3 italic" style={{ fontSize: 12 }}>
                  Not quite. Re-read the lesson and try again.
                </span>
              )}
            </div>
          )}
          {status === 'learned' && (
            <ArthVoice mode="responsive" className="mt-3">
              Got it. Marking this lesson "learned" in your competence map. I'll skip this primer next time.
            </ArthVoice>
          )}
        </>
      )}
    </SurfaceCard>
  );
}

function TierChip({ tier, reads }: {
  tier: 'primer' | 'lesson' | 'check';
  reads: { primer_seconds: number; lesson_minutes: number; deep_minutes: number };
}) {
  const label =
    tier === 'primer' ? `~${reads.primer_seconds}s primer` :
    tier === 'lesson' ? `~${reads.lesson_minutes} min` :
    `1-question check`;
  return (
    <span className="px-2 py-0.5 rounded-full font-semibold uppercase" style={{
      fontSize: 10, letterSpacing: '0.14em',
      color: 'var(--brand)',
      backgroundColor: 'color-mix(in oklch, var(--brand) 14%, transparent)',
      border: '1px solid color-mix(in oklch, var(--brand) 22%, transparent)',
    }}>{label}</span>
  );
}
