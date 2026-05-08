// UX-5B Phase B-1 — Today (Overview) deterministic composers.
//
// Pure functions. No I/O, no fetch, no LLM, no randomness. Each
// composer takes engine state + a local date and returns either
// the composed string(s) for its block or `null` (block absent).
//
// Rules baked in:
//   * R-A — block 3 (ideas) renders observational templates only;
//     this file rejects any score / confidence / conviction input.
//   * R-B — quiet-day output is first-class, not a fallback.
//   * R-C — block 4 (what changed) caps at 3 sentences each ≤ 80 chars.
//   * R-D — block 6 (watch) translates event codes via the locked
//     map; unknown codes omit silently.
//   * R-E — empty blocks return `null`. NEVER placeholder strings.
//   * R-G — greeting + today-line + quiet-day rotate by local
//     date. Idea observations + what-changed deltas do NOT rotate.
//   * R-H — fresh ideas use "Today"; held positions use "Day N"
//     (the latter lives in the existing derivePositionTemporal,
//     not duplicated here).
//
// Banned in this file (UX-5 §3): signal, batch, regime (as a
// rendered word), gate, anomaly, pipeline, ingest, replay, fill,
// guard, scheduler, cron, snapshot, advisory, engine, pending,
// cycle, runner, stage, module, as_of, submitted_at, Day 0.
// The lint script (Phase B-4) enforces.

import {
  GREETINGS,
  HOLDINGS_SUMMARY,
  IDEA_OBSERVATIONS,
  PIPELINE_CATCHING_UP_LINE,
  QUIET_DAY_VARIANTS,
  RISK_LINE,
  SYSTEM_REVIEWED_LINE,
  TODAYS_IDEAS,
  TODAY_LINE_BY_REGIME,
  WATCH_TRANSLATIONS,
  WHAT_CHANGED,
} from "./overview_copy";


// ---------------------------------------------------------------------
// 0. Local-date variant helper (R-G)
// ---------------------------------------------------------------------

/** Day-of-month modulo `n`. Stable per local date. Returns 0 for
 *  malformed dates so callers always receive a usable index. */
export function variantIndexFromYMD(ymd: string, n: number): number {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(ymd)) return 0;
  if (n <= 0) return 0;
  const day = Number(ymd.slice(8, 10));
  if (!Number.isFinite(day)) return 0;
  return day % n;
}


// ---------------------------------------------------------------------
// 1. Block 1 — greeting + today line
// ---------------------------------------------------------------------

export type GreetingSlot = "morning" | "afternoon" | "evening";


/** Pick the time-of-day greeting slot from a local hour 0..23. */
export function greetingSlotFromHour(hour: number): GreetingSlot {
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
}


export interface TodayLineInput {
  /** Local YMD (e.g. "2026-05-08"). Used for cadence rotation. */
  todayYMD: string;
  /** Local hour 0..23. Used for greeting slot selection. */
  localHour: number;
  /** "calm" | "trending" | "choppy" | "stress" — or anything
   *  unknown to omit the regime second sentence entirely. */
  regimeLabel?: string | null;
  /** True when the daily loop's most recent run failed. */
  pipelineFailed?: boolean;
}


export interface TodayLineOutput {
  greeting: string;
  /** First sentence — always present unless pipeline failed. */
  systemReviewed: string | null;
  /** Second sentence — regime-derived calm phrase, may be null
   *  if regime is unknown. */
  marketLine: string | null;
  /** When pipeline is failed, this string replaces the entire
   *  body (system + market line both omitted). */
  catchingUp: string | null;
  /** Audit-trail provenance for the surface. */
  dataSource: string;
}


export function deriveTodayLine(inp: TodayLineInput): TodayLineOutput {
  const slot = greetingSlotFromHour(inp.localHour);
  const greetingVariants = GREETINGS[slot];
  const gIdx = variantIndexFromYMD(inp.todayYMD, greetingVariants.length);
  const greeting = greetingVariants[gIdx];

  if (inp.pipelineFailed) {
    return {
      greeting,
      systemReviewed: null,
      marketLine: null,
      catchingUp: PIPELINE_CATCHING_UP_LINE,
      dataSource: "pipeline:status",
    };
  }

  const regime = (inp.regimeLabel ?? "").toLowerCase();
  const variants = regime in TODAY_LINE_BY_REGIME
    ? TODAY_LINE_BY_REGIME[regime]
    : null;
  const marketLine = variants
    ? variants[variantIndexFromYMD(inp.todayYMD, variants.length)]
    : null;

  return {
    greeting,
    systemReviewed: SYSTEM_REVIEWED_LINE,
    marketLine,
    catchingUp: null,
    dataSource: regime
      ? `regime:label,pipeline:status,as_of:${inp.todayYMD}`
      : `pipeline:status,as_of:${inp.todayYMD}`,
  };
}


