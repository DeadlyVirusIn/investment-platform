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


// Returns a calm "as of" sentence for any ISO timestamp or date-only
// string.
//
// Examples:
//   "2026-05-12T09:30:00Z" same day → "9:30 AM"   (full timestamp, time included)
//   "2026-05-09T03:30:00Z" < 7d     → "Fri 8 May 11:30 PM" (full timestamp, ET-rendered)
//   "2026-05-09"           < 7d     → "Sat 9 May" (date-only — no fake time)
//   any timestamp          older    → "9 May 2026"
//
// Phase 15h.2 / 15g.II — Date-only inputs (e.g. paper.summary.as_of_date
// = "2026-05-09") are parsed at LOCAL midnight (not UTC midnight) and
// rendered without a time component. The previous implementation
// parsed "2026-05-09" via Date.parse() which interprets date-only as
// UTC midnight per JS spec; in EDT that displays as "Fri 8 May 8 PM"
// — a misleading 1-day shift backwards plus a fake time that the
// source never carried. The fix preserves backwards-compat for full
// ISO timestamps with explicit time components.
export function formatAsOf(iso: string | null | undefined): string {
  if (!iso) return "—";

  // Detect bare-date format YYYY-MM-DD (no time component).
  const isDateOnly = /^\d{4}-\d{2}-\d{2}$/.test(iso);
  // For date-only inputs, parse at LOCAL midnight to avoid the
  // UTC-midnight TZ artifact. For full timestamps, parse as-is.
  const ts = isDateOnly
    ? Date.parse(`${iso}T00:00:00`)
    : Date.parse(iso);
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
  // Date-only sources have no real time — never append one.
  const time = isDateOnly ? null : `${hh}:${mm} ${ampm}`;

  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  if (sameDay) {
    // Same day + full timestamp -> just the time (existing behaviour)
    // Same day + date-only -> "today" date label
    return time ?? `${days[d.getDay()]} ${d.getDate()} ${months[d.getMonth()]}`;
  }

  if (ageDays < 7) {
    // < 7d: "Sat 9 May 9:30 AM" with time (full ts) OR "Sat 9 May" (date-only)
    const dateLabel = `${days[d.getDay()]} ${d.getDate()} ${months[d.getMonth()]}`;
    return time ? `${dateLabel} ${time}` : dateLabel;
  }

  // Older — date only, regardless of source granularity
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


// ============================================================
// Phase 15h.4 — staged-freshness pending-window helpers
// ============================================================
// Detect the recurring 22:30–23:30 ET Mon–Fri window where the
// daily ingest + recommendations cron has fired but the paper-trading
// run (scheduled 23:30 ET) has not yet completed. During this window
// /api/paper/summary.as_of_date still reflects the previous session
// even though tonight's pipeline IS running. The Portfolio + Overview
// surfaces use this signal to render a staged copy that names the
// pending step + the next refresh time, instead of just saying
// "Reading the last completed cycle · Sat 9 May" (which reads as
// abandonment).
//
// Pure client-side derivation. No backend call. The heuristic is
// based on the cron cadence in job_schedule:
//   ingest_prices_daily              0  22 * * 1-5
//   run_recommendations_for_all_…   30  22 * * 1-5
//   score_recommendation_outcomes    0  23 * * 1-5
//   run_paper_trading               30  23 * * 1-5

// Parts in America/New_York timezone for any Date.
function etParts(now: Date): { year: number; month: number; day: number; hour: number; minute: number; weekday: number } {
  // Intl returns the ET wall-clock components.
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
    weekday: "short",
  });
  const parts: Record<string, string> = {};
  for (const p of fmt.formatToParts(now)) parts[p.type] = p.value;
  const wmap: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  return {
    year:    parseInt(parts.year, 10),
    month:   parseInt(parts.month, 10),
    day:     parseInt(parts.day, 10),
    // "24" is returned by some impls for midnight; normalize.
    hour:    parseInt(parts.hour, 10) % 24,
    minute:  parseInt(parts.minute, 10),
    weekday: wmap[parts.weekday] ?? -1,
  };
}


// True if `now` is the recurring pending window: Mon–Fri ET, between
// 22:00 and 23:30 ET (inclusive of 22:00, exclusive of 23:30) AND
// `asOfISO` (paper summary's as_of_date) names a date strictly before
// today's ET date — i.e. the paper-trading snapshot has not yet
// rolled forward to today.
export function isPaperRunPendingWindow(
  asOfISO: string | null | undefined,
  now: Date = new Date(),
): boolean {
  if (!asOfISO) return false;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(asOfISO);
  if (!m) return false;
  const asOfY = parseInt(m[1], 10);
  const asOfM = parseInt(m[2], 10);
  const asOfD = parseInt(m[3], 10);

  const et = etParts(now);
  if (et.weekday < 1 || et.weekday > 5) return false; // Mon–Fri only
  // Window: [22:00, 23:30) ET
  const minutesInDay = et.hour * 60 + et.minute;
  if (minutesInDay < 22 * 60) return false;
  if (minutesInDay >= 23 * 60 + 30) return false;

  // as_of strictly before today (ET).
  if (asOfY !== et.year)  return asOfY  < et.year;
  if (asOfM !== et.month) return asOfM  < et.month;
  return asOfD < et.day;
}


// Copy fragment used by the staged surfaces. Kept here so tests +
// future tone tweaks live next to the detector.
export const PAPER_REFRESH_HINT_ET = "today's portfolio refresh at 11:30 PM ET";
