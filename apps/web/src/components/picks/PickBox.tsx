// PickBox — premium green BUY / red SELL / neutral HOLD card.
//
// Shows: action + confidence meter, symbol + latest price,
// thesis (2-line clamp), top 2 supporting factors, freshness,
// optional risk/invalidation hint when present.

import type { Pick, LatestPrice } from "@/lib/picks/api";
import {
  confidenceLabel, fmtConfidencePct, confidenceFraction,
} from "@/lib/picks/api";

import ConfidenceMeter from "./ConfidenceMeter";


export interface PickBoxProps {
  pick: Pick;
  price: LatestPrice | null | undefined;   // undefined = still loading; null = unavailable
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


export default function PickBox({ pick, price, onClick }: PickBoxProps) {
  const action = (pick.adjusted_action ?? pick.action) as "buy" | "sell" | "hold";
  const confidence = pick.adjusted_confidence ?? pick.confidence;
  const confFrac = confidenceFraction(confidence);

  // Top 2 supporting factors (best-effort: only those with narrative)
  const topFactors = (pick.evidence ?? [])
    .filter(e => e.narrative && e.narrative.length > 0)
    .slice(0, 2);

  // Risk hint inline (only if present)
  const riskHint = pick.risk.invalidation_text
    ?? (pick.risk.stop_loss ? `Stop $${pick.risk.stop_loss.toFixed(2)}` : null);

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
      {/* Row 1: action + confidence meter */}
      <div className="pick-box-row1">
        <span className="pick-action">{action}</span>
        <span className="pick-confidence-cluster">
          <span>{confidenceLabel(confidence)}</span>
          <ConfidenceMeter fraction={confFrac} action={action} width={56} height={4} />
          <strong>{fmtConfidencePct(confidence)}</strong>
        </span>
      </div>

      {/* Row 2: symbol + price */}
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

      {/* Row 3: thesis */}
      <p className="pick-thesis">
        {pick.thesis ?? "Click for AI reasoning."}
      </p>

      {/* Row 4: top 2 factors */}
      {topFactors.length > 0 && (
        <div className="pick-factors">
          {topFactors.map((f, i) => (
            <div key={`${f.factor_key}-${i}`} className="pick-factor">
              <span className="pick-factor-text">{f.narrative}</span>
            </div>
          ))}
        </div>
      )}

      {/* Risk inline (only if present in rationale) */}
      {riskHint && (
        <div className="pick-risk" data-test="pick-risk">
          <strong>risk</strong> · {riskHint}
        </div>
      )}

      {/* Footer meta */}
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
