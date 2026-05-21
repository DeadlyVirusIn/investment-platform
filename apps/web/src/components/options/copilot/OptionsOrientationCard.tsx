// OptionsOrientationCard — Phase H.6.
//
// Emotional onramp at the top of each primary surface. Shown ONCE
// per surface per browser; dismissed via "Got it" sets a localStorage
// key and the card never returns.
//
// Voice rules (locked):
//   * First-person plural ("we", "our") — strategist tone.
//   * Explains how to THINK about the surface, not how the UI works.
//   * One sentence, optionally one supporting line. Never multi-step.
//   * Calm verbs ("we summarize", "we surface", "we explain", "we manage").
//   * Avoid: setup-tour energy ("Welcome!"), feature-list energy
//     ("Here you can…"), congratulatory energy.

import { useEffect, useState } from "react";


const STORAGE_PREFIX = "opt-orient-v1:";


export type OrientationSurface =
  | "today"
  | "opportunities"
  | "research"
  | "holdings"
  | "journal"
  | "approaches"
  | "learn";


interface OrientationCopy {
  sentence: string;
  supporting?: string;
}


// Copy is the entire feature. Treat these strings as locked product
// language. Operator can update with explicit reason; never auto-edit.
const COPY: Record<OrientationSurface, OrientationCopy> = {
  today: {
    sentence:
      "We use Today to summarize what actually deserves attention right now.",
    supporting:
      "If the day is quiet, we'll say so. If something matters, "
      + "it'll be the first thing you see.",
  },
  opportunities: {
    sentence:
      "Most setups never become conviction. This page only surfaces "
      + "what we think is worth your time.",
    supporting:
      "Each card is one strategist sentence and one number. The "
      + "rest of the detail lives one click away.",
  },
  research: {
    sentence:
      "Research is where we explain why the strategist believes what "
      + "it believes.",
    supporting:
      "Pick any underlying for our posture, the volatility regime, "
      + "the catalysts ahead, and which strategies currently fit.",
  },
  holdings: {
    sentence:
      "This page exists to answer one question: do I need to do "
      + "anything right now?",
    supporting:
      "If a position is broken, you'll see it first. If everything "
      + "is held, we'll say that too.",
  },
  journal: {
    sentence:
      "Journal is our memory — every decision, every change of "
      + "mind, every outcome we noticed.",
    supporting:
      "Pick any entry to see the thinking that led to it or the "
      + "lifecycle events that followed.",
  },
  approaches: {
    sentence:
      "Different markets call for different ways of thinking. "
      + "These are the seven we lean on.",
    supporting:
      "Each approach tells you when it fits the current regime — "
      + "and when it doesn't.",
  },
  learn: {
    sentence:
      "One playbook per strategy. Open the one you want to "
      + "understand.",
    supporting:
      "Every playbook covers when to use it, when not to, and how "
      + "theta + IV will behave while you're in it.",
  },
};


function storageKey(surface: OrientationSurface): string {
  return `${STORAGE_PREFIX}${surface}`;
}


function hasSeen(surface: OrientationSurface): boolean {
  try {
    return !!window.localStorage.getItem(storageKey(surface));
  } catch {
    // Privacy mode / disabled storage — show the orientation every
    // time, which is acceptable for a calm one-sentence card.
    return false;
  }
}


function markSeen(surface: OrientationSurface): void {
  try {
    window.localStorage.setItem(
      storageKey(surface),
      new Date().toISOString(),
    );
  } catch {
    /* no-op */
  }
}


export interface OptionsOrientationCardProps {
  surface: OrientationSurface;
  /** Override the copy when the surface variant needs something
   *  different (e.g. canary view of Holdings). Optional. */
  overrideCopy?: OrientationCopy;
}


export default function OptionsOrientationCard({
  surface, overrideCopy,
}: OptionsOrientationCardProps) {
  const [visible, setVisible] = useState<boolean>(false);

  useEffect(() => {
    // Defer to next tick so SSR / hydration sees a stable false →
    // then we reveal client-side only when localStorage confirms
    // the user has not dismissed.
    setVisible(!hasSeen(surface));
  }, [surface]);

  if (!visible) return null;

  const copy = overrideCopy ?? COPY[surface];

  return (
    <section
      className="opt-orientation"
      data-test={`opt-orientation-${surface}`}
      role="note"
      aria-label="Orientation"
    >
      <p className="opt-orientation-sentence">{copy.sentence}</p>
      {copy.supporting && (
        <p className="opt-orientation-supporting">{copy.supporting}</p>
      )}
      <button
        type="button"
        className="opt-orientation-dismiss"
        onClick={() => {
          markSeen(surface);
          setVisible(false);
        }}
        data-test={`opt-orientation-dismiss-${surface}`}
      >
        Got it
      </button>
    </section>
  );
}
