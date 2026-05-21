// Phase 15e.1 — Today's-read hero on /overview.
//
// The first emotional moment of the page. A single "calm institutional
// strategist" sentence derived from real briefing state, plus an
// optional honest one-line diff vs the user's last visit (Phase 15e.2).
// Renders BEFORE PageChapter so the AI's voice is the first voice the
// user hears, not chrome.
//
// Discipline locks (per Phase 15e brief):
//  - Real inputs only (briefing.headline / briefing.body / diffSentence
//    derived from canonical /api/paper/summary localStorage delta)
//  - No fabricated narrative. Quiet days fall back to the briefing's
//    own honest "No new signals today" copy (semantic freeze pass).
//  - No motion. No atmospheric prose. No generic market commentary.
//  - Compact: single sentence + optional sub-line. NEVER paragraphs.
//  - Calm institutional tone — not hype, not Bloomberg, not startup.

import type { Briefing } from "@/lib/picks/copilot";
import type { DiffStatus } from "@/lib/picks/overview_memory";
import { diffSentence } from "@/lib/picks/overview_memory";
// Phase 15h.3 — freshness-aware hero composition. When the queue is
// stale, the copilot acknowledges the gap calmly instead of speaking
// in confident present-tense about Friday's data as if it were today's.
import type { FreshnessTier } from "@/lib/picks/freshness";
import {
  formatAsOf, isPaperRunPendingWindow, PAPER_REFRESH_HINT_ET,
} from "@/lib/picks/freshness";


export interface OverviewHeroProps {
  briefing: Briefing;
  /** Diff status vs last visit, derived in PicksPage. */
  diff: DiffStatus;
  /** Hide the hero entirely while the page is still loading first
   *  picks fetch — prevents an empty hero flash. */
  ready: boolean;
  /** Phase 15h.3 — aggregate freshness of the picks set (or unknown
   *  when no picks). Drives the cautious-tone branch when stale. */
  freshness?: FreshnessTier;
  /** ISO timestamp of the most-recent pick generation, for the calm
   *  "as of" annotation when stale or degraded. */
  freshAt?: string | null;
}


// Cautious-tone branch — used when aggregate freshness is "stale" or
// "unknown". The hero stops asserting present-tense reads and instead
// acknowledges the system is reading a prior cycle. Copy is drawn
// from the existing briefing.headline so the underlying analysis
// content is preserved; only the framing shifts.
function staleHeadline(briefing: Briefing, freshAt: string | null | undefined): {
  eyebrow: string;
  headline: string;
  body: string;
} {
  const asOf = freshAt ? formatAsOf(freshAt) : "the last completed cycle";
  // Phase 15h.4 — pending-window branch: name the next refresh so
  // the user sees the cycle is still running, not silent.
  const pending = isPaperRunPendingWindow(freshAt);
  if (pending) {
    return {
      eyebrow: "Reading the last cycle",
      headline: `Signals from ${asOf}.`,
      body: `${lowerFirst(briefing.headline)}. ${briefing.body ?? ""} `
        + `Tonight's cycle is still running — ${PAPER_REFRESH_HINT_ET}.`,
    };
  }
  return {
    eyebrow: "Reading the last cycle",
    headline: `Signals from ${asOf}.`,
    // Lowercase the briefing headline to chain it as the second clause.
    body: `${lowerFirst(briefing.headline)}. ${briefing.body ?? ""} `
      + "Today's pipeline has not yet produced new state — copilot is "
      + "reading the previous session's recommendations.",
  };
}


function degradedSuffix(freshAt: string | null | undefined): string {
  const asOf = freshAt ? formatAsOf(freshAt) : "an earlier session";
  return ` Based on overnight signals from ${asOf}.`;
}


function lowerFirst(s: string): string {
  if (!s) return s;
  return s.charAt(0).toLowerCase() + s.slice(1);
}


export default function OverviewHero({
  briefing, diff, ready, freshness = "unknown", freshAt,
}: OverviewHeroProps) {
  if (!ready) return null;

  // Stale + unknown both route through the cautious branch — when we
  // can't prove freshness we don't pretend the data is current.
  const isStaleish = freshness === "stale" || freshness === "unknown";

  let eyebrow: string;
  let headline: string;
  let body: string | null;

  if (isStaleish) {
    const stale = staleHeadline(briefing, freshAt);
    eyebrow = stale.eyebrow;
    headline = stale.headline;
    body = stale.body;
  } else {
    eyebrow = "Today's read";
    headline = briefing.headline;
    body = briefing.body
      ? freshness === "degraded"
        ? briefing.body + degradedSuffix(freshAt)
        : briefing.body
      : null;
  }

  return (
    <section
      className="overview-hero"
      data-test="overview-hero"
      data-freshness={freshness}
    >
      <span className="overview-hero-eyebrow">{eyebrow}</span>
      <h2 className="overview-hero-headline">{headline}</h2>
      {body && (
        <p className="overview-hero-body">{body}</p>
      )}
      <p className="overview-hero-diff" data-kind={diff.kind}>
        {diffSentence(diff)}
      </p>
    </section>
  );
}
