// Arth event log — append-only, capped, drives pattern detection.

import { KEYS, readVersioned, writeVersioned } from './storage';
import { useArthStore } from './useArthStore';

export type ChapterId =
  | 'see' | 'decide' | 'practice' | 'learn' | 'reflect' | 'remember';

export type EventKind =
  | 'session_open'
  | 'briefing_viewed'
  | 'card_viewed'
  | 'card_followed'
  | 'card_paper_traded'
  | 'card_skipped'
  | 'card_saved'
  | 'reflection_written'
  | 'memory_corrected'
  | 'lesson_opened';

export interface ArthEvent {
  id: string;
  ts: string;             // ISO
  chapter: ChapterId;
  kind: EventKind;
  entity?: string;        // symbol, lesson_slug, rec_id, etc.
  meta?: Record<string, unknown>;
}

const CAP = 5000;

function uid() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function logEvent(
  chapter: ChapterId,
  kind: EventKind,
  entity?: string,
  meta?: Record<string, unknown>,
): ArthEvent {
  const evt: ArthEvent = {
    id: uid(),
    ts: new Date().toISOString(),
    chapter,
    kind,
    entity,
    meta,
  };
  const events = readVersioned<ArthEvent[]>(KEYS.events, []);
  const next = [...events, evt];
  if (next.length > CAP) next.splice(0, next.length - CAP);
  writeVersioned(KEYS.events, next);
  return evt;
}

export function listEvents(): ArthEvent[] {
  return readVersioned<ArthEvent[]>(KEYS.events, []);
}

const EMPTY: ArthEvent[] = [];
// React hook — re-renders on event log change.
export function useEvents(): ArthEvent[] {
  return useArthStore<ArthEvent[]>(KEYS.events, EMPTY);
}
