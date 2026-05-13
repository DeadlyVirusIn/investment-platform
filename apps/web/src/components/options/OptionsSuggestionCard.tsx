// Phase Opt-C1 Step 4 — Suggestion card.
//
// Renders one research candidate. Top-3 grid is composed by
// OptionsResearchCandidates (Step 5).
//
// Discipline:
//   - NO win probability shown (until learning thresholds pass)
//   - NO "AI says" / "Top Pick" / "Best Trade" framing
//   - Setup quality dots + label only (relative, not absolute)
//   - Lifecycle pill ties suggestion to a paper-trade if one exists
//   - "Why passed" disclosure expands the 7 quality checks


import { useState } from "react";

import { cn } from "@/lib/cn";
import { dotsString, type SetupQuality } from "@/lib/options/setupQuality";


export interface SuggestionLeg {
  side: "BUY" | "SELL";
  option_type: "CALL" | "PUT";
  strike: string;
}


export interface SuggestionCardData {
  ticker: string;
  strategy_name: string;       // friendly name
  rule_id: string;             // raw DB key
  expiry: string;              // YYYY-MM-DD
  legs: SuggestionLeg[];
  max_risk_dollars: string | number | null;
  max_profit_dollars: string | number | null;
  breakeven: string | number | null;
  reading: string;             // 1-2 sentence narrative
  setup_quality: SetupQuality;
  rank: number;                // 1-based; 1/3 means top of 3
  total_today: number;         // denominator
  // Lifecycle binding (optional — populated post-Opt-B3 when a
  // paper trade was created for this candidate)
  lifecycle_status?:
    | "candidate" | "PROPOSED" | "OPEN" | "EXPIRING"
    | "CLOSED" | "EXPIRED" | "ASSIGNED";
  // Filter pass evidence — used by "Why passed" disclosure
  filter_passes?: Array<{ code: string; label: string; passed: boolean }>;
}


function _legSummary(legs: SuggestionLeg[]): string {
  return legs.map(L => {
    const s = L.side === "BUY" ? "Buy" : "Sell";
    const t = L.option_type === "CALL" ? "C" : "P";
    return `${s} ${t}${L.strike}`;
  }).join(" / ");
}


function _daysUntil(iso: string): number | null {
  const d = new Date(iso + "T00:00:00Z");
  if (Number.isNaN(d.getTime())) return null;
  const now = Date.now();
  return Math.max(0, Math.floor((d.getTime() - now) / 86_400_000));
}


function _fmtMoney(v: string | number | null): string {
  if (v == null || v === "") return "—";
  const n = typeof v === "number" ? v : parseFloat(v);
  if (Number.isNaN(n)) return String(v);
  const sign = n >= 0 ? "" : "-";
  return `${sign}$${Math.abs(n).toFixed(2)}`;
}


function _lifecyclePill(s: SuggestionCardData["lifecycle_status"]): {
  label: string; tone: string;
} {
  switch (s) {
    case "PROPOSED": return { label: "proposed", tone: "neutral" };
    case "OPEN":     return { label: "open",     tone: "pos" };
    case "EXPIRING": return { label: "expiring", tone: "warn" };
    case "CLOSED":   return { label: "closed",   tone: "accent" };
    case "EXPIRED":  return { label: "expired",  tone: "warn" };
    case "ASSIGNED": return { label: "assigned", tone: "neg" };
    default:         return { label: "candidate", tone: "neutral" };
  }
}


export default function OptionsSuggestionCard({ data }: { data: SuggestionCardData }) {
  const [whyOpen, setWhyOpen] = useState(false);
  const dte = _daysUntil(data.expiry);
  const pill = _lifecyclePill(data.lifecycle_status);

  return (
    <article
      className="opt-suggestion-card"
      data-test="options-suggestion-card"
      data-rule-id={data.rule_id}
      data-rank={data.rank}
    >
      {/* Header: ticker + dot quality + rank */}
      <header className="opt-suggestion-head">
        <span className="opt-suggestion-ticker">{data.ticker}</span>
        <span
          className="opt-suggestion-dots"
          aria-label={`Setup quality: ${data.setup_quality.label}`}
          title={data.setup_quality.label}
        >
          {dotsString(data.setup_quality.dots)}
        </span>
        <span className="opt-suggestion-rank">
          rank {data.rank}/{data.total_today}
        </span>
      </header>

      {/* Strategy + expiry */}
      <div className="opt-suggestion-strat">
        {data.strategy_name}
        <span className="opt-suggestion-exp">
          {" · exp "}{data.expiry}
          {dte !== null && ` (${dte}d)`}
        </span>
      </div>

      {/* Legs */}
      <div className="opt-suggestion-legs">{_legSummary(data.legs)}</div>

      {/* Risk metrics */}
      <dl className="opt-suggestion-metrics">
        <div className="opt-suggestion-kv">
          <dt>max risk</dt>
          <dd>{_fmtMoney(data.max_risk_dollars)}</dd>
        </div>
        <div className="opt-suggestion-kv">
          <dt>max profit</dt>
          <dd>{_fmtMoney(data.max_profit_dollars)}</dd>
        </div>
        <div className="opt-suggestion-kv">
          <dt>breakeven</dt>
          <dd>{_fmtMoney(data.breakeven)}</dd>
        </div>
      </dl>

      {/* Reading — 1-2 sentence narrative */}
      <div className="opt-suggestion-reading">
        <span className="opt-suggestion-reading-label">Reading</span>
        <p>{data.reading}</p>
      </div>

      {/* Footer: setup label + lifecycle pill */}
      <footer className="opt-suggestion-foot">
        <span className="opt-suggestion-label">
          Setup quality: {data.setup_quality.label}
          {data.setup_quality.underpowered && " (sample sparse)"}
        </span>
        <span
          className={cn("opt-suggestion-pill", `is-${pill.tone}`)}
          aria-label={`Lifecycle: ${pill.label}`}
        >
          {pill.label}
        </span>
      </footer>

      {/* "Why passed" disclosure */}
      {data.filter_passes && data.filter_passes.length > 0 && (
        <div className="opt-suggestion-why">
          <button
            type="button"
            className="opt-suggestion-why-toggle"
            aria-expanded={whyOpen}
            onClick={() => setWhyOpen(o => !o)}
          >
            {whyOpen ? "▾" : "▸"} Why this passed all{" "}
            {data.filter_passes.length} checks
          </button>
          {whyOpen && (
            <ul className="opt-suggestion-why-list">
              {data.filter_passes.map((f) => (
                <li
                  key={f.code}
                  className={cn("opt-suggestion-why-row",
                                f.passed ? "is-pos" : "is-neg")}
                >
                  <span className="opt-suggestion-why-mark">
                    {f.passed ? "✓" : "✗"}
                  </span>
                  <span>{f.label}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </article>
  );
}
