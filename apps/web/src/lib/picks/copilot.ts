// Picks copilot helpers — derive briefing + ranking labels + plain
// English text from honest pick data (no fake content).

import type { Pick, PickAction } from "./api";
// Phase 15h.1 — derive recommendation freshness locally from
// generated_at. Replaces the broken backend pick.stale_data flag
// per docs/ux/PHASE_15g_freshness_audit.md (the flag returned false
// on data 65+ hours old, lying to every consumer).
import { isPickStale } from "./freshness";


// ============================================================
// Briefing — top-of-page AI summary
// ============================================================

export type RiskPosture = "defensive" | "cautious" | "neutral" | "constructive";


export interface Briefing {
  posture: RiskPosture;
  postureLabel: string;
  headline: string;
  body: string;
  recommendedAction: string;
  highConfidenceTrims: number;
  highConfidenceHolds: number;
  freshestAtIso: string | null;   // most recent generated_at
  staleCount: number;
  thinDataCount: number;
}


export function buildBriefing(picks: Pick[]): Briefing {
  const counts: Record<PickAction, number> = { buy: 0, sell: 0, trim: 0, hold: 0 };
  const highConfidenceCounts: Record<PickAction, number> = { buy: 0, sell: 0, trim: 0, hold: 0 };
  let freshestIso: string | null = null;
  let staleCount = 0;
  let thinDataCount = 0;

  for (const p of picks) {
    const a = p.adjusted_action ?? p.action;
    counts[a] = (counts[a] ?? 0) + 1;
    const conf = parseFloat(p.adjusted_confidence ?? p.confidence ?? "0");
    const pct = conf > 1 ? conf : conf * 100;
    if (pct >= 70) highConfidenceCounts[a] = (highConfidenceCounts[a] ?? 0) + 1;
    if (isPickStale(p)) staleCount += 1;
    if (!p.enough_data) thinDataCount += 1;
    if (p.generated_at && (!freshestIso || p.generated_at > freshestIso)) {
      freshestIso = p.generated_at;
    }
  }

  // Derive posture
  const total = counts.buy + counts.sell + counts.trim + counts.hold;
  let posture: RiskPosture = "neutral";
  if (total === 0) {
    posture = "neutral";
  } else if (counts.sell > 0 || counts.trim >= total * 0.5) {
    posture = "defensive";
  } else if (counts.buy === 0 && (counts.trim > 0 || counts.hold >= total * 0.7)) {
    posture = "cautious";
  } else if (counts.buy >= total * 0.3) {
    posture = "constructive";
  } else {
    posture = "neutral";
  }

  const postureLabel: Record<RiskPosture, string> = {
    defensive:    "Defensive",
    cautious:     "Cautious",
    neutral:      "Neutral",
    constructive: "Constructive",
  };

  // Headline + body
  let headline: string;
  let body: string;
  let recommendedAction: string;

  // Cohesion polish — Phase A semantic freeze.
  // Headlines describe signals, thresholds, posture, and state.
  // No AI agency, intent, emotion, recommendations, or judgment.
  if (total === 0) {
    headline = "No new signals today";
    body = "The engine produced no signals in the most recent cycle. Check pipeline health or try again after the next refresh.";
    recommendedAction = "Check engine status";
  } else if (counts.buy === 0 && counts.sell === 0) {
    headline = "Defensive posture · no Buy signals";
    body = "No Buy signals passed today's threshold. The strongest signals are Trim and Hold. Review weak positions first.";
    recommendedAction = counts.trim > 0
      ? "Review highest-risk trims"
      : "Review watchlist holds";
  } else if (counts.buy > 0 && counts.sell === 0) {
    headline = `${counts.buy} Buy ${counts.buy === 1 ? "signal" : "signals"} today`;
    body = `${counts.buy} ${counts.buy === 1 ? "entry signal" : "entry signals"} matched today's filters. Review the highest-confidence row first.`;
    recommendedAction = "Review top Buy";
  } else if (counts.sell > 0 && counts.buy === 0) {
    headline = `${counts.sell} Sell ${counts.sell === 1 ? "signal" : "signals"} today`;
    body = `${counts.sell} ${counts.sell === 1 ? "name" : "names"} flagged for exit review. Address before evaluating new entries.`;
    recommendedAction = "Review Sell signals";
  } else {
    headline = `${counts.buy} Buy · ${counts.sell} Sell · ${counts.trim} Trim`;
    body = "Mixed signal day — both entry and exit signals present. Address Sell signals first, then evaluate Buy entries.";
    recommendedAction = "Address Sell signals first";
  }

  return {
    posture,
    postureLabel: postureLabel[posture],
    headline,
    body,
    recommendedAction,
    highConfidenceTrims: highConfidenceCounts.trim,
    highConfidenceHolds: highConfidenceCounts.hold,
    freshestAtIso: freshestIso,
    staleCount,
    thinDataCount,
  };
}


