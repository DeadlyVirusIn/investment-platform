// Arth memory — three categories: told_me / seen / patterns.
// User-visible, editable. No covert inference language.

import { KEYS, readVersioned, writeVersioned } from './storage';
import { useArthStore } from './useArthStore';

export type MemoryCategory = 'told_me' | 'seen' | 'patterns';

export interface MemoryNote {
  id: string;
  ts: string;                         // ISO
  category: MemoryCategory;
  text: string;                       // user-facing, first-person from Arth
  source: 'onboarding' | 'reflection' | 'decision' | 'pattern' | 'user_edit';
  source_event_ids?: string[];
  pinned?: boolean;
  user_edited?: boolean;
  retired?: boolean;
}

function uid() {
  return `m-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function listMemory(): MemoryNote[] {
  return readVersioned<MemoryNote[]>(KEYS.memory, []);
}

export function addMemory(input: Omit<MemoryNote, 'id' | 'ts'>): MemoryNote {
  const note: MemoryNote = {
    id: uid(),
    ts: new Date().toISOString(),
    ...input,
  };
  const all = listMemory();
  // Dedupe by category+text to avoid noise on repeated triggers.
  if (all.some((n) => n.category === note.category && n.text === note.text && !n.retired)) {
    return note;
  }
  writeVersioned(KEYS.memory, [...all, note]);
  return note;
}

export function editMemory(id: string, text: string): void {
  const all = listMemory();
  writeVersioned(
    KEYS.memory,
    all.map((n) => (n.id === id ? { ...n, text, user_edited: true } : n)),
  );
}

export function retireMemory(id: string): void {
  const all = listMemory();
  writeVersioned(
    KEYS.memory,
    all.map((n) => (n.id === id ? { ...n, retired: true } : n)),
  );
}

export function pinMemory(id: string, pinned: boolean): void {
  const all = listMemory();
  writeVersioned(
    KEYS.memory,
    all.map((n) => (n.id === id ? { ...n, pinned } : n)),
  );
}

const EMPTY_NOTES: MemoryNote[] = [];
// React hook.
export function useMemoryNotes(): MemoryNote[] {
  const all = useArthStore<MemoryNote[]>(KEYS.memory, EMPTY_NOTES);
  // Filter is OK — useArthStore caches the source array, so identical
  // inputs produce identical filter outputs at the array level (we
  // accept the new ref because the caller does not rely on === for it).
  return all.filter((n) => !n.retired);
}
