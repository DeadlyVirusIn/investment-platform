// Phase 2D — Lesson recommender.
//
// Maps observed events / patterns / outcomes to a contextual lesson.
// Every triggered lesson must be EXPLAINABLE — the surface displays
// the trigger_label so the user knows exactly why Arth surfaced it.
//
// Honesty contract: a lesson is marked 'learned' ONLY after the
// one-question check passes. Opening the primer marks 'read', not
// 'learned'. The competence map honors this distinction.

import { CONTEXTUAL_LESSONS, type ContextualLesson } from './contextualLessons';
import { getCompetence } from './competence';

export interface LessonHit {
  lesson: ContextualLesson;
  trigger_reason: string;       // user-facing — why Arth surfaced this
  trigger_event_id?: string;
  priority: number;             // 0..1 — recommender scoring
}

// Skip-reason → lesson slug
const SKIP_REASON_MAP: Record<string, string> = {
  'Earnings risk':                    'earnings_risk',
  'Too risky':                        'too_risky',
  'Already too exposed here':         'exposure',
  'Bad timing':                       'bad_timing',
  "Don't understand the structure":   'iv_crush',     // best general fallback for option setups
  'Not interested in this name':      'too_risky',    // soft fallback
};

// Concept tap → primer slug
const CONCEPT_TAP_MAP: Record<string, string> = {
  'implied_volatility':   'iv_crush',
  'iv_crush':             'iv_crush',
  'stop':                 'why_stops_exist',
  'invalidate':           'why_stops_exist',
};

// Outcome pattern → lesson slug
function outcomeLessonFor(opts: {
  pnl_pct: number; days_held: number; was_winner: boolean;
  closed_at_target: boolean; closed_below_invalidate: boolean;
}): string | null {
  if (opts.closed_below_invalidate && opts.pnl_pct < -1.0) return 'why_stops_exist';
  if (opts.was_winner && !opts.closed_at_target && opts.pnl_pct < 1.0) {
    return 'cut_winners_early';
  }
  return null;
}

// Behavior-pattern triggers
const PATTERN_LESSON_MAP: Record<string, string> = {
  'avoid_earnings_setups':            'earnings_risk',
  'avoid_high_risk_setups':           'too_risky',
  'avoid_when_overexposed':           'exposure',
};

// Public entry points

export function lessonForSkipReason(reason: string): LessonHit | null {
  const slug = SKIP_REASON_MAP[reason];
  if (!slug) return null;
  const lesson = CONTEXTUAL_LESSONS[slug];
  if (!lesson) return null;
  // Honesty mode — never surface as primer if already learned.
  const comp = getCompetence(slug);
  if (comp.status === 'learned' || comp.status === 'recalled') return null;
  return {
    lesson,
    trigger_reason: `You skipped with reason "${reason}". ${lesson.trigger_label}.`,
    priority: 1.0,                       // direct match — highest priority
  };
}

export function lessonForConceptTap(slug_or_keyword: string): LessonHit | null {
  const slug = CONCEPT_TAP_MAP[slug_or_keyword] ?? slug_or_keyword;
  const lesson = CONTEXTUAL_LESSONS[slug];
  if (!lesson) return null;
  return {
    lesson,
    trigger_reason: `You tapped "${slug_or_keyword.replace(/_/g, ' ')}" in a card.`,
    priority: 0.9,
  };
}

export function lessonForTradeOutcome(opts: {
  pnl_pct: number;
  days_held: number;
  was_winner: boolean;
  closed_at_target: boolean;
  closed_below_invalidate: boolean;
}): LessonHit | null {
  const slug = outcomeLessonFor(opts);
  if (!slug) return null;
  const lesson = CONTEXTUAL_LESSONS[slug];
  if (!lesson) return null;
  return {
    lesson,
    trigger_reason: opts.closed_below_invalidate
      ? `That trade closed past its invalidate at ${opts.pnl_pct.toFixed(1)}%. ${lesson.trigger_label}.`
      : `You closed the position at +${opts.pnl_pct.toFixed(1)}% — below the target. ${lesson.trigger_label}.`,
    priority: 0.85,
  };
}

export function lessonForPattern(rule_key: string): LessonHit | null {
  const slug = PATTERN_LESSON_MAP[rule_key];
  if (!slug) return null;
  const lesson = CONTEXTUAL_LESSONS[slug];
  if (!lesson) return null;
  const comp = getCompetence(slug);
  if (comp.status === 'learned' || comp.status === 'recalled') return null;
  return {
    lesson,
    trigger_reason: `I've noticed a recurring pattern: ${rule_key.replace(/_/g, ' ')}. Worth understanding the why behind it.`,
    priority: 0.7,
  };
}

export function lessonForStreakMilestone(day: number): LessonHit | null {
  if (day !== 7 && day !== 30) return null;
  const slug = 'showing_up';
  const lesson = CONTEXTUAL_LESSONS[slug];
  if (!lesson) return null;
  const comp = getCompetence(slug);
  if (comp.status === 'learned' || comp.status === 'recalled') return null;
  return {
    lesson,
    trigger_reason: `Day ${day} of practice — milestone moment.`,
    priority: 0.6,
  };
}