// ---------------------------------------------------------------------
// 2. Block 2 — holdings summary
// ---------------------------------------------------------------------

export interface HoldingsSummaryInput {
  openCount: number;
  /** Optional state tags computed upstream (count of positions
   *  approaching their target / needing attention). Until pricing
   *  is wired these may be null; the derive omits the state-clause
   *  rather than guess. */
  approachingTargetCount?: number | null;
  needsAttentionCount?: number | null;
}


export interface HoldingsSummaryOutput {
  /** Composed sentence for the block, or null when no positions
   *  open (the block then renders the "noneOpen" line). */
  countSentence: string;
  /** Optional state-clause; null when no truthful clause derives. */
  stateClause: string | null;
  /** Always include the link copy + target. */
  linkText: string;
  linkHref: string;
  dataSource: string;
}


export function deriveHoldingsSummary(
  inp: HoldingsSummaryInput,
): HoldingsSummaryOutput {
  const n = Math.max(0, Math.floor(inp.openCount));
  if (n === 0) {
    return {
      countSentence: HOLDINGS_SUMMARY.noneOpen,
      stateClause: null,
      linkText: HOLDINGS_SUMMARY.link,
      linkHref: "/portfolio?view=brief",
      dataSource: "paper_position:open_count",
    };
  }

  const noun = n === 1
    ? HOLDINGS_SUMMARY.positionNounSingular
    : HOLDINGS_SUMMARY.positionNounPlural;

  const approaching = inp.approachingTargetCount ?? null;
  const needs = inp.needsAttentionCount ?? null;

  let stateClause: string | null = null;
  // Mark-dependent clauses; only render when truthful counts exist.
  // R-E forbids placeholder text so we leave the clause null when
  // the upstream data is null (mark price not yet wired).
  if (approaching !== null && needs !== null) {
    if (needs > 0) {
      stateClause = HOLDINGS_SUMMARY.stateClauses.oneNeedsAttention;
    } else if (approaching === 0) {
      stateClause = HOLDINGS_SUMMARY.stateClauses.allStable;
    } else if (approaching === n) {
      stateClause = HOLDINGS_SUMMARY.stateClauses.allApproaching;
    } else if (approaching === 1) {
      stateClause = HOLDINGS_SUMMARY.stateClauses.oneApproachingTarget;
    } else {
      stateClause = HOLDINGS_SUMMARY.stateClauses.allStable;
    }
  }

  return {
    countSentence: `${n} ${noun}.`,
    stateClause,
    linkText: HOLDINGS_SUMMARY.link,
    linkHref: "/portfolio?view=brief",
    dataSource:
      "paper_position:open_count,paper_position:approaching_target,"
      + "paper_position:needs_attention",
  };
}


// ---------------------------------------------------------------------
// 3. Block 3 — today's ideas (R-A: observational only)
// ---------------------------------------------------------------------

/** Inputs for the per-idea observation classifier. ALL fields
 *  optional — the classifier picks the first matching template
 *  and falls back to the generic observation when nothing
 *  matches. NEVER takes a score, confidence, or conviction
 *  field — UX-5B forbids those reaching this surface. */
export interface IdeaInput {
  symbol: string;
  /** Sector label if known. Used for sector observations. */
  sector?: string | null;
  /** True when the candidate sits inside its strategy's entry
   *  band today. Truth comes from the existing
   *  candidate_idea / strategy template. */
  entryZoneReached?: boolean;
  /** True when the day's low touched a relevant moving average
   *  and closed above it. */
  pullbackHeld?: boolean;
  /** When the candidate is consolidating near a moving average,
   *  the window length (e.g. 20, 50, 200). */
  baseAverageWindow?: number | null;
  /** Days until next earnings event (≤ 5 → "this week"). */
  earningsDaysAway?: number | null;
  /** True when the symbol moved ≥ 2% today (chart-context only,
   *  no score implied). */
  recentlyMoved?: boolean;
  /** True when the sector showed strength relative to broad
   *  market today (chart-context only). */
  sectorStrengthening?: boolean;
  /** True when the sector held flat while the market fell. */
  sectorStable?: boolean;
}


