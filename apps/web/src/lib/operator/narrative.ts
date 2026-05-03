// Narrative helpers — transforms raw system state into readable sentences.
// Answers: what's happening, why, should operator act?

import type {
  PaperSummary, CurrentState, AnomalySummary, AnomalyEvent,
} from "./types";

export type SystemTone = "healthy" | "warning" | "degraded" | "critical";

export interface SystemNarrative {
  tone: SystemTone;
  headline: string;
  body: string;
  action: string;
  topConcern?: AnomalyEvent | null;
}

export function deriveSystemNarrative(
  summary: PaperSummary | undefined,
  state: CurrentState | undefined,
  anomalies: AnomalySummary | undefined,
): SystemNarrative {
  if (!summary || !state) {
    return {
      tone: "warning",
      headline: "System idle",
      body: "Waiting for daily pipeline to complete.",
      action: "Run make paper-daily to refresh state.",
    };
  }

  const anomCrit = anomalies?.by_severity?.critical ?? 0;
  const anomWarn = anomalies?.by_severity?.warning ?? 0;
  const top = anomalies?.top3?.[0] ?? null;

  // Critical path
  if (anomCrit > 0 || summary.pipeline_status === "failed") {
    return {
      tone: "critical",
      headline: "System degraded — review required",
      body: top
        ? `${top.title}. ${top.description}`
        : "Pipeline failed. Inspect error log.",
      action: "Pause new entries. Diagnose before next run.",
      topConcern: top,
    };
  }

  // Warning path
  if (anomWarn > 0 || summary.pipeline_status === "partial") {
    const tone: SystemTone = "warning";
    const headline = top
      ? `Warning: ${top.title}`
      : "Pipeline partial — non-critical issues";
    const body = top?.description ??
      "Some data sources unavailable. Production behavior unaffected.";
    return {
      tone,
      headline,
      body,
      action: "Review anomalies panel. No pause required.",
      topConcern: top,
    };
  }

  // Healthy — narrate current regime + decision
  const regime = state.stress_regime ? "Stress regime"
    : state.directional_regime ? "Directional regime"
    : "Neutral";
  const engine = state.engine === "A" ? "Engine A (mean reversion)"
    : state.engine === "B" ? "Engine B (credit + rates)"
    : "no active engine";
  const firedSentence = state.fire
    ? `Fired ${engine} — long ${summary.open_positions_count} position${
        summary.open_positions_count === 1 ? "" : "s"
      }.`
    : `${engine} standing by — ${extractBlockingCondition(state.reason)}.`;

  return {
    tone: "healthy",
    headline: `${regime} · ${engine === "no active engine" ? "idle" : engine}`,
    body: firedSentence,
    action: state.fire
      ? "Monitor open position. System will close at target exit."
      : "No action required. System will re-evaluate tomorrow.",
  };
}

function extractBlockingCondition(reason: string): string {
  // Parse reason like: "directional_regime=True credit_stable=False rates_calm=False"
  const negatives: string[] = [];
  const m = reason.match(/(\w+)=False/g) ?? [];
  for (const token of m) {
    const key = token.split("=")[0];
    if (key === "fire" || key === "stress_regime" || key === "directional_regime")
      continue;
    negatives.push(humanize(key));
  }
  if (negatives.length === 0) return "conditions not met";
  if (negatives.length === 1) return `${negatives[0]} blocking entry`;
  return `${negatives.slice(0, -1).join(", ")} and ${negatives.at(-1)} blocking entry`;
}

function humanize(key: string): string {
  return key.replace(/_/g, " ");
}
