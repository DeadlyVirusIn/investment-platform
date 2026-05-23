// Local-first reflection store. Versioned schema — bump SCHEMA_VERSION and add
// a migration branch when the shape changes. Future kinds (paper-trade review,
// confidence calibration, thesis-review) plug in by extending ReflectionKind.
import { readJSON, writeJSON, useLocalValue } from "./local-store";

export const STORAGE_KEY = "arthos.reflections.v1";
const SCHEMA_VERSION = 1 as const;

export type ReflectionKind =
  | "start-here"
  | "lesson-capture"
  | "journal-note"
  | "paper-trade-review"
  | "mistake"
  | "thesis-review";

export type Reflection = {
  id: string;
  kind: ReflectionKind;
  /** Slug, journal id, or trade id depending on kind. Empty for free notes. */
  targetId: string;
  /** Optional second-person prompt that produced the reflection. */
  prompt?: string;
  body: string;
  /** ISO timestamp. */
  createdAt: string;
};

type Store = {
  version: typeof SCHEMA_VERSION;
  reflections: Reflection[];
};

const empty: Store = { version: SCHEMA_VERSION, reflections: [] };

function load(): Store {
  const raw = readJSON<Store>(STORAGE_KEY, empty);
  if (!raw || raw.version !== SCHEMA_VERSION) return empty;
  return raw;
}

export function listReflections(): Reflection[] {
  return [...load().reflections].sort((a, b) =>
    b.createdAt.localeCompare(a.createdAt),
  );
}

export function findReflection(kind: ReflectionKind, targetId: string): Reflection | undefined {
  return load().reflections.find((r) => r.kind === kind && r.targetId === targetId);
}

export function saveReflection(input: Omit<Reflection, "id" | "createdAt"> & { id?: string }): Reflection {
  const store = load();
  const now = new Date().toISOString();
  const id = input.id ?? `${input.kind}-${input.targetId || "free"}-${Date.now()}`;
  const existingIdx = store.reflections.findIndex(
    (r) => r.kind === input.kind && r.targetId === input.targetId,
  );
  const next: Reflection = {
    id,
    kind: input.kind,
    targetId: input.targetId,
    prompt: input.prompt,
    body: input.body,
    createdAt: existingIdx >= 0 ? store.reflections[existingIdx].createdAt : now,
  };
  const reflections = [...store.reflections];
  if (existingIdx >= 0) reflections[existingIdx] = next;
  else reflections.push(next);
  writeJSON<Store>(STORAGE_KEY, { version: SCHEMA_VERSION, reflections });
  return next;
}

export function deleteReflection(id: string) {
  const store = load();
  writeJSON<Store>(STORAGE_KEY, {
    version: SCHEMA_VERSION,
    reflections: store.reflections.filter((r) => r.id !== id),
  });
}

// React hooks ─────────────────────────────────────────────────────────────────
export function useReflections(): Reflection[] {
  const store = useLocalValue<Store>(STORAGE_KEY, empty);
  if (!store || store.version !== SCHEMA_VERSION) return [];
  return [...store.reflections].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export function useReflection(kind: ReflectionKind, targetId: string): Reflection | undefined {
  const all = useReflections();
  return all.find((r) => r.kind === kind && r.targetId === targetId);
}
