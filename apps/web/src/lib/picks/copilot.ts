// Picks copilot helpers — derive briefing + ranking labels + plain
// English text from honest pick data (no fake content).

import type { Pick, PickAction } from "./api";


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
    if (p.stale_data) staleCount += 1;
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

  if (total === 0) {
    headline = "AI engine has no fresh suggestions";
    body = "The recommendation engine has not produced any results recently. Check engine health or try again shortly.";
    recommendedAction = "Check engine status";
  } else if (counts.buy === 0 && counts.sell === 0) {
    headline = "AI is cautious today";
    body = "No fresh Buy signals passed the engine's threshold. The strongest signals are Trim and Hold — protect gains, reduce weak positions, and wait for cleaner entries.";
    recommendedAction = counts.trim > 0
      ? "Review highest-risk trims"
      : "Review watchlist holds";
  } else if (counts.buy > 0 && counts.sell === 0) {
    headline = `${counts.buy} Buy ${counts.buy === 1 ? "idea" : "ideas"} today`;
    body = `AI sees ${counts.buy === 1 ? "an entry opportunity" : "entry opportunities"} with favorable risk/reward. Review the highest-confidence pick first.`;
    recommendedAction = "Review top Buy";
  } else if (counts.sell > 0 && counts.buy === 0) {
    headline = `${counts.sell} Sell ${counts.sell === 1 ? "signal" : "signals"} today`;
    body = "AI sees risk increasing on these names. Consider exiting before further deterioration.";
    recommendedAction = "Review Sell signals";
  } else {
    headline = `${counts.buy} Buy · ${counts.sell} Sell · ${counts.trim} Trim`;
    body = "Mixed market — AI sees both entry and exit signals. Address Sell signals first, then evaluate Buy opportunities.";
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

  // Strong hold — high-confidence hold (the AI is confident about NOT acting)
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

  // Fall back to honest per-action template
  switch (action) {
    case "buy":  return "AI sees improving momentum and favorable risk/reward.";
    case "sell": return "Risk is too high or trend is broken. AI suggests avoiding or exiting.";
    case "trim": return "Momentum is weak and risk is rising. AI suggests reducing exposure instead of adding more.";
    case "hold": return "Not attractive enough to buy today. Keep watching for a better entry.";
  }
}


// ============================================================
// Filters
// ============================================================

export type PicksFilter =
  | "all" | "buy" | "hold" | "trim" | "sell"
  | "high-confidence" | "freshest" | "highest-risk";


export const FILTER_LABELS: Record<PicksFilter, string> = {
  "all":             "All",
  "buy":             "Buy",
  "hold":            "Hold",
  "trim":            "Trim",
  "sell":            "Sell",
  "high-confidence": "High confidence",
  "freshest":        "Freshest",
  "highest-risk":    "Highest risk",
};


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
        return p.stale_data || !p.enough_data || a === "sell" || a === "trim";
      })
      .sort((a, b) => {
        const score = (p: Pick) => {
          let s = 0;
          if (p.stale_data) s += 30;
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