// ============================================================
// Ranking labels — derive small pill text for each card
// ============================================================

export function rankingLabel(pick: Pick, allPicks: Pick[]): string | null {
  const action = pick.adjusted_action ?? pick.action;
  const conf = parseFloat(pick.adjusted_confidence ?? pick.confidence ?? "0");
  const pct = conf > 1 ? conf : conf * 100;

  // Fresh signal — generated within last 2 hours
  if (pick.generated_at) {
    const hoursOld = (Date.now() - Date.parse(pick.generated_at)) / 3_600_000;
    if (hoursOld < 2) return "Fresh signal";
  }

  // Highest-risk trim/sell — lowest invalidation distance OR lowest confidence within action group
  if (action === "trim" || action === "sell") {
    const sameAction = allPicks.filter(p => (p.adjusted_action ?? p.action) === action);
    if (sameAction.length > 1) {
      const minConf = Math.min(...sameAction.map(p => {
        const c = parseFloat(p.adjusted_confidence ?? p.confidence ?? "0");
        return c > 1 ? c : c * 100;
      }));
      if (pct === minConf && pct < 60) {
        return action === "trim" ? "Highest-risk trim" : "Highest-risk sell";
      }
    }
  }

  // Strong hold — high-confidence hold signal (engine threshold met for NOT acting)
  if (action === "hold" && pct >= 70) return "Strong hold";

  // Watchlist candidate — borderline hold (45-65%)
  if (action === "hold" && pct >= 45 && pct < 65) return "Watchlist candidate";

  // Weak momentum — low confidence anything
  if (pct < 40 && pct > 0) return "Weak signal";

  // Top buy — buy with highest confidence in buy group
  if (action === "buy") {
    const buys = allPicks.filter(p => (p.adjusted_action ?? p.action) === "buy");
    if (buys.length > 1) {
      const maxBuyConf = Math.max(...buys.map(p => {
        const c = parseFloat(p.adjusted_confidence ?? p.confidence ?? "0");
        return c > 1 ? c : c * 100;
      }));
      if (pct === maxBuyConf) return "Top opportunity";
    } else {
      return "Top opportunity";
    }
  }

  return null;
}


// ============================================================
// Plain-English explanation per pick — strips raw score jargon
// ============================================================

const JARGON_PATTERNS: RegExp[] = [
  /composite\s+score\s+[\-+]?[\d.]+\s*[→\-]+\s*\w+\.?\s*/gi,
  /(trend|momentum|volatility|risk|valuation|growth|technical|fundamental)\/?\w*\s+score[: ]\s*[\-+]?[\d.]+\s*\.?/gi,
  /\bscore\s*[: ]\s*[\-+]?[\d.]+\s*\.?/gi,
  /\b[\-+]?\d+\.\d{3,}\s*\.?/g,
];


function isMostlyJargon(text: string | null): boolean {
  if (!text) return true;
  let stripped = text;
  for (const p of JARGON_PATTERNS) stripped = stripped.replace(p, "");
  return stripped.trim().length < 24;
}


