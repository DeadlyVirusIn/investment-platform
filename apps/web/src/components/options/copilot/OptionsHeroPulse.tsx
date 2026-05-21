// OptionsHeroPulse — Today-page hero. Calm AI briefing.
//
// Reads exclusively from existing read-only endpoints. Renders ONE
// confident sentence + four pulse cells:
//   * AI posture (from /options/learning/summary)
//   * Volatility regime (from /options/features aggregated)
//   * Premium environment (from /options/features aggregated)
//   * Today's signal count (from /options/shadow/summary)
//
// Discipline:
//   * Zero math here. Server-side summaries only.
//   * Honest empty states. If a field is null, the cell says so.
//   * No execution buttons. No buy/sell.

import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";
import OptionsLiveStateChip from "./OptionsLiveStateChip";


interface LearningSummary {
  enabled?: boolean;
  ml_options_learning_enabled?: boolean;
  thresholds_met?: boolean;
  gate?: {
    closed_trades?: number;
    closed_trades_target?: number;
    distinct_strategies_meeting_floor?: number;
    distinct_strategies_target?: number;
    trading_days?: number;
    trading_days_target?: number;
  };
}

interface ShadowSummary {
  active?: boolean;
  latest_run_date?: string;
  total_runs?: number;
  underlying_count?: number;
  contracts_evaluated?: number;
  would_trade_count?: number;
  blocked_reason_counts?: Record<string, number>;
}


function classifyVolFromFeatures(_rows: Record<string, unknown>[]): string {
  // Aggregation heuristic — when iv_rank_252d is widely available,
  // average it; otherwise honest empty state. The classification logic
  // matches OptionsIVContext so both surfaces stay consistent.
  const ivRanks = _rows
    .map(r => r["iv_rank_252d"])
    .filter((v): v is number => typeof v === "number");
  if (ivRanks.length === 0) return "unavailable";
  const mean = ivRanks.reduce((a, b) => a + b, 0) / ivRanks.length;
  if (mean >= 75) return "rich";
  if (mean >= 50) return "elevated";
  if (mean >= 25) return "average";
  return "cheap";
}


export default function OptionsHeroPulse() {
  const [learning, setLearning] = useState<LearningSummary | null>(null);
  const [shadow, setShadow] = useState<ShadowSummary | null>(null);
  const [features, setFeatures] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    // Fetch universe symbols first, then fan-out one feature fetch per
    // symbol. /options/features requires a per-symbol query param, so
    // there is no batch endpoint to call. Honest fallback: when feature
    // values are NULL (history-fn gap), classifyVolFromFeatures returns
    // "unavailable" instead of fabricating a regime.
    (async () => {
      const [learn, shad, syms] = await Promise.all([
        fetch("/api/options/learning/summary")
          .then(r => r.ok ? r.json() : null).catch(() => null),
        fetch("/api/options/shadow/summary")
          .then(r => r.ok ? r.json() : null).catch(() => null),
        fetch("/api/options/symbols")
          .then(r => r.ok ? r.json() : null).catch(() => null),
      ]);
      if (cancelled) return;
      setLearning((learn as LearningSummary | null) ?? null);
      setShadow((shad as ShadowSummary | null) ?? null);

      const symList = (syms && typeof syms === "object"
        && Array.isArray((syms as Record<string, unknown>).symbols))
        ? (syms as { symbols: string[] }).symbols
        : [];

      const featRows = await Promise.all(symList.map(sym =>
        fetch(`/api/options/features?symbol=${encodeURIComponent(sym)}`)
          .then(r => r.ok ? r.json() : null)
          .then(j => j && typeof j === "object"
            ? (j as Record<string, unknown>).features as Record<string, unknown> | null
            : null)
          .catch(() => null),
      ));
      if (cancelled) return;
      setFeatures(featRows.filter((r): r is Record<string, unknown> => r != null));
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, []);

  // Posture derivation — read from learning + shadow summary:
  //   thresholds_met=true                       → "Calibrated"
  //   active shadow run + ! thresholds_met       → "Observing"
  //   no recent shadow run                      → "Idle"
  // This is honest framing of the engine state; no fabrication.
  const postureLabel = (() => {
    if (learning?.thresholds_met) return "Calibrated";
    if (shadow?.active && (shadow.total_runs ?? 0) > 0) return "Observing";
    return "Idle";
  })();
  // H-refine: cells row removed; calm sentence carries entire story.
  // wouldTrade / underlyings / volTier still drive sentence composition.
  const wouldTrade = shadow?.would_trade_count ?? null;
  const underlyings = shadow?.underlying_count ?? features.length ?? null;
  const volTier = classifyVolFromFeatures(features);

  // Phase H — first-person plural strategist voice. Calm. Confident.
  // Replaces engine-telemetry phrasing with a single human sentence.
  const calmSentence = (() => {
    if (loading) return "We're reading today's tape…";
    const parts: string[] = [];
    if (wouldTrade != null && wouldTrade > 0) {
      parts.push(
        `We're watching ${wouldTrade} setup${wouldTrade === 1 ? "" : "s"}`,
      );
    } else {
      parts.push("Nothing has crossed conviction yet today");
    }
    if (underlyings != null) {
      parts.push(`across ${underlyings} underlying${underlyings === 1 ? "" : "s"}`);
    }
    if (volTier !== "unavailable") {
      parts.push(`Premium environment is ${volTier}`);
    } else {
      parts.push("Premium environment is still loading");
    }
    return parts.join(". ") + ".";
  })();

  return (
    <section
      className={cn("opt-hero-pulse")}
      data-test="opt-hero-pulse"
    >
      {/* Phase J — asymmetric 2/3 + 1/3 hero. Left column carries the
          cinematic anchor (eyebrow + posture word + sentence). Right
          column carries the live-state chip + as-of timestamp as quiet
          chrome. On narrow widths the right column folds beneath the
          left (see .opt-today .opt-hero-header media query). */}
      <header className="opt-hero-header">
        <div className="opt-hero-moment">
          <div className="opt-narrative-eyebrow">Today · AI strategist</div>
          <div className="opt-hero-moment-word">{postureLabel}</div>
          <p className="opt-hero-sentence">{calmSentence}</p>
        </div>
        <div className="opt-hero-aside">
          <OptionsLiveStateChip />
          {shadow?.latest_run_date && (
            <p className="opt-hero-asof">As of {shadow.latest_run_date}</p>
          )}
        </div>
      </header>
    </section>
  );
}
