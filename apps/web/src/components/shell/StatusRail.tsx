// Phase UI-TERMINAL-LAYERS — Layer 1: NOW / NEXT / PORTFOLIO rail.
// Thin context strip directly below MarketTicker. 30px.
// P1.6B.2 — third segment is a beginner-legible portfolio drawdown state
// (links to TrackRecord). Operator event counts moved to Observability.

import { Link } from "react-router-dom";
import {
  useCurrentState, useCanonicalDrawdownPct,
} from "@/lib/operator/hooks";
import { cn } from "@/lib/cn";

export default function StatusRail() {
  const { data: state } = useCurrentState();
  // P2 root-shell canonicalization — drawdown derives from the single
  // canonical portfolio's equity curve, NOT the all-portfolios aggregate
  // (summary.max_drawdown_pct). Same source as NAV. Unchanged in P1.6B.2.
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

  // PORTFOLIO — plain-language distance from the equity peak. No operator
  // vocabulary. Drawdown source unchanged.
  const dd = canonicalDd;
  let portfolioLabel: string;
  let portfolioTone: "pos" | "warn" | "neg" = "pos";
  if (dd == null) {
    portfolioLabel = "—";
  } else if (dd <= -2) {
    // Any meaningful drawdown (≥2% below peak) reads as caution amber; the
    // figure itself conveys severity (e.g. 3.1% vs 6.4% below peak).
    portfolioLabel = `${Math.abs(dd).toFixed(1)}% below peak`;
    portfolioTone = "warn";
  } else {
    portfolioLabel = "Near high";
  }

  return (
    <div className="u-status-rail">
      <Segment label="NOW" tone={nowTone}
               value={`${regime} · ${engineText}`} />
      <Segment label="NEXT" tone="accent" value={nextText} />
      <Segment label="PORTFOLIO" tone={portfolioTone}
               value={portfolioLabel} to="/track-record" />
    </div>
  );
}

function Segment({ label, value, tone, to }: {
  label: string; value: string;
  tone: "pos" | "neg" | "warn" | "accent";
  // P1.6B.2 — when set, the segment becomes a drilldown link (same class →
  // layout unchanged). Used by PORTFOLIO → TrackRecord for verifiability.
  to?: string;
}) {
  const cls = {
    pos: "is-pos", neg: "is-neg", warn: "is-warn", accent: "is-accent",
  }[tone];
  const inner = (
    <>
      <span className="u-status-seg-label">{label}</span>
      <span className="u-status-seg-value">{value}</span>
    </>
  );
  return to
    ? <Link to={to} className={cn("u-status-seg", cls)}>{inner}</Link>
    : <div className={cn("u-status-seg", cls)}>{inner}</div>;
}
