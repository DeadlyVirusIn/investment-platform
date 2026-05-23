// SSR-safe localStorage subscription helper. Versioned schema migrations live
// next to each consumer; this file just handles read/write/notify plumbing.
import { useSyncExternalStore } from "react";

const isBrowser = typeof window !== "undefined" && typeof localStorage !== "undefined";

type Listener = () => void;
const listeners = new Map<string, Set<Listener>>();

function emit(key: string) {
  listeners.get(key)?.forEach((fn) => fn());
}

if (isBrowser) {
  window.addEventListener("storage", (e) => {
    if (e.key) emit(e.key);
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
    emit(key);
  } catch {
    // quota / disabled storage — fail silently
  }
}

export function useLocalValue<T>(key: string, fallback: T): T {
  const subscribe = (cb: Listener) => {
    if (!listeners.has(key)) listeners.set(key, new Set());
    const set = listeners.get(key)!;
    set.add(cb);
    return () => set.delete(cb);
  };
  const getSnapshot = () => readJSON<T>(key, fallback);
  const getServerSnapshot = () => fallback;
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
