// Phase SYSTEM-UI-BEGINNER — UI mode toggle.
// Persists to localStorage. Default guided for new users (no prior key).

import { useEffect, useState } from "react";

export type UIMode = "guided" | "expert";

const KEY = "TRADING_UI_MODE";

export function getInitialMode(): UIMode {
  if (typeof window === "undefined") return "guided";
  const v = window.localStorage.getItem(KEY);
  if (v === "expert" || v === "guided") return v;
  return "guided";
}

export function setMode(mode: UIMode): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, mode);
  window.dispatchEvent(new CustomEvent("ui-mode-change", { detail: mode }));
}

export function useUIMode(): [UIMode, (m: UIMode) => void] {
  const [mode, setState] = useState<UIMode>(() => getInitialMode());
  useEffect(() => {
    const handler = (e: Event) => {
      const m = (e as CustomEvent<UIMode>).detail;
      if (m === "guided" || m === "expert") setState(m);
    };
    window.addEventListener("ui-mode-change", handler);
    return () => window.removeEventListener("ui-mode-change", handler);
  }, []);
  return [mode, (m) => { setMode(m); setState(m); }];
}
