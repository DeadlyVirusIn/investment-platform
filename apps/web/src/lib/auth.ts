/**
 * M2 auth client helpers. Thin wrappers over the api.ts fetch layer, which
 * already sends `credentials: 'include'` so the HttpOnly arthos_session cookie
 * flows. We NEVER store the password or any auth token client-side — the
 * session lives only in the HttpOnly cookie set by the backend.
 */

import { apiGet, apiPost } from './api';

export interface SessionUser {
  id: string;
  email: string | null;
  display_name: string | null;
}

export interface SessionState {
  authenticated: boolean;
  user: SessionUser | null;
}

export interface AuthResult {
  ok: boolean;
  user: SessionUser;
}

export function getSession(): Promise<SessionState> {
  return apiGet<SessionState>('/session');
}

export function signup(email: string, password: string, displayName?: string): Promise<AuthResult> {
  return apiPost<AuthResult>('/signup', {
    email,
    password,
    display_name: displayName || undefined,
  });
}

export function login(email: string, password: string): Promise<AuthResult> {
  return apiPost<AuthResult>('/login', { email, password });
}

export function logout(): Promise<{ ok: boolean }> {
  return apiPost<{ ok: boolean }>('/logout', {});
}
