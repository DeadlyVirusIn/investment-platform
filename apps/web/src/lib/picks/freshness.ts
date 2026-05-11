// Phase 15h.1 — Derive recommendation freshness locally.
//
// Replaces the broken backend `pick.stale_data` flag (which returns
// `false` on data 65+ hours old per the Phase 15g audit, lying to
// every consumer that treats it as truth).
//
// Three honest tiers based on `pick.generated_at` against the SLA
// proposed in docs/ux/PHASE_15g_freshness_audit.md §5:
//   fresh      < 16h  — current cycle, full confidence
//   degraded   16-30h — last cycle but still actionable
//   stale      > 30h  — copilot must soften tone, hero must acknowledge
//   unknown    no generated_at — treat as stale
//
// SLA constants exported so other surfaces (TopStrip NAV, Today's-read
// hero, freshness annotation pills) can use the same derivation. NO
// per-surface bespoke thresholds.

import type { Pick } from "@/lib/picks/api";


export type FreshnessTier = "fresh" | "degraded" | "stale" | "unknown";


// Hours since the ISO timestamp; null if unparseable.
export function ageHours(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return null;
  const ms = Date.now() - ts;
  if (ms < 0) return 0; // future-dated row treated as just-now
  return ms / 3_600_000;
}


// SLA — recommendations channel. See PHASE_15g_freshness_audit.md §5.
export const RECS_FRESH_HOURS = 16;
export const RECS_DEGRADED_HOURS = 30;


export function freshnessFromAge(hours: number | null): FreshnessTier {
  if (hours == null) return "unknown";
  if (hours < RECS_FRESH_HOURS) return "fresh";
  if (hours < RECS_DEGRADED_HOURS) return "degraded";
  return "stale";
}


// Per-pick freshness — derived from generated_at, NOT from the
// backend's stale_data flag (which is broken per audit).
export function pickFreshness(pick: Pick): FreshnessTier {
  return freshnessFromAge(ageHours(pick.generated_at));
}


// Boolean shortcut for the "is this pick effectively stale" question.
// True for both stale and unknown — unknown timestamps are treated
// conservatively (cannot prove freshness => assume stale).
export function isPickStale(pick: Pick): boolean {
  const tier = pickFreshness(pick);
  return tier === "stale" || tier === "unknown";
}


// Aggregate freshness across a set of picks. Used by the Today's-read
// hero to decide between confident and cautious tones (Phase 15h.3).
//
// Logic:
//   - Empty set                   -> "unknown"
//   - Any pick "stale"            -> "stale"   (cautious; entire set is now suspect)
//   - All picks "fresh"           -> "fresh"
//   - Otherwise (mix of fresh+degraded, or all degraded) -> "degraded"
export function aggregatePickFreshness(picks: Pick[]): FreshnessTier {
  if (picks.length === 0) return "unknown";
  let anyStale = false;
  let anyDegraded = false;
  let anyUnknown = false;
  for (const p of picks) {
    const t = pickFreshness(p);
    if (t === "stale") anyStale = true;
    else if (t === "degraded") anyDegraded = true;
    else if (t === "unknown") anyUnknown = true;
  }
  if (anyStale || anyUnknown) return "stale";
  if (anyDegraded) return "degraded";
  return "fresh";
}
