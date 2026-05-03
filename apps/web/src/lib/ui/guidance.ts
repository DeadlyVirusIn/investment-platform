// Phase SYSTEM-UI-BEGINNER — plain-English explanations.
// Deterministic. No external API calls. Text kept terminal-terse.

import type { CurrentState, PaperSummary } from "@/lib/operator/types";

export interface Guidance {
  plain: string;
  goodBad: "good" | "bad" | "neutral" | "warning";
  why: string;
  userAction: string;
}

export const TOOLTIPS: Record<string, string> = {
  regime: "The current market environment.",
  gates: "Safety checks that must pass before a strategy can act.",
  engine: "A trading strategy module. None armed = system waiting.",
  risk: "Current warning level (market + data + portfolio).",
  catalyst: "News or events that may affect a stock (e.g. earnings).",
  confidence: "How strongly the system trusts this decision.",
  drawdown: "Drop from peak NAV. Lower = worse.",
  paper: "Simulated trading. No real money changes hands.",
  armed: "Ready to trigger a trade when conditions align.",
  standing_by: "System is waiting for better conditions.",
};


// ---------------------------------------------------------------------------
// Regime
// ---------------------------------------------------------------------------

export function guideRegime(state: CurrentState | undefined): Guidance {
  if (!state) return {
    plain: "Regime data not yet available.",
    goodBad: "neutral",
    why: "Pipeline hasn't produced today's snapshot.",
    userAction: "Wait for first nightly run.",
  };
  if (state.stress_regime) return {
    plain: "Market is in stress — elevated volatility, unfavorable for new entries.",
    goodBad: "bad",
    why: "Stress regime detected from volatility + market structure signals.",
    userAction: "Review only. No new trades recommended.",
  };
  if (state.directional_regime) return {
    plain: "Market is trending, but the system is waiting for stronger confirmation before opening trades.",
    goodBad: "good",
    why: "Directional regime means sustained trend, but entry still requires all safety gates.",
    userAction: "Monitor. Wait for gates to align.",
  };
  return {
    plain: "Market is in a neutral state — no clear trend signal.",
    goodBad: "neutral",
    why: "Neither stress nor directional regime flags are active.",
    userAction: "Wait. The system will re-evaluate on next session.",
  };
}


// ---------------------------------------------------------------------------
// Gates
// ---------------------------------------------------------------------------

export interface GateStatus {
  key: string;
  label: string;
  pass: boolean | null;     // null = unknown
  why: string;
}

const GATE_DEFS: Array<{ key: string; label: string; why: string }> = [
  { key: "rates_calm",
    label: "Rates environment",
    why: "10y yield not jumping — interest-rate shocks avoided." },
  { key: "vrp_supportive",
    label: "Volatility premium",
    why: "Implied vs realized volatility spread is constructive." },
  { key: "credit_stable",
    label: "Credit spreads",
    why: "High-yield credit showing no stress." },
  { key: "liquidity_expanding",
    label: "Market liquidity",
    why: "Bank reserves / liquidity proxies rising." },
];

export function describeGates(state: CurrentState | undefined): {
  gates: GateStatus[];
  passing: number;
  failing: number;
  total: number;
} {
  if (!state) {
    return {
      gates: GATE_DEFS.map(g => ({
        key: g.key, label: g.label, pass: null, why: g.why,
      })),
      passing: 0, failing: 0, total: GATE_DEFS.length,
    };
  }
  const ctx = state.context_values || {};
  const gates = GATE_DEFS.map(g => ({
    key: g.key, label: g.label,
    pass: typeof (ctx as any)[g.key] === "boolean"
      ? (ctx as any)[g.key] as boolean : null,
    why: g.why,
  }));
  const passing = gates.filter(g => g.pass === true).length;
  const failing = gates.filter(g => g.pass === false).length;
  return { gates, passing, failing, total: GATE_DEFS.length };
}

export function guideGates(state: CurrentState | undefined): Guidance {
  const { passing, failing, total } = describeGates(state);
  if (passing >= 3) return {
    plain: `${passing} of ${total} required safety checks are passing. System has clear signal to act.`,
    goodBad: "good",
    why: "Strategies require at least most gates green to reduce false-positive entries.",
    userAction: "Monitor for engine firing.",
  };
  if (passing >= 2) return {
    plain: `Only ${passing} of ${total} required safety checks are passing. System needs more confirmation before trading.`,
    goodBad: "warning",
    why: `${failing} gate(s) failing, meaning one or more macro conditions aren't safe yet.`,
    userAction: "Wait. System protects itself by holding off.",
  };
  return {
    plain: `Only ${passing} of ${total} safety checks pass. System is defensive.`,
    goodBad: "bad",
    why: "Too few macro conditions are safe. Forcing trades here historically loses money.",
    userAction: "No action. This is protective, not an error.",
  };
}


