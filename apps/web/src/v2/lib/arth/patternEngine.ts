// Phase 2A — Pattern engine.
//
// Runs over the event log + decisions and produces PatternObservation
// rows in storage. Pure compute; called on demand (after every event)
// from a single dispatcher (see eventDispatcher). Engine respects the
// minimum-5-observations Guardrail — internal counters can be any size,
// but PatternObservation rows are only WRITTEN once count >= 5.
//
// Rule set v1 (per §2.4 of ARTHOS_PHASE2_PRODUCT_EVOLUTION.md). New
// rules added in later phases must satisfy all five guardrails.

import { listEvents, type ArthEvent } from './events';
import { listDecisions, type Decision } from './decisions';
import { upsertPattern, type PatternCategory } from './patterns';

const WINDOW_DAYS_DEFAULT = 60;

interface RuleContext {
  events: ArthEvent[];
  decisions: Decision[];
  now: number;
  windowMs: number;
}

interface Rule {
  key: string;
  category: PatternCategory;
  detect: (ctx: RuleContext) => { count: number; event_ids: string[] } | null;
  text: (count: number) => string;
}

// ---------------------------------------------------------------------
// Rule catalogue
// ---------------------------------------------------------------------

const RULES: Rule[] = [

  // AVOID rules — based on skip-with-reason patterns.

  {
    key: 'avoid_earnings_setups',
    category: 'avoid',
    detect: ({ decisions, now, windowMs }) => {
      const skips = decisions.filter(
        (d) =>
          d.action === 'skipped' &&
          d.skip_reason &&
          /earnings/i.test(d.skip_reason) &&
          new Date(d.ts).getTime() >= now - windowMs,
      );
      if (skips.length === 0) return null;
      return { count: skips.length, event_ids: skips.map((d) => d.id) };
    },
    text: (n) =>
      `You've skipped ${n} earnings-related setup${n === 1 ? '' : 's'} so far. ` +
      `When the skip reason mentions earnings, you opt out.`,
  },

  {
    key: 'avoid_high_risk_setups',
    category: 'avoid',
    detect: ({ decisions, now, windowMs }) => {
      const skips = decisions.filter(
        (d) =>
          d.action === 'skipped' &&
          d.skip_reason &&
          /too risky/i.test(d.skip_reason) &&
          new Date(d.ts).getTime() >= now - windowMs,
      );
      if (skips.length === 0) return null;
      return { count: skips.length, event_ids: skips.map((d) => d.id) };
    },
    text: (n) =>
      `You've skipped ${n} setup${n === 1 ? '' : 's'} with "too risky" as ` +
      `the reason. Risk framing tends to be your top skip filter.`,
  },

  {
    key: 'avoid_when_overexposed',
    category: 'avoid',
    detect: ({ decisions, now, windowMs }) => {
      const skips = decisions.filter(
        (d) =>
          d.action === 'skipped' &&
          d.skip_reason &&
          /already too exposed/i.test(d.skip_reason) &&
          new Date(d.ts).getTime() >= now - windowMs,
      );
      if (skips.length === 0) return null;
      return { count: skips.length, event_ids: skips.map((d) => d.id) };
    },
    text: (n) =>
      `You've skipped ${n} setup${n === 1 ? '' : 's'} citing existing exposure. ` +
      `You track concentration before adding new positions.`,
  },

  // FAVOR rules — based on follow patterns.

  {
    key: 'favor_following_calls',
    category: 'favor',
    detect: ({ decisions, now, windowMs }) => {
      const follows = decisions.filter(
        (d) =>
          (d.action === 'paper_traded' || d.action === 'followed') &&
          new Date(d.ts).getTime() >= now - windowMs,
      );
      if (follows.length === 0) return null;
      return { count: follows.length, event_ids: follows.map((d) => d.id) };
    },
    text: (n) =>
      `You've followed ${n} of my call${n === 1 ? '' : 's'} so far.`,
  },

  // STRENGTH rules — observable habit signals.

  {
    key: 'strength_reflection_habit',
    category: 'strength',
    detect: ({ events, now, windowMs }) => {
      const reflections = events.filter(
        (e) =>
          e.kind === 'reflection_written' &&
          new Date(e.ts).getTime() >= now - windowMs,
      );
      if (reflections.length === 0) return null;
      return {
        count: reflections.length,
        event_ids: reflections.map((e) => e.id),
      };
    },
    text: (n) =>
      `You've written ${n} reflection${n === 1 ? '' : 's'} so far. ` +
      `Reflection is a habit you keep.`,
  },

  // MISTAKE rules — observable repeated errors. These only matter once
  // closed-trade outcome tracking lands in 2B. For 2A we record the
  // scaffold; rule fires with count=0 until outcome data exists.

  {
    key: 'mistake_no_reflection_on_follow',
    category: 'mistake',
    detect: ({ events, decisions, now, windowMs }) => {
      const window = now - windowMs;
      const follows = decisions.filter(
        (d) =>
          (d.action === 'paper_traded' || d.action === 'followed') &&
          new Date(d.ts).getTime() >= window,
      );
      if (follows.length === 0) return null;

      // For each follow, check if a reflection event exists within 24h.
      const reflectionEvents = events.filter(
        (e) =>
          e.kind === 'reflection_written' &&
          new Date(e.ts).getTime() >= window,
      );

      const followsWithoutReflection: string[] = [];
      for (const f of follows) {
        const fTs = new Date(f.ts).getTime();
        const matched = reflectionEvents.some((r) => {
          const rTs = new Date(r.ts).getTime();
          return r.entity === f.symbol && rTs >= fTs && rTs <= fTs + 86_400_000;
        });
        if (!matched) followsWithoutReflection.push(f.id);
      }
      if (followsWithoutReflection.length === 0) return null;
      return {
        count: followsWithoutReflection.length,
        event_ids: followsWithoutReflection,
      };
    },
    text: (n) =>
      `${n} follow${n === 1 ? '' : 's'} without a same-day reflection. ` +
      `Reflection at the moment of intent is where I learn what you expect.`,
  },
];

// ---------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------

const MIN_OBSERVATIONS_TO_PERSIST = 5;

export function scanPatterns(opts?: { window_days?: number }): void {
  const windowDays = opts?.window_days ?? WINDOW_DAYS_DEFAULT;
  const ctx: RuleContext = {
    events: listEvents(),
    decisions: listDecisions(),
    now: Date.now(),
    windowMs: windowDays * 86_400_000,
  };

  for (const rule of RULES) {
    const result = rule.detect(ctx);
    if (!result) continue;
    if (result.count < MIN_OBSERVATIONS_TO_PERSIST) {
      // Don't write a row yet — Guardrail #3 forbids surfacing below 5.
      // We intentionally skip persistence too; the rule re-evaluates
      // every scan and the row appears at the moment it crosses 5.
      continue;
    }
    upsertPattern(
      rule.key,
      rule.category,
      result.count,
      result.event_ids,
      rule.text,
    );
  }
}

export const ALL_RULES = RULES;
