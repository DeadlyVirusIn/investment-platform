// UX-3D Phase A — engine state → copilot prose.
//
// Pure functions. No I/O. No fetch. No randomness. No LLM. Every
// output is determined entirely by the input, and every output
// carries a `dataSource` string naming which engine fields it
// composes (audit trail).
//
// The CI lint rejects any synthesised sentence rendered without a
// `data-source` attribute; this file is the only legitimate place
// to mint those strings.

import { CONFIDENCE_LABELS, HERO_TEMPLATES } from "./copy";
import type {
  ConfidenceBand,
  HeroCopy,
  HeroPattern,
} from "./types";


// ---------------------------------------------------------------------
// 1. Confidence: numeric → 3-band
// ---------------------------------------------------------------------

/** Maps a 0-1 confidence score to a 3-band label.
 *  Boundaries: [0, 0.5) → lower; [0.5, 0.75) → medium; [0.75, 1] → higher.
 *  null / undefined / NaN → "lower" (most-conservative default). */
export function deriveConfidenceBand(
  score: number | null | undefined,
): ConfidenceBand {
  if (score === null || score === undefined) return "lower";
  const n = Number(score);
  if (!Number.isFinite(n)) return "lower";
  if (n >= 0.75) return "higher";
  if (n >= 0.5) return "medium";
  return "lower";
}


export function describeConfidence(
  score: number | null | undefined,
): { band: ConfidenceBand; short: string; long: string } {
  const band = deriveConfidenceBand(score);
  return {
    band,
    short: CONFIDENCE_LABELS[band].short,
    long: CONFIDENCE_LABELS[band].long,
  };
}


// ---------------------------------------------------------------------
// 2. Hero pattern selection
// ---------------------------------------------------------------------

export interface HeroEngineState {
  /** True only when the daily run has never produced a snapshot yet. */
  firstSession?: boolean;
  /** Count of items at "critical" severity in anomalies today. */
  criticalAnomalies?: number;
  /** True if pipeline_status is "failed" today. */
  pipelineFailed?: boolean;
  /** Current open paper-trade count. */
  openPositions?: number;
  /** New signals first observed in the last 24h. */
  newSignals24h?: number;
  /** Volatility delta vs the prior session, fraction (e.g. -0.18). */
  volatilityDelta?: number;
  /** True if regime.stress_regime is currently set. */
  stressRegime?: boolean;
  /** Yesterday's close-to-close session return, fraction. */
  prevSessionReturn?: number;
  /** Current drawdown from peak, fraction (e.g. -0.07). */
  drawdownFromPeak?: number;
  /** YYYY-MM-DD; used to pick a quiet-state cadence variant so a
   *  returning user sees a slightly different sentence each day. */
  asOfDate?: string;
}


/** Choose the hero pattern by walking the priority rules in order.
 *  First match wins. NEVER returns null — falls through to
 *  "first_session" when no engine state is loaded. */
export function selectHeroPattern(state: HeroEngineState): {
  pattern: HeroPattern;
  vars: Record<string, string | number>;
  dataSource: string;
} {
  if (state.firstSession || Object.keys(state).length === 0) {
    return { pattern: "first_session", vars: {}, dataSource: "first_session" };
  }
  if ((state.criticalAnomalies ?? 0) > 0 || state.pipelineFailed) {
    return {
      pattern: "needs_attention",
      vars: {},
      dataSource: "anomaly:critical,pipeline:status",
    };
  }
  // Drawdown precedes volatility; both override quieter branches.
  if ((state.drawdownFromPeak ?? 0) <= -0.05) {
    const pct = Math.round(Math.abs(state.drawdownFromPeak ?? 0) * 100);
    return {
      pattern: "drawdown_from_peak",
      vars: { pct },
      dataSource: "summary:max_drawdown_pct",
    };
  }
  // "Calmer after selloff" — yesterday was meaningfully down AND
  // today's vol is easing.
  if (
    (state.prevSessionReturn ?? 0) <= -0.015
    && (state.volatilityDelta ?? 0) <= 0
  ) {
    return {
      pattern: "calmer_after_selloff",
      vars: {},
      dataSource: "summary:prev_session_return,regime:volatility_delta",
    };
  }
  // Volatility elevated today.
  if (state.stressRegime) {
    return {
      pattern: "volatility_elevated",
      vars: {},
      dataSource: "regime:stress_regime",
    };
  }
  // Markets softened + new setups appeared.
  if (
    (state.volatilityDelta ?? 0) <= -0.10
    && (state.newSignals24h ?? 0) >= 1
  ) {
    return {
      pattern: "softened_with_new_setups",
      vars: { newCount: state.newSignals24h ?? 0 },
      dataSource: "regime:volatility_delta,signal:new_count_24h",
    };
  }
  // Holding open positions, nothing new today.
  if ((state.openPositions ?? 0) > 0 && (state.newSignals24h ?? 0) === 0) {
    return {
      pattern: "carrying_open_only",
      vars: { openCount: state.openPositions ?? 0 },
      dataSource: "paper_position:open_count,signal:new_count_24h",
    };
  }
  // Default — quiet session. Cadence-vary by date.
  return {
    pattern: "quiet_session",
    vars: { variantIndex: variantIndexFromDate(state.asOfDate) },
    dataSource: "regime:quiet,signal:new_count_24h",
  };
}


/** Deterministic 0..3 index from an as_of_date so the quiet hero
 *  varies subtly day-to-day without ever feeling random. Stable
 *  given the same date. */
export function variantIndexFromDate(date?: string): number {
  if (!date) return 0;
  // Use the day-of-month modulo the variant count. Stable per date.
  const day = Number(date.slice(8, 10));
  if (!Number.isFinite(day)) return 0;
  return day % 4;
}


// ---------------------------------------------------------------------
// 3. Compose the full HeroCopy envelope
// ---------------------------------------------------------------------

export function deriveHero(state: HeroEngineState): HeroCopy {
  const { pattern, vars, dataSource } = selectHeroPattern(state);
  const tmpl = HERO_TEMPLATES[pattern];
  const sentence = tmpl.render(vars);
  // Defensive: enforce hero-length contract at the boundary so a
  // misuse here surfaces in dev rather than at runtime in prod.
  if (sentence.length > 100) {
    // Truncate would break truth; prefer to fall back to a known-safe
    // pattern so the page never renders an over-long hero.
    return {
      sentence: HERO_TEMPLATES.quiet_session.render({ variantIndex: 0 }),
      tone: "calm",
      pacing: "calm",
      dataSource: "fallback:hero_length_guard",
    };
  }
  return {
    sentence,
    tone: tmpl.tone,
    pacing: tmpl.pacing,
    dataSource,
  };
}
