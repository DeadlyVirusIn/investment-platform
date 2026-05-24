// Phase 2A — Event dispatcher.
//
// Single funnel for all observable events. Wraps logEvent + triggers
// downstream pattern + competence recomputation. Phase 2A is the
// foundation: 2B/2C/2D will register their own observers (trust
// metrics, lesson recommender, etc.).

import { logEvent, type ChapterId, type EventKind } from './events';
import { scanPatterns } from './patternEngine';
import { rebuildFromEvents } from './competence';

type Observer = () => void;

const observers: Set<Observer> = new Set();

export function registerObserver(fn: Observer): () => void {
  observers.add(fn);
  return () => observers.delete(fn);
}

/** Single entry point for emitting events. Use this instead of
 *  logEvent directly when downstream side-effects matter. */
export function dispatch(
  chapter: ChapterId,
  kind: EventKind,
  entity?: string,
  meta?: Record<string, unknown>,
): void {
  logEvent(chapter, kind, entity, meta);
  // Built-in observers — always run.
  scanPatterns();
  rebuildFromEvents();
  // Plugin observers from later phases.
  for (const fn of observers) {
    try { fn(); } catch { /* one observer's failure must not block others */ }
  }
}
