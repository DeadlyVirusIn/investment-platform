// V2 user preferences — onboarding, watchlist, highlights, a11y.
// Storage key "v2-prefs" keeps this isolated from any existing prefs.

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  createContext,
  useContext,
  type ReactNode,
} from 'react';

export type ReaderLevel = 'beginner' | 'building' | 'experienced';

export interface Highlight {
  id: string;
  lessonSlug: string;
  lessonTitle: string;
  text: string;
  createdAt: number;
}

interface PrefsState {
  hasOnboarded: boolean;
  level?: ReaderLevel;
  topics: string[];
  watchlist: string[];
  highlights: Highlight[];
  dailyReadingTime?: string;
  notificationsEnabled: boolean;
  reducedMotion: boolean;
  largerText: boolean;
  // MVP Phase A — first/last visit tracking. Used by Salutation (Day N
  // counter, long-gap rule) and FirstPositionPanel (cold-start guard).
  // Date-only ISO strings (YYYY-MM-DD) to avoid timezone-diff drift on
  // day-count computation.
  firstVisitedDate?: string;
  lastVisitedDate?: string;
}

const DEFAULTS: PrefsState = {
  hasOnboarded: false,
  level: undefined,
  topics: [],
  watchlist: [],
  highlights: [],
  dailyReadingTime: '07:00',
  notificationsEnabled: false,
  reducedMotion: false,
  largerText: false,
  firstVisitedDate: undefined,
  lastVisitedDate: undefined,
};

interface PrefsValue extends PrefsState {
  // MVP Phase A — captured at provider-mount, immutable for session.
  // Salutation reads this to compute "long-gap" rule and Day-N.
  previousVisitDate?: string;
  completeOnboarding: (level: ReaderLevel, topics: string[], time: string) => void;
  toggleWatchlist: (symbol: string) => void;
  inWatchlist: (symbol: string) => boolean;
  addHighlight: (lessonSlug: string, lessonTitle: string, text: string) => void;
  removeHighlight: (id: string) => void;
  setLevel: (l: ReaderLevel) => void;
  setTopics: (t: string[]) => void;
  setDailyReadingTime: (t: string) => void;
  setNotificationsEnabled: (b: boolean) => void;
  setReducedMotion: (b: boolean) => void;
  setLargerText: (b: boolean) => void;
  resetPrefs: () => void;
}

const Ctx = createContext<PrefsValue | undefined>(undefined);
const KEY = 'v2-prefs';

function load(): PrefsState {
  if (typeof window === 'undefined') return DEFAULTS;
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch {
    return DEFAULTS;
  }
}

function save(s: PrefsState) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* noop */
  }
}

