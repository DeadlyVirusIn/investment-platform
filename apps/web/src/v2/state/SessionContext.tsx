// M2 session awareness — fetches /api/session once on mount and exposes the
// authenticated user + a refresh()/signOut() the chrome and AccountPage use.
// No token is stored; identity lives only in the HttpOnly cookie.

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from 'react';
import { getSession, logout as apiLogout, type SessionUser } from '../../lib/auth';

interface SessionContextValue {
  user: SessionUser | null;
  authenticated: boolean;
  loading: boolean;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const s = await getSession();
      setUser(s.authenticated ? s.user : null);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    try {
      await apiLogout();
    } catch {
      /* clearing local state below regardless */
    }
    setUser(null);
    await refresh();
  }, [refresh]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <SessionContext.Provider
      value={{ user, authenticated: !!user, loading, refresh, signOut }}
    >
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    // Safe fallback so components don't crash if rendered outside the provider.
    return {
      user: null,
      authenticated: false,
      loading: false,
      refresh: async () => {},
      signOut: async () => {},
    };
  }
  return ctx;
}