export function plainExplain(pick: Pick): string {
  const action = pick.adjusted_action ?? pick.action;

  if (!isMostlyJargon(pick.thesis)) {
    let cleaned = pick.thesis ?? "";
    for (const p of JARGON_PATTERNS) cleaned = cleaned.replace(p, "");
    cleaned = cleaned.replace(/\s{2,}/g, " ").trim();
    if (cleaned.length > 24) return cleaned;
  }

  // Fall back to honest per-action template — observational, no AI agency
  switch (action) {
    case "buy":  return "Engine signal: improving momentum, entry threshold met.";
    case "sell": return "Engine signal: risk threshold breached or trend broken.";
    case "trim": return "Engine signal: momentum weakening, risk rising — exposure reduction flagged.";
    case "hold": return "Engine signal: no entry threshold met today.";
  }
}


// ============================================================
// Filters
// ============================================================

export type PicksFilter =
  | "all" | "buy" | "hold" | "trim" | "sell"
  | "high-confidence" | "freshest" | "highest-risk";


// Phase 15b3 microcopy round 2 — Opus verbatim swaps for the three
// non-action filters. "High confidence / Freshest / Highest risk" are
// engineering descriptors; the new labels are the actual rules the
// filters apply, so the user can predict what they'll see.
export const FILTER_LABELS: Record<PicksFilter, string> = {
  "all":             "All",
  "buy":             "Buy",
  "hold":            "Hold",
  "trim":            "Trim",
  "sell":            "Sell",
  "high-confidence": "≥70% confidence",
  "freshest":        "<6h old",
  "highest-risk":    "Risk-flagged",
};


// ============================================================
// Priority action — single most-important pick of the day
// ============================================================

export interface PriorityResult {
  pick: Pick;
  reason: string;          // why this matters
  ctaSecondary: string;    // "Review all trims" / "Review all sells" / null
  ctaSecondaryFilter: PicksFilter | null;
}


export function derivePriority(picks: Pick[]): PriorityResult | null {
  if (picks.length === 0) return null;

  const score = (p: Pick): number => {
    const action = p.adjusted_action ?? p.action;
    const c = parseFloat(p.adjusted_confidence ?? p.confidence ?? "0");
    const pct = c > 1 ? c : c * 100;
    // Sell > Trim > Buy > Hold (urgency)
    const actionWeight: Record<PickAction, number> = {
      sell: 100, trim: 70, buy: 60, hold: 20,
    };
    let s = (actionWeight[action] ?? 0) + pct * 0.5;
    if (isPickStale(p)) s -= 20;
    if (!p.enough_data) s -= 15;
    return s;
  };

  const sorted = [...picks].sort((a, b) => score(b) - score(a));
  const top = sorted[0];
  const action = top.adjusted_action ?? top.action;

  let reason: string;
  let ctaSecondary = "";
  let ctaSecondaryFilter: PicksFilter | null = null;

  switch (action) {
    case "sell":
      reason = "Risk threshold breached and no remaining upside flagged by the engine. Address before reviewing other signals.";
      ctaSecondary = "Review all sell signals";
      ctaSecondaryFilter = "sell";
      break;
    case "trim":
      reason = "Momentum weakened past threshold. Reducing exposure protects gains and frees capital for new setups.";
      ctaSecondary = "Review all trims";
      ctaSecondaryFilter = "trim";
      break;
    case "buy":
      reason = "Strongest entry signal of the day by composite score. Review thesis before acting.";
      ctaSecondary = "Review all buy signals";
      ctaSecondaryFilter = "buy";
      break;
    case "hold":
      reason = "No urgent action — highest-conviction watchlist row today by composite score.";
      ctaSecondary = "Review watchlist";
      ctaSecondaryFilter = "hold";
      break;
  }

  return { pick: top, reason, ctaSecondary, ctaSecondaryFilter };
}


// ============================================================
// Pick tags — small chips per card (Momentum weak, Risk rising, etc.)
// ============================================================

