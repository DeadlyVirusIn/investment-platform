/**
 * M5 demand-validation client helper. Collect-only. Uses the credentials:'include'
 * fetch layer (session cookie attaches user_id server-side when logged in; works
 * anonymously too). Failures are the caller's to swallow — feedback must never
 * block reading a recommendation.
 */

import { apiPost } from './api';

export type SignalType =
  | 'trust_useful'
  | 'trust_not_useful'
  | 'would_use_again'
  | 'would_not_use_again'
  | 'confusing'
  | 'beta_interest'
  | 'investor_interest'
  | 'feedback_text';

export type FeedbackSurface = 'pick_detail' | 'options_detail' | 'account' | 'profile' | 'discover';

export function sendSignal(
  surface: FeedbackSurface,
  signalType: SignalType,
  value?: string,
  payload?: Record<string, unknown>,
): Promise<{ ok: boolean }> {
  return apiPost<{ ok: boolean }>('/feedback/signal', {
    surface,
    signal_type: signalType,
    value: value || undefined,
    payload: payload || undefined,
  });
}