export interface IdeaCardOutput {
  symbol: string;
  /** Locked temporal cue per R-H — fresh ideas always show
   *  "Today", never "Day 0". */
  temporal: string;
  observation: string;
  dataSource: string;
}


/** Pick ONE observational template per idea. Order = preference
 *  (first match wins). Banned upstream: scores, confidence,
 *  conviction. The lint enforces; this file refuses to consume
 *  such fields by simply not having parameters for them. */
export function deriveIdeaCard(inp: IdeaInput): IdeaCardOutput {
  // Widen to string — IDEA_OBSERVATIONS uses `as const` so the
  // literal types would otherwise prevent reassignment.
  let observation: string = IDEA_OBSERVATIONS.generic;
  let dataSource: string = "candidate_idea:symbol";

  // Order matters — sector strength is the most specific
  // cross-asset observation, then position-specific clues.
  if (inp.sectorStrengthening && inp.sector) {
    observation = IDEA_OBSERVATIONS.sectorStrengthening
      .replace("{sector}", inp.sector);
    dataSource = "candidate_idea:sector,market:sector_strength";
  } else if (inp.sectorStable && inp.sector) {
    observation = IDEA_OBSERVATIONS.sectorStable
      .replace("{sector}", inp.sector);
    dataSource = "candidate_idea:sector,market:sector_strength";
  } else if (inp.entryZoneReached) {
    observation = IDEA_OBSERVATIONS.entryZoneReached;
    dataSource = "candidate_idea:entry_band";
  } else if (inp.pullbackHeld) {
    observation = IDEA_OBSERVATIONS.pullbackHeld;
    dataSource = "candidate_idea:pullback_signal";
  } else if (
    inp.baseAverageWindow !== null
    && inp.baseAverageWindow !== undefined
    && inp.baseAverageWindow > 0
  ) {
    observation = IDEA_OBSERVATIONS.baseBuilding
      .replace("{window}", String(inp.baseAverageWindow));
    dataSource = "candidate_idea:base_window";
  } else if (
    inp.earningsDaysAway !== null
    && inp.earningsDaysAway !== undefined
    && inp.earningsDaysAway >= 0
    && inp.earningsDaysAway <= 5
  ) {
    observation = IDEA_OBSERVATIONS.earningsApproaching;
    dataSource = "candidate_idea:earnings_day";
  } else if (inp.recentlyMoved) {
    observation = IDEA_OBSERVATIONS.recentlyMoved;
    dataSource = "candidate_idea:price_change_24h";
  }

  return {
    symbol: inp.symbol,
    temporal: TODAYS_IDEAS.freshTemporalCue,  // "Today"
    observation,
    dataSource,
  };
}


export interface TodaysIdeasInput {
  ideas: ReadonlyArray<IdeaInput>;
}


export interface TodaysIdeasOutput {
  cards: ReadonlyArray<IdeaCardOutput>;
  /** Always at most 3 — R-F caps the block. */
  truncatedFrom?: number;
}


/** Compose the Today's Ideas block. Returns null when no ideas
 *  available (R-E — block absent, NEVER renders header alone). */
export function deriveTodaysIdeas(
  inp: TodaysIdeasInput,
): TodaysIdeasOutput | null {
  if (!inp.ideas || inp.ideas.length === 0) return null;
  const original = inp.ideas.length;
  const limited = inp.ideas.slice(0, 3);
  return {
    cards: limited.map(deriveIdeaCard),
    truncatedFrom: original > 3 ? original : undefined,
  };
}


// ---------------------------------------------------------------------
// 4. Block 4 — what changed (R-C: tiny, ≤ 3 sentences)
// ---------------------------------------------------------------------

