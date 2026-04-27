// Phase 11L — Guardrails toggle (UI-only, default ON).
//
// Persists in localStorage. NEVER controls backend behaviour;
// when OFF, only the visual emphasis of the 11K interpretation
// panels is dimmed/hidden — the underlying API responses still
// carry the same guardrail copy and the verbatim banner text on
// every page is unaffected.

import { createContext, useContext, useEffect, useMemo, useState } from 'react';

const STORAGE_KEY = 'options.guardrailsOn';

interface GuardrailsToggleCtx {
  on: boolean;
  setOn: (next: boolean) => void;
  toggle: () => void;
}

const Ctx = createContext<GuardrailsToggleCtx>({
  on: true,
  setOn: () => undefined,
  toggle: () => undefined,
});

function _readInitial(): boolean {
  if (typeof window === 'undefined') return true;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v === null) return true;        // default ON
    return v === '1' || v === 'true';
  } catch {
    return true;
  }
}

export function GuardrailsToggleProvider({
  children,
}: { children: React.ReactNode }) {
  const [on, setOnState] = useState<boolean>(_readInitial);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, on ? '1' : '0');
    } catch {
      /* ignore */
    }
  }, [on]);

  const value = useMemo<GuardrailsToggleCtx>(() => ({
    on,
    setOn: setOnState,
    toggle: () => setOnState((v) => !v),
  }), [on]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useGuardrailsToggle(): GuardrailsToggleCtx {
  return useContext(Ctx);
}
