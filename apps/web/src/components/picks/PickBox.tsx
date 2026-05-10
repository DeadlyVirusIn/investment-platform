// PickBox — green BUY / red SELL / neutral HOLD card.
// Click → opens modal with full details.

import type { Pick } from "@/lib/picks/api";
import { confidenceLabel, fmtConfidencePct } from "@/lib/picks/api";


export interface PickBoxProps {
  pick: Pick;
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


export default function PickBox({ pick, onClick }: PickBoxProps) {
  const action = (pick.adjusted_action ?? pick.action) as "buy" | "sell" | "hold";
  const confidence = pick.adjusted_confidence ?? pick.confidence;

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
        <span className="pick-confidence">{confidenceLabel(confidence)} · {fmtConfidencePct(confidence)}</span>
      </div>

      <h3 className="pick-symbol">{pick.symbol ?? "—"}</h3>

      <p className="pick-thesis">
        {pick.thesis ?? "Click for AI reasoning."}
      </p>

      <div className="pick-meta">
        <span>{fmtRelTime(pick.generated_at)}</span>
        {pick.stale_data && <span style={{ color: "var(--picks-sell)" }}>stale</span>}
        {!pick.enough_data && <span style={{ color: "var(--picks-sell)" }}>thin data</span>}
      </div>
    </button>
  );
}