export interface PickTag {
  text: string;
  tone: "warn" | "info" | "good" | "danger";
}


export function pickTags(pick: Pick): PickTag[] {
  const tags: PickTag[] = [];
  const action = pick.adjusted_action ?? pick.action;
  const conf = parseFloat(pick.adjusted_confidence ?? pick.confidence ?? "0");
  const pct = conf > 1 ? conf : conf * 100;

  if (isPickStale(pick)) tags.push({ text: "Stale signal", tone: "warn" });
  if (!pick.enough_data) tags.push({ text: "Thin data", tone: "warn" });

  if (action === "trim") tags.push({ text: "Momentum weak", tone: "warn" });
  if (action === "sell") tags.push({ text: "Risk rising", tone: "danger" });
  if (action === "buy") tags.push({ text: "Setup forming", tone: "good" });
  if (action === "hold" && pct >= 70) tags.push({ text: "Strong hold", tone: "info" });
  else if (action === "hold") tags.push({ text: "Watchlist", tone: "info" });

  // Recency
  if (pick.generated_at) {
    const hoursOld = (Date.now() - Date.parse(pick.generated_at)) / 3_600_000;
    if (hoursOld < 2) tags.push({ text: "Fresh", tone: "good" });
  }

  return tags.slice(0, 3);
}


// ============================================================
// Empty-state triggers — what conditions would change the picture
// ============================================================

export function emptyStateTriggers(action: PickAction): { title: string; question: string; conditions: string[] } {
  switch (action) {
    case "buy":
      return {
        title: "No Buy signals today",
        question: "What would create a Buy?",
        conditions: [
          "Stronger upward momentum",
          "Better risk/reward setup",
          "Fresher catalyst or earnings beat",
        ],
      };
    case "sell":
      return {
        title: "No urgent Sell signals today",
        question: "What would trigger a Sell?",
        conditions: [
          "Trend breaks below key support",
          "Volatility rises sharply",
          "Downside risk outweighs upside",
        ],
      };
    case "trim":
      return {
        title: "No Trim signals",
        question: "What would suggest trimming?",
        conditions: ["Momentum weakening", "Risk metrics rising"],
      };
    case "hold":
      return {
        title: "No Hold signals",
        question: "What would suggest holding?",
        conditions: ["Mixed signals across factors", "Below conviction threshold"],
      };
  }
}


export function applyFilter(picks: Pick[], filter: PicksFilter): Pick[] {
  if (filter === "all") return picks;
  if (filter === "buy" || filter === "hold" || filter === "trim" || filter === "sell") {
    return picks.filter(p => (p.adjusted_action ?? p.action) === filter);
  }
  if (filter === "high-confidence") {
    return picks.filter(p => {
      const c = parseFloat(p.adjusted_confidence ?? p.confidence ?? "0");
      const pct = c > 1 ? c : c * 100;
      return pct >= 70;
    });
  }
  if (filter === "freshest") {
    return [...picks].sort((a, b) => {
      const ta = a.generated_at ? Date.parse(a.generated_at) : 0;
      const tb = b.generated_at ? Date.parse(b.generated_at) : 0;
      return tb - ta;
    });
  }
  if (filter === "highest-risk") {
    // Highest risk: stale, thin data, or trim/sell with low confidence
    return [...picks]
      .filter(p => {
        const a = p.adjusted_action ?? p.action;
        return isPickStale(p) || !p.enough_data || a === "sell" || a === "trim";
      })
      .sort((a, b) => {
        const score = (p: Pick) => {
          let s = 0;
          if (isPickStale(p)) s += 30;
          if (!p.enough_data) s += 20;
          const action = p.adjusted_action ?? p.action;
          if (action === "sell") s += 40;
          if (action === "trim") s += 25;
          const c = parseFloat(p.adjusted_confidence ?? p.confidence ?? "0");
          const pct = c > 1 ? c : c * 100;
          s += (100 - pct) * 0.5;
          return s;
        };
        return score(b) - score(a);
      });
  }
  return picks;
}
