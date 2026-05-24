// Phase 2A/2B — Event dispatcher.
//
// Phase 2B Mandatory upgrade (M2):
//   - dispatch() accepts an idempotency_key.
//   - Same (kind + entity + idempotency_key) seen within IDEMPOTENCY_WINDOW_MS
//     is suppressed at the door. Protects pattern + cohort stats from
//     double-tap / React-strict-replay / browser-navigation double-fire.
//   - The suppression cache is in-memory (per-tab) — survives session,
//     not page reload. That's appropriate for double-tap; cross-reload
//     deduplication would require event-key persistence (deferred).

import { logEvent, type ChapterId, type EventKind } from './events';
import { scanPatterns } from './patternEngine';
import { rebuildFromEvents } from './competence';

type Observer = () => void;

const observers: Set<Observer> = new Set();

export function registerObserver(fn: Observer): () => void {
  observers.add(fn);
  return () => observers.delete(fn);
}

// ---------------------------------------------------------------------
// Idempotency cache (Phase 2B M2)
// ---------------------------------------------------------------------

const IDEMPOTENCY_WINDOW_MS = 60_000;   // 60s — covers double-taps, replay
const idempotencyCache = new Map<string, number>();   // key → last_fired_ms

function idempotencyKey(kind: EventKind, entity: string | undefined,
                       key: string | undefined): string {
  return `${kind}::${entity ?? ''}::${key ?? ''}`;
}

function isDuplicate(kind: EventKind, entity: string | undefined,
                     key: string | undefined): boolean {
  if (!key) return false;            // no key → caller opted out of dedup
  const k = idempotencyKey(kind, entity, key);
  const last = idempotencyCache.get(k);
  const now = Date.now();
  if (last !== undefined && (now - last) < IDEMPOTENCY_WINDOW_MS) return true;
  idempotencyCache.set(k, now);
  // Prune entries older than 2× the window so the cache can't grow
  // unbounded over a long session.
  if (idempotencyCache.size > 200) {
    const cutoff = now - 2 * IDEMPOTENCY_WINDOW_MS;
    for (const [ck, cts] of idempotencyCache) {
      if (cts < cutoff) idempotencyCache.delete(ck);
    }
  }
  return false;
}

export interface DispatchOptions {
  /** Suppress duplicates with the same (kind, entity, idempotency_key)
   *  within 60s. Provide a stable key per logical action. */
  idempotency_key?: string;
}

/** Single entry point for emitting events. Use this instead of
 *  logEvent directly when downstream side-effects matter. */
export function dispatch(
  chapter: ChapterId,
  kind: EventKind,
  entity?: string,
  meta?: Record<string, unknown>,
  options?: DispatchOptions,
): void {
  if (isDuplicate(kind, entity, options?.idempotency_key)) {
    return;            // silently suppressed — pattern/cohort stats safe
  }

  logEvent(chapter, kind, entity, meta);
  scanPatterns();
  rebuildFromEvents();
  for (const fn of observers) {
    try { fn(); } catch { /* one observer's failure must not block others */ }
  }
}

/** Test/dev helper — reset the in-memory idempotency cache. */
export function __resetIdempotencyCache(): void {
  idempotencyCache.clear();
}
