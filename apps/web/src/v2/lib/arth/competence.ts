// Phase 2A — Competence map derivation.
//
// Tracks the user's progress through lesson concepts. Status evolves
// from untaught → encountered → read → learned → recalled based on
// observable events. No browsing-based "learned" status — only earned.

import { KEYS, readVersioned, writeVersioned } from './storage';
import { useArthStore } from './useArthStore';
import { listEvents } from './events';

const STORAGE_KEY = `${KEYS.memory}.competence`;

export type CompetenceStatus =
  | 'untaught'
  | 'encountered'   // term tapped or seen in a card, no engagement
  | 'read'          // primer opened OR lesson opened
  | 'learned'       // primer "got it" passed OR lesson check passed
  | 'recalled';     // referenced in a later reflection

export interface CompetenceEntry {
  lesson_slug: string;
  status: CompetenceStatus;
  first_encountered_at?: string;
  read_at?: string;
  learned_at?: string;
  last_recalled_at?: string;
  recall_count: number;
}

function emptyEntry(slug: string): CompetenceEntry {
  return { lesson_slug: slug, status: 'untaught', recall_count: 0 };
}

export function listCompetence(): CompetenceEntry[] {
  return readVersioned<CompetenceEntry[]>(STORAGE_KEY, []);
}

export function getCompetence(slug: string): CompetenceEntry {
  return listCompetence().find((c) => c.lesson_slug === slug) ?? emptyEntry(slug);
}

function persist(entries: CompetenceEntry[]): void {
  writeVersioned(STORAGE_KEY, entries);
}

function upsert(entry: CompetenceEntry): void {
  const all = listCompetence();
  const idx = all.findIndex((c) => c.lesson_slug === entry.lesson_slug);
  if (idx >= 0) all[idx] = entry;
  else all.push(entry);
  persist(all);
}

// Status transitions are monotonic (you can't un-learn).
const ORDER: Record<CompetenceStatus, number> = {
  untaught: 0, encountered: 1, read: 2, learned: 3, recalled: 4,
};

function bumpTo(slug: string, target: CompetenceStatus, ts: string): void {
  const current = getCompetence(slug);
  if (ORDER[target] <= ORDER[current.status]) return;
  const next: CompetenceEntry = { ...current };
  next.status = target;
  if (target === 'encountered' && !next.first_encountered_at) {
    next.first_encountered_at = ts;
  }
  if (target === 'read' && !next.read_at) next.read_at = ts;
  if (target === 'learned' && !next.learned_at) next.learned_at = ts;
  upsert(next);
}

export function markEncountered(slug: string, ts = new Date().toISOString()): void {
  bumpTo(slug, 'encountered', ts);
}
export function markRead(slug: string, ts = new Date().toISOString()): void {
  bumpTo(slug, 'read', ts);
}
export function markLearned(slug: string, ts = new Date().toISOString()): void {
  bumpTo(slug, 'learned', ts);
}
export function markRecalled(slug: string, ts = new Date().toISOString()): void {
  const all = listCompetence();
  const idx = all.findIndex((c) => c.lesson_slug === slug);
  const base = idx >= 0 ? all[idx] : emptyEntry(slug);
  const next: CompetenceEntry = {
    ...base,
    status: 'recalled',
    last_recalled_at: ts,
    recall_count: (base.recall_count ?? 0) + 1,
  };
  if (idx >= 0) all[idx] = next;
  else all.push(next);
  persist(all);
}

/** Rebuild from event log. Idempotent — safe to call on every event. */
export function rebuildFromEvents(): void {
  const events = listEvents();
  const known: Record<string, CompetenceEntry> = {};
  function ensure(slug: string): CompetenceEntry {
    if (!known[slug]) known[slug] = emptyEntry(slug);
    return known[slug];
  }
  for (const e of events) {
    if (!e.entity) continue;
    const slug = e.entity;
    if (e.kind === 'concept_tapped' as never || e.kind === 'card_viewed') {
      const c = ensure(slug);
      if (ORDER[c.status] < ORDER['encountered']) {
        c.status = 'encountered';
        c.first_encountered_at = c.first_encountered_at ?? e.ts;
      }
    }
    if (e.kind === 'lesson_opened' || e.kind === 'primer_completed' as never) {
      const c = ensure(slug);
      if (ORDER[c.status] < ORDER['read']) {
        c.status = 'read';
        c.read_at = c.read_at ?? e.ts;
      }
    }
    if (e.kind === 'lesson_learned' as never) {
      const c = ensure(slug);
      if (ORDER[c.status] < ORDER['learned']) {
        c.status = 'learned';
        c.learned_at = c.learned_at ?? e.ts;
      }
    }
  }
  persist(Object.values(known));
}

const EMPTY: CompetenceEntry[] = [];
export function useCompetence(): CompetenceEntry[] {
  return useArthStore<CompetenceEntry[]>(STORAGE_KEY, EMPTY);
}
