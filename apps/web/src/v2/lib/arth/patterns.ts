// Phase 2A — Pattern observation store.
//
// Hard guardrails (per direction reset):
//   1. No personality conclusions — text is always behavioral, never identity
//   2. Observable behaviors only — every note cites source_event_ids
//   3. Minimum 5 observations before user-facing display (see hidden flag)
//   4. Confidence visible — surfaced as words, never numbers
//   5. Every pattern disputable — confirm + dispute hooks present
//
// Phase 2A only writes + reads; UI surfaces ship in 2C (Decision Desk),
// 2D (Contextual Learning), 2E (Mentor Profile).

import { KEYS, readVersioned, writeVersioned } from './storage';
import { useArthStore } from './useArthStore';

export type PatternCategory = 'avoid' | 'favor' | 'strength' | 'mistake';
export type PatternConfidence = 'low' | 'medium' | 'high';

const STORAGE_KEY = `${KEYS.memory}.patterns`;
const DISPUTE_PAUSE_DAYS = 30;
const MIN_OBSERVATIONS_FOR_DISPLAY = 5;

export interface PatternObservation {
  id: string;
  category: PatternCategory;
  rule_key: string;                    // e.g. 'avoid_earnings_setups'
  text: string;                        // behavioral, e.g. "You've skipped 5 of 6 earnings setups."
  observation_count: number;           // total events that produced this
  source_event_ids: string[];          // most recent N (cap 50)
  first_seen_at: string;               // ISO
  last_seen_at: string;                // ISO
  confidence: PatternConfidence;
  user_confirmed?: boolean;
  user_disputed?: boolean;
  disputed_at?: string;
  retired?: boolean;
}

function uid() {
  return `p-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function listPatterns(): PatternObservation[] {
  return readVersioned<PatternObservation[]>(STORAGE_KEY, []);
}

export function findPattern(rule_key: string): PatternObservation | undefined {
  return listPatterns().find((p) => p.rule_key === rule_key && !p.retired);
}

export function upsertPattern(
  rule_key: string,
  category: PatternCategory,
  newCount: number,
  newEventIds: string[],
  textFromCount: (count: number) => string,
): PatternObservation {
  const all = listPatterns();
  const now = new Date().toISOString();
  const existing = all.find((p) => p.rule_key === rule_key);

  // Dispute-pause: if user disputed within last 30 days, skip update.
  if (existing?.user_disputed && existing.disputed_at) {
    const disputedAt = new Date(existing.disputed_at).getTime();
    const pauseUntil = disputedAt + DISPUTE_PAUSE_DAYS * 86_400_000;
    if (Date.now() < pauseUntil) return existing;
    // Pause expired — clear dispute flag, recompute below.
  }

  const confidence: PatternConfidence =
    newCount >= 20 ? 'high' : newCount >= 10 ? 'medium' : 'low';

  const merged: PatternObservation = existing
    ? {
        ...existing,
        observation_count: newCount,
        source_event_ids: dedupedTail([...existing.source_event_ids, ...newEventIds], 50),
        last_seen_at: now,
        text: textFromCount(newCount),
        confidence,
        // Clear dispute flag if we got here past pause window.
        user_disputed: false,
        disputed_at: undefined,
      }
    : {
        id: uid(),
        category,
        rule_key,
        text: textFromCount(newCount),
        observation_count: newCount,
        source_event_ids: newEventIds.slice(-50),
        first_seen_at: now,
        last_seen_at: now,
        confidence,
      };

  const next = existing
    ? all.map((p) => (p.id === existing.id ? merged : p))
    : [...all, merged];
  writeVersioned(STORAGE_KEY, next);
  return merged;
}

export function confirmPattern(id: string): void {
  const all = listPatterns();
  writeVersioned(
    STORAGE_KEY,
    all.map((p) =>
      p.id === id
        ? { ...p, user_confirmed: true, user_disputed: false, disputed_at: undefined }
        : p,
    ),
  );
}

export function disputePattern(id: string): void {
  const all = listPatterns();
  const now = new Date().toISOString();
  writeVersioned(
    STORAGE_KEY,
    all.map((p) =>
      p.id === id
        ? {
            ...p,
            user_disputed: true,
            user_confirmed: false,
            disputed_at: now,
            // Drop two confidence tiers per guardrail.
            confidence:
              p.confidence === 'high' ? 'low'
              : p.confidence === 'medium' ? 'low'
              : 'low',
          }
        : p,
    ),
  );
}

export function retirePattern(id: string): void {
  const all = listPatterns();
  writeVersioned(
    STORAGE_KEY,
    all.map((p) => (p.id === id ? { ...p, retired: true } : p)),
  );
}

/** Returns only patterns the user is allowed to see — observes
 *  Guardrail #3 (min 5 observations) + not-retired + not-paused. */
export function visiblePatterns(): PatternObservation[] {
  return listPatterns().filter((p) => {
    if (p.retired) return false;
    if (p.observation_count < MIN_OBSERVATIONS_FOR_DISPLAY) return false;
    if (p.user_disputed && p.disputed_at) {
      const pauseUntil =
        new Date(p.disputed_at).getTime() + DISPUTE_PAUSE_DAYS * 86_400_000;
      if (Date.now() < pauseUntil) return false;
    }
    return true;
  });
}

const EMPTY: PatternObservation[] = [];

export function useVisiblePatterns(): PatternObservation[] {
  const all = useArthStore<PatternObservation[]>(STORAGE_KEY, EMPTY);
  return all.filter((p) => {
    if (p.retired) return false;
    if (p.observation_count < MIN_OBSERVATIONS_FOR_DISPLAY) return false;
    if (p.user_disputed && p.disputed_at) {
      const pauseUntil =
        new Date(p.disputed_at).getTime() + DISPUTE_PAUSE_DAYS * 86_400_000;
      if (Date.now() < pauseUntil) return false;
    }
    return true;
  });
}

/** Hedge-word render for visible patterns. */
export function confidenceHedge(c: PatternConfidence): string {
  return c === 'high' ? "I'm sure" : c === 'medium' ? 'It looks like' : 'I think';
}

function dedupedTail<T>(arr: T[], max: number): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const v of arr) {
    const k = String(v);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(v);
  }
  return out.slice(-max);
}
