// Arth decision capture — Follow / Paper trade / Skip / Save / Held cash.
//
// Phase 2B mandatory upgrade (M1): every decision now carries a cohort
// key + outcome slot. cohort is set at write time using classifyCohort
// — the "uncategorized" bucket only fires when classifyCohort fails to
// match (vanishingly rare; currently impossible with the 5 classifiers
// covering all TODAYS_DESK rec shapes).

import type { Recommendation } from '../../data/arthosData';
import { KEYS, readVersioned, writeVersioned } from './storage';
import { useArthStore } from './useArthStore';
import { classifyCohort, type CohortKey } from './cohort';

export type DecisionAction =
  | 'followed'
  | 'paper_traded'
  | 'skipped'
  | 'saved'
  | 'held_cash';     // NEW — first-class cash-as-decision (per direction reset #5)

export type DecisionConfidence = 'low' | 'medium' | 'high';

export interface DecisionOutcome {
  closed_at: string;            // ISO
  pnl_pct: number;              // signed percent (+1.4 = +1.4%)
  arth_was_right: boolean;
  days_held: number;
}

export interface Decision {
  id: string;
  rec_id: string;                       // symbol or rec key
  symbol: string;                       // 'CASH' for held_cash
  action: DecisionAction;
  skip_reason?: string;
  thesis_snapshot: string;
  ts: string;

  // Phase 2B M1 — cohort persisted at write time.
  cohort: CohortKey;

  // Phase 2B — outcome populated after trade close (Practice → Report Card).
  outcome?: DecisionOutcome;

  // Phase 2B — Arth's confidence on this rec at decision time
  // (snapshot, so later confidence-tuning doesn't rewrite history).
  arth_confidence?: DecisionConfidence;
}

function uid() {
  return `d-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/** Phase 2B — record a decision against a Recommendation. The cohort
 *  is derived from the rec at write time and persisted alongside the
 *  decision so future cohortStats() queries are stable. */
export function recordDecision(
  input: Omit<Decision, 'id' | 'ts' | 'cohort'> & {
    rec?: Recommendation;                // optional, for cohort classification
    cohort?: CohortKey;                  // explicit override (used by held_cash)
  },
): Decision {
  const { rec, cohort: cohortOverride, ...rest } = input;
  const cohort: CohortKey =
    cohortOverride ?? (rec ? classifyCohort(rec) : 'uncategorized');

  const dec: Decision = {
    id: uid(),
    ts: new Date().toISOString(),
    cohort,
    ...rest,
  };
  const all = readVersioned<Decision[]>(KEYS.decisions, []);
  writeVersioned(KEYS.decisions, [...all, dec]);
  return dec;
}

/** Phase 2B — close a paper-traded decision with an outcome. Used by
 *  ClosedTradeRetrospective + Report Card. Idempotent — re-applying
 *  the same outcome is a no-op. */
export function closeDecision(id: string, outcome: DecisionOutcome): void {
  const all = readVersioned<Decision[]>(KEYS.decisions, []);
  const idx = all.findIndex((d) => d.id === id);
  if (idx < 0) return;
  if (all[idx].outcome) return;          // already closed — no overwrite
  all[idx] = { ...all[idx], outcome };
  writeVersioned(KEYS.decisions, all);
}

export function listDecisions(): Decision[] {
  return readVersioned<Decision[]>(KEYS.decisions, []);
}

const EMPTY_DEC: Decision[] = [];
export function useDecisions(): Decision[] {
  return useArthStore<Decision[]>(KEYS.decisions, EMPTY_DEC);
}

export function decisionForToday(rec_id: string): Decision | undefined {
  const today = new Date().toISOString().slice(0, 10);
  return listDecisions().find(
    (d) => d.rec_id === rec_id && d.ts.slice(0, 10) === today,
  );
}
