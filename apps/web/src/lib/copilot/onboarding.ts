// UX-3D Phase A — onboarding flag helpers.
//
// Exactly 3 localStorage flags. Used only to suppress a clause that
// has fired once. NEVER used to personalise content. NEVER stored
// server-side. NEVER tied to a user identity.
//
// Failure modes (private mode, disabled storage, quota exceeded) are
// swallowed: a clause that can't be marked-seen will simply re-fire
// next session. Better than crashing.

import type { OnboardingFlag } from "./types";


const STORAGE_PREFIX = ""; // flag names are already prefixed with `ux_`


function _safeStorage(): Storage | null {
  try {
    if (typeof window === "undefined") return null;
    return window.localStorage ?? null;
  } catch {
    return null;
  }
}


/** True iff the flag has previously been set on this browser. */
export function hasSeen(flag: OnboardingFlag): boolean {
  const s = _safeStorage();
  if (!s) return false;
  try {
    return s.getItem(STORAGE_PREFIX + flag) === "1";
  } catch {
    return false;
  }
}


/** Mark a flag seen. Idempotent. Failures are swallowed — at worst
 *  the clause renders again next visit, which is acceptable. */
export function markSeen(flag: OnboardingFlag): void {
  const s = _safeStorage();
  if (!s) return;
  try {
    s.setItem(STORAGE_PREFIX + flag, "1");
  } catch {
    // private mode / quota exceeded — accept silently
  }
}


/** Test-only: clear every onboarding flag. NEVER call from
 *  production code. Exposed so future component tests can reset
 *  state cleanly. */
export function _resetAllOnboardingFlags(): void {
  const s = _safeStorage();
  if (!s) return;
  const flags: OnboardingFlag[] = [
    "ux_seen_quiet_day",
    "ux_seen_first_position",
    "ux_seen_first_exit",
  ];
  for (const f of flags) {
    try { s.removeItem(STORAGE_PREFIX + f); } catch { /* swallow */ }
  }
}