// ---------------------------------------------------------------------------
// Engine
// ---------------------------------------------------------------------------

export interface EngineStatus {
  id: "A" | "B" | "C";
  label: string;
  armed: boolean;
  blockedBy: string;
}

export function describeEngines(
  state: CurrentState | undefined,
): EngineStatus[] {
  const ctx = state?.context_values || {};
  const stress = !!state?.stress_regime;
  const directional = !!state?.directional_regime;
  const creditOk = (ctx as any).credit_stable === true;
  const ratesOk  = (ctx as any).rates_calm === true;

  const A: EngineStatus = {
    id: "A",
    label: "Engine A · mean reversion",
    armed: stress && state?.engine === "A",
    blockedBy: stress
      ? (state?.engine === "A"
          ? "armed"
          : "waiting for oversold setup")
      : "not in stress regime",
  };
  const B: EngineStatus = {
    id: "B",
    label: "Engine B · credit + rates",
    armed: directional && state?.engine === "B",
    blockedBy: !directional
      ? "not in directional regime"
      : (!creditOk && !ratesOk ? "waiting for credit + rates alignment"
         : !creditOk ? "waiting for credit alignment"
         : !ratesOk  ? "waiting for rates alignment"
         : (state?.engine === "B" ? "armed" : "conditions not yet met")),
  };
  const C: EngineStatus = {
    id: "C",
    label: "Engine C · ML candidate",
    armed: false,
    blockedBy: "disabled until enough data is collected",
  };
  return [A, B, C];
}

export function guideEngine(state: CurrentState | undefined): Guidance {
  if (!state) return {
    plain: "Engine state unknown — pipeline has not run.",
    goodBad: "neutral",
    why: "No snapshot data yet.",
    userAction: "Wait for next pipeline run.",
  };
  if (state.fire) return {
    plain: `Engine ${state.engine} is actively trading.`,
    goodBad: "good",
    why: "All conditions aligned for this strategy.",
    userAction: "Monitor position. System manages the exit.",
  };
  return {
    plain: "No engine is trading right now. This is protective, not an error.",
    goodBad: "warning",
    why: "Not enough conditions aligned to approve a strategy.",
    userAction: "Wait. System is watching for better setup.",
  };
}


// ---------------------------------------------------------------------------
// Risk
// ---------------------------------------------------------------------------

export function guideRisk(
  summary: PaperSummary | undefined,
  critCount: number,
  warnCount: number,
): Guidance {
  const dd = summary?.max_drawdown_pct ?? 0;
  if (critCount > 0) return {
    plain: `${critCount} critical anomal${critCount === 1 ? "y" : "ies"} open.`,
    goodBad: "bad",
    why: "System detected unusual behavior that may affect trading quality.",
    userAction: "Review anomalies panel. Pause new entries.",
  };
  if (warnCount > 0 || dd < -5) return {
    plain: dd < -5
      ? `Drawdown at ${dd.toFixed(1)}% — system tightening.`
      : `${warnCount} warning-level issue${warnCount === 1 ? "" : "s"} open.`,
    goodBad: "warning",
    why: "Non-critical issues present. System remains cautious.",
    userAction: "Monitor. No new trade recommended.",
  };
  return {
    plain: "Risk levels normal.",
    goodBad: "good",
    why: "No open anomalies and drawdown contained.",
    userAction: "No action required.",
  };
}


// ---------------------------------------------------------------------------
// Best-action aggregator
// ---------------------------------------------------------------------------

export function bestAction(
  state: CurrentState | undefined,
  summary: PaperSummary | undefined,
  critCount: number,
): string {
  if (critCount > 0) return "Best action: review — pause new entries.";
  if (!state) return "Best action: wait — system is warming up.";
  const dd = summary?.max_drawdown_pct ?? 0;
  if (dd < -5) return "Best action: monitor risk — system tightening.";
  if (state.fire) return "Best action: monitor — system is actively trading.";
  const { passing, total } = describeGates(state);
  if (passing >= total - 1) {
    return "Best action: monitor — system close to a high-quality setup.";
  }
  return "Best action: wait — system is not seeing a high-quality setup.";
}
