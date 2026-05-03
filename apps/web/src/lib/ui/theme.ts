// Phase 3 — theme bootstrap + persistence.
// Default: dark. Persisted in localStorage["theme"].
// Applied via [data-theme] on <html>.

import { useEffect, useState } from "react";

export type ThemeMode = "dark" | "light";

const KEY = "theme";

function readInitial(): ThemeMode {
  if (typeof window === "undefined") return "dark";
  try {
    const v = window.localStorage.getItem(KEY);
    return v === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

function applyTheme(t: ThemeMode) {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", t);
}

// Set theme attribute as early as possible to avoid flash. Call this in
// the entry-point module so every render past mount sees correct tokens.
export function bootstrapTheme(): ThemeMode {
  const t = readInitial();
  applyTheme(t);
  return t;
}

export function useTheme(): [ThemeMode, (next: ThemeMode) => void] {
  const [mode, setMode] = useState<ThemeMode>(() => readInitial());
  useEffect(() => {
    applyTheme(mode);
    try {
      window.localStorage.setItem(KEY, mode);
    } catch {
      /* ignore */
    }
  }, [mode]);
  return [mode, setMode];
}
