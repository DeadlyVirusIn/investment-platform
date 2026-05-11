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
//    own honest "AI engine has no fresh suggestions" copy.
//  - No motion. No atmospheric prose. No generic market commentary.
//  - Compact: single sentence + optional sub-line. NEVER paragraphs.
//  - Calm institutional tone — not hype, not Bloomberg, not startup.

import type { Briefing } from "@/lib/picks/copilot";
import type { DiffStatus } from "@/lib/picks/overview_memory";
import { diffSentence } from "@/lib/picks/overview_memory";


export interface OverviewHeroProps {
  briefing: Briefing;
  /** Diff status vs last visit, derived in PicksPage. */
  diff: DiffStatus;
  /** Hide the hero entirely while the page is still loading first
   *  picks fetch — prevents an empty hero flash. */
  ready: boolean;
}


export default function OverviewHero({ briefing, diff, ready }: OverviewHeroProps) {
  if (!ready) return null;

  return (
    <section className="overview-hero" data-test="overview-hero">
      <span className="overview-hero-eyebrow">Today's read</span>
      <h2 className="overview-hero-headline">{briefing.headline}</h2>
      {briefing.body && (
        <p className="overview-hero-body">{briefing.body}</p>
      )}
      <p className="overview-hero-diff" data-kind={diff.kind}>
        {diffSentence(diff)}
      </p>
    </section>
  );
}
