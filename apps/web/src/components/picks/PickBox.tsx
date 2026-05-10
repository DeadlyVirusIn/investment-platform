// PickBox — color-loud BUY / SELL / TRIM / HOLD card.
//
// Plain-English title + plain explanation + "what to do" line.
// Optional ranking label pill.

import type { Pick, LatestPrice } from "@/lib/picks/api";
import {
  confidenceLabel, fmtConfidencePct, confidenceFraction,
  actionTitle, actionGuidance,
} from "@/lib/picks/api";
import { plainExplain } from "@/lib/picks/copilot";

import ConfidenceMeter from "./ConfidenceMeter";


export interface PickBoxProps {
  pick: Pick;
  price: LatestPrice | null | undefined;
  rankingLabel?: string | null;
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


export default function PickBox({ pick, price, rankingLabel, onClick }: PickBoxProps) {
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
      <div className="pick-box-row1">
        <span className="pick-action">{action}</span>
        <span className="pick-confidence-cluster">
          <span>{confidenceLabel(confidence)}</span>
          <ConfidenceMeter fraction={confFrac} action={action} width={56} height={4} />
          <strong>{fmtConfidencePct(confidence)}</strong>
        </span>
      </div>

      {rankingLabel && (
        <span className="pick-rank-pill" data-action={action}>{rankingLabel}</span>
      )}

      <h4 className="pick-title-line">{actionTitle(action)}</h4>

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

      <p className="pick-explain">{plainExplain(pick)}</p>
      <p className="pick-todo">{actionGuidance(action)}</p>

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
