// Phase UI-TERMINAL-LAYERS — Layer 1: NOW / NEXT / RISK rail.
// Thin context strip directly below MarketTicker. 30px.

import {
  useCurrentState, useAnomalySummary, useCanonicalDrawdownPct,
} from "@/lib/operator/hooks";
import { cn } from "@/lib/cn";

export default function StatusRail() {
  const { data: state } = useCurrentState();
  const { data: anom } = useAnomalySummary();
  // P2 root-shell canonicalization — drawdown risk flag derives from the
  // single canonical portfolio's equity curve, NOT the all-portfolios
  // aggregate (summary.max_drawdown_pct). Same source as NAV.
  const canonicalDd = useCanonicalDrawdownPct();

  // NOW
  const regime = state?.stress_regime ? "Stress"
    : state?.directional_regime ? "Directional" : "Neutral";
  const engineText = state?.fire
    ? `Engine ${state.engine} firing`
    : state?.engine && state.engine !== "none"
      ? `Engine ${state.engine} idle`
      : "no engine armed";
  const nowTone = state?.fire ? "accent"
    : state?.stress_regime ? "warn" : "pos";

  // NEXT
  const nextText = state?.fire
    ? "Monitor target exit"
    : state?.stress_regime
      ? "Await oversold setup (P15)"
      : state?.directional_regime
        ? "Await credit + rates alignment"
        : "Await regime qualification";

  // RISK
  const crit = anom?.by_severity?.critical ?? 0;
  const warn = anom?.by_severity?.warning ?? 0;
  const dd = canonicalDd ?? 0;
  const ddFlag = dd < -5 ? " · DD>5%" : dd < -2 ? " · DD watch" : "";
  let riskLabel: string;
  let riskTone: "pos" | "warn" | "neg" = "pos";
  if (crit > 0) {
    riskLabel = `${crit} critical${ddFlag}`;
    riskTone = "neg";
  } else if (warn > 0) {
    riskLabel = `${warn} warning${ddFlag}`;
    riskTone = "warn";
  } else {
    riskLabel = `Low · no anomalies${ddFlag}`;
    riskTone = "pos";
  }

  return (
    <div className="u-status-rail">
      <Segment label="NOW" tone={nowTone}
               value={`${regime} · ${engineText}`} />
      <Segment label="NEXT" tone="accent" value={nextText} />
      <Segment label="RISK" tone={riskTone} value={riskLabel} />
    </div>
  );
}

function Segment({ label, value, tone }: {
  label: string; value: string;
  tone: "pos" | "neg" | "warn" | "accent";
}) {
  const cls = {
    pos: "is-pos", neg: "is-neg", warn: "is-warn", accent: "is-accent",
  }[tone];
  return (
    <div className={cn("u-status-seg", cls)}>
      <span className="u-status-seg-label">{label}</span>
      <span className="u-status-seg-value">{value}</span>
    </div>
  );
}