export function UserPrefsProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PrefsState>(() => {
    const base = load();
    // Screenshot helpers — URL params seed state for headless capture:
    //   ?seedWatchlist=AMAT,TSLA,NFLX  populates watchlist
    //   ?seedVisits=12                 seeds firstVisitedDate N days ago
    //                                   and lastVisitedDate as yesterday
    if (typeof window === 'undefined') return base;
    try {
      const params = new URLSearchParams(window.location.search);
      const patch: Partial<PrefsState> = {};

      const watchlistSeed = params.get('seedWatchlist');
      if (watchlistSeed) {
        const tokens = watchlistSeed
          .split(',')
          .map((t) => t.trim().toUpperCase())
          .filter(Boolean);
        if (tokens.length > 0) {
          patch.watchlist = Array.from(
            new Set([...base.watchlist, ...tokens])
          );
        }
      }

      const visitsSeed = params.get('seedVisits');
      if (visitsSeed) {
        const n = parseInt(visitsSeed, 10);
        if (Number.isFinite(n) && n > 0) {
          const today = new Date();
          const first = new Date(
            today.getTime() - (n - 1) * 24 * 60 * 60 * 1000
          );
          const yesterday = new Date(
            today.getTime() - 24 * 60 * 60 * 1000
          );
          patch.firstVisitedDate = first.toISOString().slice(0, 10);
          patch.lastVisitedDate = yesterday.toISOString().slice(0, 10);
        }
      }

      if (Object.keys(patch).length === 0) return base;
      return { ...base, ...patch };
    } catch {
      return base;
    }
  });

  useEffect(() => {
    save(state);
  }, [state]);

  // MVP Phase A — capture previous-visit value AT MOUNT (immutable
  // for this session). Salutation reads `previousVisitDate` for the
  // long-gap rule and avoids the chicken-egg of "lastVisitedDate just
  // got updated to today" overwriting yesterday's value.
  const [previousVisitDate] = useState<string | undefined>(() => {
    return load().lastVisitedDate;
  });

  // On mount: set firstVisitedDate if absent; update lastVisitedDate
  // to today. Effect runs after first paint, so any component that
  // reads `previousVisitDate` (immutable above) sees yesterday's value.
  useEffect(() => {
    const today = new Date().toISOString().slice(0, 10);
    setState((s) => {
      const patch: Partial<PrefsState> = {};
      if (!s.firstVisitedDate) patch.firstVisitedDate = today;
      if (s.lastVisitedDate !== today) patch.lastVisitedDate = today;
      if (Object.keys(patch).length === 0) return s;
      return { ...s, ...patch };
    });
  }, []);

  // Apply accessibility prefs to the v2-root container, not <html>.
  useEffect(() => {
    document.querySelectorAll('.v2-root').forEach((el) => {
      el.classList.toggle('reduced-motion', state.reducedMotion);
      el.classList.toggle('larger-text', state.largerText);
    });
  }, [state.reducedMotion, state.largerText]);

  const completeOnboarding = useCallback(
    (level: ReaderLevel, topics: string[], time: string) => {
      setState((s) => ({
        ...s,
        hasOnboarded: true,
        level,
        topics,
        dailyReadingTime: time,
      }));
    },
    []
  );

  const toggleWatchlist = useCallback((symbol: string) => {
    setState((s) => ({
      ...s,
      watchlist: s.watchlist.includes(symbol)
        ? s.watchlist.filter((x) => x !== symbol)
        : [...s.watchlist, symbol],
    }));
  }, []);

  const inWatchlist = useCallback(
    (symbol: string) => state.watchlist.includes(symbol),
    [state.watchlist]
  );

  const addHighlight = useCallback(
    (lessonSlug: string, lessonTitle: string, text: string) => {
      setState((s) => ({
        ...s,
        highlights: [
          {
            id: `h-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
            lessonSlug,
            lessonTitle,
            text,
            createdAt: Date.now(),
          },
          ...s.highlights,
        ],
      }));
    },
    []
  );

  const removeHighlight = useCallback((id: string) => {
    setState((s) => ({
      ...s,
      highlights: s.highlights.filter((h) => h.id !== id),
    }));
  }, []);

  const setLevel = useCallback(
    (l: ReaderLevel) => setState((s) => ({ ...s, level: l })),
    []
  );
  const setTopics = useCallback(
    (t: string[]) => setState((s) => ({ ...s, topics: t })),
    []
  );
  const setDailyReadingTime = useCallback(
    (t: string) => setState((s) => ({ ...s, dailyReadingTime: t })),
    []
  );
  const setNotificationsEnabled = useCallback(
    (b: boolean) => setState((s) => ({ ...s, notificationsEnabled: b })),
    []
  );
  const setReducedMotion = useCallback(
    (b: boolean) => setState((s) => ({ ...s, reducedMotion: b })),
    []
  );
  const setLargerText = useCallback(
    (b: boolean) => setState((s) => ({ ...s, largerText: b })),
    []
  );
  const resetPrefs = useCallback(() => setState(DEFAULTS), []);

  const value = useMemo<PrefsValue>(
    () => ({
      ...state,
      previousVisitDate,
      completeOnboarding,
      toggleWatchlist,
      inWatchlist,
      addHighlight,
      removeHighlight,
      setLevel,
      setTopics,
      setDailyReadingTime,
      setNotificationsEnabled,
      setReducedMotion,
      setLargerText,
      resetPrefs,
    }),
    [
      state,
      previousVisitDate,
      completeOnboarding,
      toggleWatchlist,
      inWatchlist,
      addHighlight,
      removeHighlight,
      setLevel,
      setTopics,
      setDailyReadingTime,
      setNotificationsEnabled,
      setReducedMotion,
      setLargerText,
      resetPrefs,
    ]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useUserPrefs() {
  const v = useContext(Ctx);
  if (!v) throw new Error('useUserPrefs must be used within UserPrefsProvider');
  return v;
}
