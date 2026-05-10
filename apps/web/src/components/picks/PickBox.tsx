// PickBox — color-loud BUY / SELL / TRIM / HOLD card.
//
// Shows: action badge + confidence meter, plain-English title,
// symbol + price, 1-sentence explanation, "what to do" line, freshness.

import type { Pick, LatestPrice } from "@/lib/picks/api";
import {
  confidenceLabel, fmtConfidencePct, confidenceFraction,
  actionTitle, actionGuidance,
} from "@/lib/picks/api";

import ConfidenceMeter from "./ConfidenceMeter";


export interface PickBoxProps {
  pick: Pick;
  price: LatestPrice | null | undefined;
  onClick: (pickId: string) => void;
}


function fmtRelTime(iso: string | null): string {
  if (!iso) return "—";
  const ms = Date.now() - Date.parse(iso);
  const hours = ms / 3_600_000;
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m ago`;
  if (hours < 24) return `${Math.round(hours)}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}


function fmtPrice(p: number | null): string {
  if (p == null) return "—";
  if (p >= 1000) return `$${p.toFixed(0)}`;
  return `$${p.toFixed(2)}`;
}


/** Plain-English 1-sentence explanation. Falls back to thesis. */
function plainExplanation(pick: Pick): string {
  const action = pick.adjusted_action ?? pick.action;
  const thesis = pick.thesis;

  // If thesis exists and reads naturally (>20 chars, contains a verb-ish word), use it
  if (thesis && thesis.length > 20 && /\b(is|are|has|been|holds?|signals?|shows?|points?|trend|ramp|growth|risk|catalyst|earn|capex|margin|momentum|valuation)\b/i.test(thesis)) {
    return thesis;
  }

  // Otherwise generate from action
  switch (action) {
    case "buy":  return "AI sees an entry opportunity here based on current signals.";
    case "sell": return "AI suggests exiting — risk currently outweighs upside.";
    case "trim": return "AI suggests reducing exposure — momentum has weakened.";
    case "hold": return "Signals are mixed; AI prefers to wait.";
  }
}


export default function PickBox({ pick, price, onClick }: PickBoxProps) {
  const action = pick.adjusted_action ?? pick.action;
  const confidence = pick.adjusted_confidence ?? pick.confidence;
  const confFrac = confidenceFraction(confidence);

  return (
    <button
      type="button"
      className="pick-box"
      data-action={action}
      data-test="pick-box"
      data-symbol={pick.symbol ?? ""}
      onClick={() => onClick(pick.id)}
      aria-label={`${action.toUpperCase()} ${pick.symbol ?? "asset"}, confidence ${fmtConfidencePct(confidence)}. Open details.`}
    >
      {/* Row 1: action badge + confidence */}
      <div className="pick-box-row1">
        <span className="pick-action">{action}</span>
        <span className="pick-confidence-cluster">
          <span>{confidenceLabel(confidence)}</span>
          <ConfidenceMeter fraction={confFrac} action={action} width={56} height={4} />
          <strong>{fmtConfidencePct(confidence)}</strong>
        </span>
      </div>

      {/* Row 2: plain-English title */}
      <h4 className="pick-title-line">{actionTitle(action)}</h4>

      {/* Row 3: symbol + price */}
      <div className="pick-box-row2">
        <h3 className="pick-symbol">{pick.symbol ?? "—"}</h3>
        {price === undefined && <span className="pick-price-loading">loading…</span>}
        {price === null && <span className="pick-price-loading">no quote</span>}
        {price && (
          <span className="pick-price" title={new Date(price.ts).toLocaleString()}>
            {fmtPrice(price.close)}
          </span>
        )}
      </div>

      {/* Row 4: explanation (1 sentence) */}
      <p className="pick-explain">{plainExplanation(pick)}</p>

      {/* Row 5: what to do (action guidance) */}
      <p className="pick-todo">{actionGuidance(action)}</p>

      {/* Footer */}
      <div className="pick-meta">
        <span>{fmtRelTime(pick.generated_at)}</span>
        <span>
          {pick.stale_data && <span className="pick-meta-warn">stale</span>}
          {!pick.enough_data && <span className="pick-meta-warn">thin data</span>}
          {!pick.stale_data && pick.enough_data && <span>—</span>}
        </span>
      </div>
    </button>
  );
}
