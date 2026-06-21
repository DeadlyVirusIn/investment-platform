/**
 * M3 profile client helpers. Collect-only investing profile (no recommendation
 * behavior yet). Uses the credentials:'include' fetch layer; session cookie
 * authenticates. Nothing sensitive is collected.
 */

import { apiGet, apiPut } from './api';

export interface ProfileData {
  investing_experience: string | null;
  investing_goal: string | null;
  risk_comfort: string | null;
  time_horizon: string | null;
  preferred_style: string | null;
  liquidity_need: string | null;
  options_experience: string | null;
}

export interface ProfileResponse {
  profile: ProfileData;
  complete: boolean;
}

export function getProfile(): Promise<ProfileResponse> {
  return apiGet<ProfileResponse>('/profile');
}

export function saveProfile(values: Partial<ProfileData>): Promise<ProfileResponse> {
  return apiPut<ProfileResponse>('/profile', values);
}
