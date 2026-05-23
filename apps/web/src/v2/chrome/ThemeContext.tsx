// V2 theme — local context, persists to localStorage["v2-theme"].
// Applied via [data-theme] attribute on the .v2-root element by V2App,
// NOT on <html> — keeps the existing app's theming untouched.

import {
  useCallback,
  useEffect,
  useState,
  createContext,
  useContext,
  type ReactNode,
} from 'react';

type Theme = 'light' | 'dark';

interface ThemeValue {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeValue | undefined>(undefined);
const STORAGE_KEY = 'v2-theme';

function detectInitial(): Theme {
  if (typeof window === 'undefined') return 'dark';
  // Screenshot override — visit any v2 URL with ?theme=dark or
  // ?theme=light to force the palette for headless capture. Has no
  // effect on real users (the URL params they'd type won't include it).
  try {
    const q = new URLSearchParams(window.location.search).get('theme');
    if (q === 'dark' || q === 'light') return q;
  } catch {
    /* noop */
  }
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch {
    /* noop */
  }
  const prefersLight = window.matchMedia?.(
    '(prefers-color-scheme: light)'
  ).matches;
  return prefersLight ? 'light' : 'dark';
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(detectInitial);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* noop */
    }
  }, [theme]);

  const toggle = useCallback(() => {
    setThemeState((t) => (t === 'dark' ? 'light' : 'dark'));
  }, []);

  return (
    <ThemeContext.Provider
      value={{
        theme,
        setTheme: setThemeState,
        toggle,
      }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
