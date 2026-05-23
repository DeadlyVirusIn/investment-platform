// Lesson read-receipts + followed-decision store. Local-first, no XP/streaks.
import { readJSON, writeJSON, useLocalValue } from "./local-store";

const LESSONS_KEY = "arthos.lessons.read.v1";
const FOLLOWS_KEY = "arthos.follows.v1";

type ReadStore = { version: 1; slugs: Record<string, string /* ISO date */> };
type FollowStore = { version: 1; ids: Record<string, string /* ISO date */> };

const emptyRead: ReadStore = { version: 1, slugs: {} };
const emptyFollow: FollowStore = { version: 1, ids: {} };

// Lessons ─────────────────────────────────────────────────────────────────────
export function markLessonRead(slug: string, read: boolean) {
  const store = readJSON<ReadStore>(LESSONS_KEY, emptyRead);
  const slugs = { ...store.slugs };
  if (read) slugs[slug] = new Date().toISOString();
  else delete slugs[slug];
  writeJSON<ReadStore>(LESSONS_KEY, { version: 1, slugs });
}

export function useLessonRead(slug: string): boolean {
  const store = useLocalValue<ReadStore>(LESSONS_KEY, emptyRead);
  return Boolean(store?.slugs?.[slug]);
}

export function useReadLessons(): string[] {
  const store = useLocalValue<ReadStore>(LESSONS_KEY, emptyRead);
  return Object.keys(store?.slugs ?? {});
}

// Follows ─────────────────────────────────────────────────────────────────────
export function toggleFollow(journalId: string) {
  const store = readJSON<FollowStore>(FOLLOWS_KEY, emptyFollow);
  const ids = { ...store.ids };
  if (ids[journalId]) delete ids[journalId];
  else ids[journalId] = new Date().toISOString();
  writeJSON<FollowStore>(FOLLOWS_KEY, { version: 1, ids });
}

export function useIsFollowing(journalId: string): boolean {
  const store = useLocalValue<FollowStore>(FOLLOWS_KEY, emptyFollow);
  return Boolean(store?.ids?.[journalId]);
}

export function useFollowedDecisions(): string[] {
  const store = useLocalValue<FollowStore>(FOLLOWS_KEY, emptyFollow);
  return Object.keys(store?.ids ?? {});
}
