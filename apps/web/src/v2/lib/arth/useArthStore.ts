// Cached-snapshot localStorage hook for Arth stores.
// Critical: useSyncExternalStore demands stable references from
// getSnapshot — otherwise React re-renders infinitely. We cache the
// parsed value keyed by the raw string and only re-parse on change.

import { useSyncExternalStore } from 'react';
import { SCHEMA_VERSION, type Versioned } from './storage';

const isBrowser =
  typeof window !== 'undefined' && typeof localStorage !== 'undefined';

const listeners = new Map<string, Set<() => void>>();
const cache = new Map<string, { raw: string | null; value: unknown }>();

if (isBrowser) {
  window.addEventListener('storage', (e) => {
    if (e.key) {
      cache.delete(e.key);
      listeners.get(e.key)?.forEach((fn) => fn());
    }
  });
}

function readRaw(key: string): string | null {
  if (!isBrowser) return null;
  try { return localStorage.getItem(key); } catch { return null; }
}

function snapshot<T>(key: string, fallback: T): T {
  const raw = readRaw(key);
  const cached = cache.get(key);
  if (cached && cached.raw === raw) return cached.value as T;
  let parsed: T = fallback;
  if (raw) {
    try {
      const payload = JSON.parse(raw) as Versioned<T>;
      if (payload && payload.version === SCHEMA_VERSION) {
        parsed = payload.data;
      }
    } catch { /* fallback */ }
  }
  cache.set(key, { raw, value: parsed });
  return parsed;
}

export function invalidateArthCache(key?: string) {
  if (key) {
    cache.delete(key);
    listeners.get(key)?.forEach((fn) => fn());
  } else {
    cache.clear();
    listeners.forEach((set) => set.forEach((fn) => fn()));
  }
}

export function useArthStore<T>(key: string, fallback: T): T {
  const subscribe = (cb: () => void) => {
    let set = listeners.get(key);
    if (!set) { set = new Set(); listeners.set(key, set); }
    set.add(cb);
    return () => { set!.delete(cb); };
  };
  return useSyncExternalStore(
    subscribe,
    () => snapshot<T>(key, fallback),
    () => fallback,
  );
}
