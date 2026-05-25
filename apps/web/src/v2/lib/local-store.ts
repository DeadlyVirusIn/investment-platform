// SSR-safe localStorage subscription helper. Versioned schema migrations live
// next to each consumer; this file just handles read/write/notify plumbing.
//
// Cache contract: useSyncExternalStore requires stable references from
// getSnapshot. We cache the parsed object keyed by the raw localStorage
// string so two render passes against unchanged storage return the same
// object identity. Writes invalidate same-window; cross-window writes
// invalidate via the storage event.
import { useSyncExternalStore } from "react";

const isBrowser = typeof window !== "undefined" && typeof localStorage !== "undefined";

type Listener = () => void;
const listeners = new Map<string, Set<Listener>>();
const snapshotCache = new Map<string, { raw: string | null; value: unknown }>();

function emit(key: string) {
  listeners.get(key)?.forEach((fn) => fn());
}

if (isBrowser) {
  window.addEventListener("storage", (e) => {
    if (e.key) {
      snapshotCache.delete(e.key);
      emit(e.key);
    }
  });
}

export function readJSON<T>(key: string, fallback: T): T {
  if (!isBrowser) return fallback;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function writeJSON<T>(key: string, value: T): void {
  if (!isBrowser) return;
  try {
    localStorage.setItem(key, JSON.stringify(value));
    snapshotCache.delete(key);
    emit(key);
  } catch {
    // quota / disabled storage — fail silently
  }
}

function cachedSnapshot<T>(key: string, fallback: T): T {
  if (!isBrowser) return fallback;
  let raw: string | null = null;
  try { raw = localStorage.getItem(key); } catch { return fallback; }
  const cached = snapshotCache.get(key);
  if (cached && cached.raw === raw) return cached.value as T;
  let parsed: T = fallback;
  if (raw) {
    try { parsed = JSON.parse(raw) as T; } catch { parsed = fallback; }
  }
  snapshotCache.set(key, { raw, value: parsed });
  return parsed;
}

export function useLocalValue<T>(key: string, fallback: T): T {
  const subscribe = (cb: Listener) => {
    if (!listeners.has(key)) listeners.set(key, new Set());
    const set = listeners.get(key)!;
    set.add(cb);
    return () => set.delete(cb);
  };
  const getSnapshot = () => cachedSnapshot<T>(key, fallback);
  const getServerSnapshot = () => fallback;
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
