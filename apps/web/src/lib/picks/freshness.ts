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


// ============================================================
// Phase 15h.2 — calm "as of" formatting helpers
// ============================================================
// Format an ISO timestamp into the institutional-strategist style
// the freshness pills use: "Mon 9:30 AM ET" / "Sat 9 May" / "today
// 9:30 AM" depending on age. Never raw ISO. Never long form.

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}


// Returns a calm "as of" sentence for any ISO timestamp.
// Examples:
//   today  → "9:30 AM"
//   < 7d   → "Sat 9 May 9:30 AM"
//   older  → "9 May 2026"
export function formatAsOf(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return "—";
  const d = new Date(ts);
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  const ageDays = Math.floor((now.getTime() - ts) / (24 * 3_600_000));

  let hh = d.getHours();
  const mm = pad2(d.getMinutes());
  const ampm = hh >= 12 ? "PM" : "AM";
  hh = hh % 12; if (hh === 0) hh = 12;
  const time = `${hh}:${mm} ${ampm}`;

  if (sameDay) return time;

  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  if (ageDays < 7) {
    // "Sat 9 May 9:30 AM"
    return `${days[d.getDay()]} ${d.getDate()} ${months[d.getMonth()]} ${time}`;
  }
  // Older — drop the time, keep date only
  return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
}


// Generic freshness tier from any ISO timestamp using the same
// recommendations SLA. The PortfolioSnapshot + TopStrip surfaces use
// this for paper/summary.last_decision_ts. Per Phase 15g audit: a
// finer per-channel SLA (intra-market-hours portfolio refresh < 30m)
// is appropriate but defers until the system actually runs that often;
// for now one SLA across surfaces keeps the UI tone coherent.
export function freshnessFromTs(iso: string | null | undefined): FreshnessTier {
  return freshnessFromAge(ageHours(iso));
}
