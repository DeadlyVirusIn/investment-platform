// Arth storage — namespaced localStorage keys.
// Phase 1 (architecture foundation). Client-side only; opt-in sync deferred.

export const NS = 'arthos.v2';

export const KEYS = {
  events:      `${NS}.events`,
  streak:      `${NS}.streak`,
  memory:      `${NS}.memory`,
  decisions:   `${NS}.decisions`,
  briefings:   `${NS}.briefings`,
} as const;

export const SCHEMA_VERSION = 1 as const;

export type Versioned<T> = { version: typeof SCHEMA_VERSION; data: T };

const isBrowser =
  typeof window !== 'undefined' && typeof localStorage !== 'undefined';

export function readVersioned<T>(key: string, fallback: T): T {
  if (!isBrowser) return fallback;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Versioned<T>;
    if (!parsed || parsed.version !== SCHEMA_VERSION) return fallback;
    return parsed.data;
  } catch {
    return fallback;
  }
}

export function writeVersioned<T>(key: string, data: T): void {
  if (!isBrowser) return;
  try {
    const payload: Versioned<T> = { version: SCHEMA_VERSION, data };
    localStorage.setItem(key, JSON.stringify(payload));
    // Invalidate Arth's snapshot cache + fan-out to local subscribers.
    // Direct invalidation avoids reliance on the StorageEvent which
    // does not fire on same-window writes by default.
    import('./useArthStore').then((m) => m.invalidateArthCache(key));
  } catch {
    // quota / disabled — silent
  }
}

export function todayKey(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}
