// Phase 15f.3 — Visited-pick memory.
//
// Tracks which pick IDs the user has opened in the PickModal during
// review sessions. Persists to localStorage so the visited state
// survives page reloads and lets the user pick up a long review
// session where they left off.
//
// Discipline (per Phase 15f brief):
//  - NOT an unread-inbox pattern
//  - NOT notification dots
//  - Subtle visual treatment in PickBox CSS (opacity shift), not loud
//  - Bounded to 500 most-recent IDs to keep localStorage small

import { useCallback, useEffect, useState } from "react";


const KEY = "pi-visited-picks";
const MAX_TRACKED = 500;


// FIFO ordered list (newest at end). Set semantics for read; ordered
// for eviction when MAX_TRACKED exceeded.
function readVisitedRaw(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((s): s is string => typeof s === "string");
  } catch {
    return [];
  }
}


function writeVisitedRaw(ids: string[]): void {
  if (typeof window === "undefined") return;
  try {
    const trimmed = ids.length > MAX_TRACKED
      ? ids.slice(ids.length - MAX_TRACKED)
      : ids;
    window.localStorage.setItem(KEY, JSON.stringify(trimmed));
  } catch {
    /* ignore quota errors */
  }
}


export function getVisitedSet(): Set<string> {
  return new Set(readVisitedRaw());
}


export function markVisitedRaw(id: string): void {
  if (!id) return;
  const list = readVisitedRaw();
  // Move-to-back (so eviction prefers oldest).
  const filtered = list.filter(x => x !== id);
  filtered.push(id);
  writeVisitedRaw(filtered);
}


// React hook — returns the current visited Set + a stable mark fn.
// Set is replaced (new instance) on each mark so React re-renders
// downstream consumers reading from the Set.
export function useVisitedPicks(): {
  visited: Set<string>;
  mark: (id: string) => void;
} {
  const [visited, setVisited] = useState<Set<string>>(() => getVisitedSet());

  // Listen to storage events from other tabs so a long-running session
  // sees visited markers from sibling tabs (e.g. opening a pick on one
  // tab while reviewing the queue on another).
  useEffect(() => {
    function onStorage(e: StorageEvent) {
      if (e.key === KEY) setVisited(getVisitedSet());
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const mark = useCallback((id: string) => {
    if (!id) return;
    markVisitedRaw(id);
    setVisited(prev => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  }, []);

  return { visited, mark };
}