export interface WhatChangedInput {
  /** Number of new ideas first observed in the last 24h. */
  newIdeas24h?: number;
  /** Count of open positions whose state changed to
   *  "approaching target" today. */
  positionsApproachingTarget?: number;
  /** Count of positions closed today. */
  positionsClosedToday?: number;
  /** Calm-phrasing regime label that yesterday surfaced. Pair
   *  with `regimeNow` to produce the "shifted from X to Y"
   *  sentence. Both must be present for the line to render. */
  regimePrev?: string | null;
  regimeNow?: string | null;
}


export interface WhatChangedOutput {
  /** ≤ 3 sentences. Each ≤ 80 chars (verified by composition). */
  sentences: ReadonlyArray<string>;
  /** Audit-trail provenance. */
  dataSource: string;
  /** True when the block fell back to the quiet-change line.
   *  Used downstream to suppress the line if the user has
   *  already seen it once today. */
  isQuietFallback: boolean;
}


function _calmRegimePhrase(label: string | null | undefined): string | null {
  if (!label) return null;
  const k = label.toLowerCase();
  if (k === "calm") return "calm";
  if (k === "trending") return "directional";
  if (k === "choppy") return "uneven";
  if (k === "stress") return "unsettled";
  return null;
}


/** Compose the What Changed block. Returns null when nothing
 *  truthful (and quiet fallback already shown today, supplied by
 *  caller via the `suppressQuietFallback` flag). */
export function deriveWhatChanged(
  inp: WhatChangedInput,
  suppressQuietFallback = false,
): WhatChangedOutput | null {
  const sentences: string[] = [];
  const sources: string[] = [];

  const newCount = inp.newIdeas24h ?? 0;
  if (newCount === 1) {
    sentences.push(WHAT_CHANGED.newIdeasSingular);
    sources.push("candidate_idea:new_count_24h");
  } else if (newCount > 1) {
    sentences.push(
      WHAT_CHANGED.newIdeasPlural.replace("{n}", String(newCount)),
    );
    sources.push("candidate_idea:new_count_24h");
  }

  const approaching = inp.positionsApproachingTarget ?? 0;
  if (approaching === 1 && sentences.length < 3) {
    sentences.push(WHAT_CHANGED.positionApproachingTarget);
    sources.push("paper_position:approaching_target");
  } else if (approaching > 1 && sentences.length < 3) {
    sentences.push(
      WHAT_CHANGED.positionsApproachingTarget.replace(
        "{n}", String(approaching),
      ),
    );
    sources.push("paper_position:approaching_target");
  }

  const closed = inp.positionsClosedToday ?? 0;
  if (closed === 1 && sentences.length < 3) {
    sentences.push(WHAT_CHANGED.positionClosedSingular);
    sources.push("paper_trade:closed_today");
  } else if (closed > 1 && sentences.length < 3) {
    sentences.push(
      WHAT_CHANGED.positionsClosedPlural.replace("{n}", String(closed)),
    );
    sources.push("paper_trade:closed_today");
  }

  const prev = _calmRegimePhrase(inp.regimePrev);
  const now = _calmRegimePhrase(inp.regimeNow);
  if (prev && now && prev !== now && sentences.length < 3) {
    sentences.push(
      WHAT_CHANGED.regimeShifted
        .replace("{prev}", prev)
        .replace("{now}", now),
    );
    sources.push("regime:label_prev,regime:label_now");
  }

  if (sentences.length === 0) {
    if (suppressQuietFallback) return null;
    return {
      sentences: [WHAT_CHANGED.quietChangeFallback],
      dataSource: "what_changed:quiet_fallback",
      isQuietFallback: true,
    };
  }

  // R-C — guard each sentence's length at 80 chars. None of the
  // templates above exceed; this is a defensive check so future
  // additions can't silently regress.
  for (const s of sentences) {
    if (s.length > 80) {
      // Truncating would break truth; instead drop this sentence.
      // (Should never happen with the current templates.)
      const idx = sentences.indexOf(s);
      sentences.splice(idx, 1);
    }
  }

  return {
    sentences,
    dataSource: sources.join(",") || "what_changed:none",
    isQuietFallback: false,
  };
}


// ---------------------------------------------------------------------
// 5. Block 5 — risk line (conditional)
// ---------------------------------------------------------------------

export interface RiskLineInput {
  /** Drawdown from peak as a fraction (e.g. -0.07 = 7% below). */
  drawdownFromPeak?: number;
  /** True when stress regime is currently set. */
  stressRegime?: boolean;
  /** Count of strategies that paused themselves today. */
  pausedStrategiesToday?: number;
}


