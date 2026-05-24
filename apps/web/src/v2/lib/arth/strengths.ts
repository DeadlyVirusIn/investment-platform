// Phase 2E — Strengths + blind-spots deriver.
//
// All entries are evidence-backed. Honesty mandate: never surface
// a strength or blind spot without ≥5 supporting observations. When
// data is thin, the entry is hidden — NEVER replaced with speculation.

import { listEvents, type ArthEvent } from './events';
import { listDecisions, type Decision } from './decisions';

export type StrengthBlindCategory = 'strength' | 'blind_spot';

export interface StrengthBlindEntry {
  id: string;
  category: StrengthBlindCategory;
  text: string;                    // user-facing
  evidence_count: number;
  evidence_summary: string;        // explicit count/source — proves it
  confidence: 'low' | 'medium' | 'high';
}

const MIN_OBS = 5;

function reflectionsCount(events: ArthEvent[]): number {
  return events.filter((e) => e.kind === 'reflection_written').length;
}

function followsCount(decisions: Decision[]): number {
  return decisions.filter(
    (d) => d.action === 'paper_traded' || d.action === 'followed',
  ).length;
}

function skipsByReason(decisions: Decision[], rx: RegExp): number {
  return decisions.filter(
    (d) => d.action === 'skipped' && d.skip_reason && rx.test(d.skip_reason),
  ).length;
}

function winnerCutEarlyCount(decisions: Decision[]): number {
  // A "winner cut early" is closed_at < target with pnl_pct > 0 but
  // small (< 1%). We use the pnl_pct < 1 heuristic since Phase 2A
  // outcome storage doesn't (yet) track target-hit explicitly.
  return decisions.filter(
    (d) => d.outcome && d.outcome.pnl_pct > 0 && d.outcome.pnl_pct < 1.0,
  ).length;
}

function loserHeldPastInvalidateCount(decisions: Decision[]): number {
  // Heuristic: large loss (< -2%) suggests held past invalidate.
  // Phase 2F will replace with explicit invalidate-crossed flag.
  return decisions.filter(
    (d) => d.outcome && d.outcome.pnl_pct < -2.0,
  ).length;
}

function followsWithSameDayReflection(events: ArthEvent[], decisions: Decision[]): number {
  const follows = decisions.filter(
    (d) => d.action === 'paper_traded' || d.action === 'followed',
  );
  const reflections = events.filter((e) => e.kind === 'reflection_written');
  let n = 0;
  for (const f of follows) {
    const fTs = new Date(f.ts).getTime();
    const matched = reflections.some((r) => {
      const rTs = new Date(r.ts).getTime();
      return r.entity === f.symbol && rTs >= fTs && rTs <= fTs + 86_400_000;
    });
    if (matched) n++;
  }
  return n;
}

function confidenceFromCount(n: number): 'low' | 'medium' | 'high' {
  if (n >= 20) return 'high';
  if (n >= 10) return 'medium';
  return 'low';
}

export function deriveStrengths(): StrengthBlindEntry[] {
  const events = listEvents();
  const decisions = listDecisions();
  const out: StrengthBlindEntry[] = [];

  // S1 — Reflection habit.
  const reflCount = reflectionsCount(events);
  if (reflCount >= MIN_OBS) {
    out.push({
      id: 'strength_reflection_habit',
      category: 'strength',
      text: 'You write reflections consistently. That habit is rare.',
      evidence_count: reflCount,
      evidence_summary: `${reflCount} reflections in your log so far.`,
      confidence: confidenceFromCount(reflCount),
    });
  }

  // S2 — Following through (high follow count).
  const fCount = followsCount(decisions);
  if (fCount >= MIN_OBS) {
    out.push({
      id: 'strength_engagement',
      category: 'strength',
      text: "You don't just read — you act on calls. Higher signal-to-noise on your decisions.",
      evidence_count: fCount,
      evidence_summary: `${fCount} follows on record.`,
      confidence: confidenceFromCount(fCount),
    });
  }

  // S3 — Same-day reflection on follows.
  const sameDay = followsWithSameDayReflection(events, decisions);
  if (sameDay >= MIN_OBS) {
    out.push({
      id: 'strength_reflect_at_decision',
      category: 'strength',
      text: "You reflect at the moment of intent — not after the outcome. That's how I learn what you expected.",
      evidence_count: sameDay,
      evidence_summary: `${sameDay} follows with a same-day reflection.`,
      confidence: confidenceFromCount(sameDay),
    });
  }

  return out;
}

export function deriveBlindSpots(): StrengthBlindEntry[] {
  const decisions = listDecisions();
  const out: StrengthBlindEntry[] = [];

  // B1 — Cutting winners early.
  const cut = winnerCutEarlyCount(decisions);
  if (cut >= MIN_OBS) {
    out.push({
      id: 'blind_cut_winners_early',
      category: 'blind_spot',
      text: 'You may be exiting winners before they reach target.',
      evidence_count: cut,
      evidence_summary: `${cut} closed winners under +1% suggest early exits.`,
      confidence: confidenceFromCount(cut),
    });
  }

  // B2 — Holding losers past invalidate.
  const held = loserHeldPastInvalidateCount(decisions);
  if (held >= MIN_OBS) {
    out.push({
      id: 'blind_hold_losers',
      category: 'blind_spot',
      text: 'You may be holding losers past their invalidate.',
      evidence_count: held,
      evidence_summary: `${held} closed losers beyond -2% suggest the invalidate line was breached.`,
      confidence: confidenceFromCount(held),
    });
  }

  // B3 — Skipping for "Bad timing" repeatedly.
  const timingSkips = skipsByReason(decisions, /bad timing/i);
  if (timingSkips >= MIN_OBS) {
    out.push({
      id: 'blind_timing_skips',
      category: 'blind_spot',
      text: '"Bad timing" comes up often as a skip reason. Worth naming what you were waiting for each time.',
      evidence_count: timingSkips,
      evidence_summary: `${timingSkips} skips cited timing.`,
      confidence: confidenceFromCount(timingSkips),
    });
  }

  return out;
}
