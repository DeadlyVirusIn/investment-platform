// UX-8B Phase 8B-1 — Portfolio Weather Room hero.
//
// The single visual element that proves the entire UX-8 direction.
// Renders:
//
//   * Date masthead    (12px tracked uppercase)
//   * Condition label  (11px tracked uppercase, accent color)
//   * Condition sentence (32px Source Serif 4 with 2px accent bar)
//   * Pressure-band overlay (CSS gradient on the block, alpha-driven)
//
// The 2px accent bar (the single bold move from R5) scales in over
// 100ms ~440ms after first paint, anchored top. After that, NO
// motion. The bar is structural, not decorative.
//
// All atmosphere + accent colors come from CSS custom properties
// scoped to body[data-condition="…"]. The component itself is
// stateless and accepts only the literal text.

import { useEffect, useRef } from "react";

import type { Condition } from "@/lib/copilot/condition";


export interface ConditionBlockProps {
  /** Date in display form, e.g. "MAY 8". Caller localises. */
  date: string;
  /** One of STABLE / PRESSURED / OPPORTUNISTIC. */
  condition: Condition;
  /** The composed condition sentence. MUST contain a numeric
   *  anchor when condition === "PRESSURED" (visible-condition-
   *  explanation contract from UX-8 §4.3). */
  sentence: string;
  className?: string;
}


/** Delay (ms) before the 2px accent bar's scaleY entrance fires.
 *  Sequence: date 0-100ms, label 140-240ms, sentence 240-340ms,
 *  bar 440-540ms. The bar is the final element; landing the
 *  AI's signature LAST. */
const ACCENT_BAR_DELAY_MS = 440;


export default function ConditionBlock(
  { date, condition, sentence, className }: ConditionBlockProps,
) {
  const ref = useRef<HTMLElement | null>(null);

  // Trigger the accent-bar scaleY animation by adding the
  // is-revealed class. CSS handles the actual transition.
  // Reduced-motion media query collapses the transition to 0ms.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const t = window.setTimeout(() => {
      el.classList.add("is-revealed");
    }, ACCENT_BAR_DELAY_MS);
    return () => window.clearTimeout(t);
  }, [condition, sentence]);

  return (
    <header
      ref={ref}
      className={`ux8-condition-block ${className ?? ""}`.trim()}
      data-test="condition-block"
      data-source={`condition:${condition},date:${date}`}
      role="banner"
    >
      <div className="ux8-condition-column">
        <p className="ux8-condition-date" data-test="condition-date">
          {date}
        </p>
        <p
          className="ux8-condition-label"
          data-test="condition-label"
          aria-label={`Portfolio condition: ${condition.toLowerCase()}`}
        >
          {condition}
        </p>
        <h1
          className="ux8-condition-sentence"
          data-test="condition-sentence"
        >
          {sentence}
        </h1>
      </div>
    </header>
  );
}
