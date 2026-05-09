// UX-9 Phase 9A — Hero card.
//
// Portfolio Pulse — INVARIANT shape per UX-9 R3 lock. Position
// weight bars fill staggered on first paint (300ms ease-out per
// bar, 60ms gap). Tabular-nums delta count-up over 800ms. AI
// READ paragraph fades in at ~760ms. Mini-objects fade in
// staggered at ~960ms.
//
// NO live-WebSocket dependency. ALL motion is one-shot first-
// paint reveal; after ~1500ms the card is static until next
// session. prefers-reduced-motion strips all motion.

import { useEffect, useRef, useState } from "react";

export type PositionHue =
  1 | 2 | 3 | 4 | 5 | 6 | 7 | "cash";

export interface PositionWeight {
  symbol: string;
  /** 0..1 fraction of portfolio. Sums across array should ≈ 1. */
  weight: number;
  hue: PositionHue;
}

export interface HeroMiniObject {
  label: string;
  value: string;
}

export interface HeroCardProps {
  /** today's portfolio delta as a fraction (0.008 = +0.8%) */
  todayDeltaPct: number;
  positions: PositionWeight[];
  read: string;
  miniObjects?: HeroMiniObject[];
  /** Optional click handler used by admin overlay for tooltip
   *  positioning. Ignored in normal user mode. */
  onLineageHover?: (anchor: HTMLElement) => void;
}


/** Pure CSS animation reveal — adds .is-revealed shortly after
 *  mount so the bar widths transition from 0 to target. */
function _useReveal(ref: React.RefObject<HTMLElement | null>, delayMs = 80) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const t = window.setTimeout(() => el.classList.add("is-revealed"), delayMs);
    return () => window.clearTimeout(t);
  }, [delayMs, ref]);
}


/** Tabular-nums count-up animation. Uses requestAnimationFrame
 *  for ease-out interpolation. Honors prefers-reduced-motion. */
function _useCountUp(target: number, durationMs = 800, startDelay = 300): number {
  const [value, setValue] = useState(target);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const reduced = window.matchMedia
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setValue(target);
      return;
    }
    let raf = 0;
    let startTs = 0;
    setValue(0);
    const step = (ts: number) => {
      if (!startTs) startTs = ts + startDelay;
      const elapsed = Math.max(0, ts - startTs);
      const t = Math.min(1, elapsed / durationMs);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(target * eased);
      if (t < 1) raf = window.requestAnimationFrame(step);
    };
    raf = window.requestAnimationFrame(step);
    return () => window.cancelAnimationFrame(raf);
  }, [target, durationMs, startDelay]);
  return value;
}


export default function HeroCard(p: HeroCardProps) {
  const ref = useRef<HTMLElement | null>(null);
  _useReveal(ref);
  const animatedDelta = _useCountUp(p.todayDeltaPct);

  return (
    <article
      ref={ref}
      className="ux9-hero"
      data-test="ux9-hero"
      data-source="paper_position:weight,paper_summary:daily_pnl"
      onMouseEnter={(e) => p.onLineageHover?.(e.currentTarget)}
    >
      <header className="ux9-hero-header">
        <h2 className="ux9-hero-header-label">PORTFOLIO PULSE</h2>
        <span className="ux9-hero-delta" data-test="ux9-hero-delta">
          {animatedDelta >= 0 ? "↗" : "↘"}{" "}
          {(Math.abs(animatedDelta) * 100).toFixed(1)}% today
        </span>
      </header>

      <div className="ux9-hero-bars" role="presentation">
        {p.positions.map((pos, i) => (
          <span
            key={pos.symbol}
            className="ux9-hero-bar"
            style={{
              "--bar-color": typeof pos.hue === "number"
                ? `var(--ux9-pos-${pos.hue})`
                : "var(--ux9-pos-cash)",
              "--bar-target-width": `${(pos.weight * 100).toFixed(2)}%`,
              "--bar-index": i,
            } as React.CSSProperties}
            data-symbol={pos.symbol}
            data-test="ux9-hero-bar"
            aria-label={`${pos.symbol} ${(pos.weight * 100).toFixed(0)}%`}
          />
        ))}
      </div>

      <div className="ux9-hero-bar-labels" aria-hidden="true">
        {p.positions.map((pos) => (
          <span
            key={pos.symbol}
            className="ux9-hero-bar-label"
            style={{
              "--label-target-width": `${(pos.weight * 100).toFixed(2)}%`,
            } as React.CSSProperties}
          >
            {pos.symbol}
          </span>
        ))}
      </div>

      <p className="ux9-hero-read" data-test="ux9-hero-read">
        {p.read}
      </p>

      {p.miniObjects && p.miniObjects.length > 0 && (
        <div className="ux9-hero-mini">
          {p.miniObjects.map((m) => (
            <div key={m.label} className="ux9-hero-mini-object">
              <span className="ux9-hero-mini-label">{m.label}</span>
              <span className="ux9-hero-mini-value">{m.value}</span>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}