export interface RiskLineOutput {
  /** ≤ 2 sentences. */
  sentences: ReadonlyArray<string>;
  dataSource: string;
}


/** Compose the conditional risk block. Returns null when no
 *  trigger matches — block absent (R-E + Strategic lock A). */
export function deriveRiskLine(inp: RiskLineInput): RiskLineOutput | null {
  const sentences: string[] = [];
  const sources: string[] = [];

  const dd = inp.drawdownFromPeak;
  if (typeof dd === "number" && Number.isFinite(dd) && dd <= -0.05) {
    const pct = Math.round(Math.abs(dd) * 100);
    sentences.push(RISK_LINE.drawdownPercent.replace("{pct}", String(pct)));
    sources.push("summary:max_drawdown_pct");
  }

  if (inp.stressRegime && sentences.length < 2) {
    sentences.push(RISK_LINE.stressContext);
    sources.push("regime:stress");
  }

  const paused = inp.pausedStrategiesToday ?? 0;
  if (paused === 1 && sentences.length < 2) {
    sentences.push(RISK_LINE.pausedSingular);
    sources.push("strategy:paused_count");
  } else if (paused > 1 && sentences.length < 2) {
    sentences.push(
      RISK_LINE.pausedPlural.replace("{n}", String(paused)),
    );
    sources.push("strategy:paused_count");
  }

  if (sentences.length === 0) return null;
  return {
    sentences,
    dataSource: sources.join(","),
  };
}


// ---------------------------------------------------------------------
// 6. Block 6 — watch this week (R-D: events → watchfulness)
// ---------------------------------------------------------------------

export interface WatchEventInput {
  /** Event code from the catalyst calendar. Anything not in
   *  WATCH_TRANSLATIONS omits silently. */
  code: string;
  /** Day-of-week label as already-rendered string ("Wed",
   *  "Thursday"). Caller localises; this composer never
   *  formats dates itself. */
  day: string;
  /** Optional symbol — required only for EARNINGS code. */
  symbol?: string | null;
}


export interface WatchOutput {
  lines: ReadonlyArray<string>;
  dataSource: string;
}


/** Compose the watch block. Returns null when nothing
 *  translatable (R-E). */
export function deriveWatch(
  events: ReadonlyArray<WatchEventInput>,
): WatchOutput | null {
  if (!events || events.length === 0) return null;
  const lines: string[] = [];
  const seenCodes = new Set<string>();

  for (const ev of events) {
    if (lines.length >= 3) break;
    const code = (ev.code ?? "").toUpperCase();
    const template = WATCH_TRANSLATIONS[code];
    if (!template) continue;
    if (code === "EARNINGS") {
      if (!ev.symbol) continue;
      lines.push(
        template
          .replace("{symbol}", ev.symbol)
          .replace("{day}", ev.day),
      );
    } else {
      // Macro events: dedupe by code so two CPI fixtures don't
      // both render.
      if (seenCodes.has(code)) continue;
      seenCodes.add(code);
      lines.push(template.replace("{day}", ev.day));
    }
  }

  if (lines.length === 0) return null;
  return {
    lines,
    dataSource: "catalyst_calendar:upcoming",
  };
}


// ---------------------------------------------------------------------
// 7. Quiet-day rendering (R-B — first-class)
// ---------------------------------------------------------------------

export interface QuietDayOutput {
  greeting: string;
  body: string;
  dataSource: string;
}


/** Render the quiet-day full-page collapse. Used when EVERY
 *  other block returned null (no positions, no ideas, no
 *  changes, no risks, no events). */
export function deriveQuietDay(inp: TodayLineInput): QuietDayOutput {
  const slot = greetingSlotFromHour(inp.localHour);
  const greetingVariants = GREETINGS[slot];
  const gIdx = variantIndexFromYMD(inp.todayYMD, greetingVariants.length);
  const greeting = greetingVariants[gIdx];

  const bIdx = variantIndexFromYMD(inp.todayYMD, QUIET_DAY_VARIANTS.length);
  const body = QUIET_DAY_VARIANTS[bIdx];

  return {
    greeting,
    body,
    dataSource: "quiet_day:variant_by_date",
  };
}
