// PickBox — compact, scannable card with action color, tags, plain text.

import type { Pick, LatestPrice } from "@/lib/picks/api";
import {
  fmtConfidencePct, confidenceFraction,
  actionGuidance,
} from "@/lib/picks/api";
import { plainExplain, pickTags } from "@/lib/picks/copilot";

import ConfidenceMeter from "./ConfidenceMeter";


export interface PickBoxProps {
  pick: Pick;
  price: LatestPrice | null | undefined;
  rankingLabel?: string | null;
  eventBadge?: { text: string; tone: "good" | "warn" | "info" | "bad" } | null;
  onClick: (pickId: string) => void;
  // Phase 15f.3 — visited state. When true, the card carries
  // data-visited="true" which CSS uses to subtly fade the chrome.
  visited?: boolean;
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


function isFresh(iso: string | null): boolean {
  if (!iso) return false;
  return (Date.now() - Date.parse(iso)) < 2 * 3_600_000;
}


export default function PickBox({ pick, price, rankingLabel, eventBadge, onClick, visited }: PickBoxProps) {
  const action = pick.adjusted_action ?? pick.action;
  const confidence = pick.adjusted_confidence ?? pick.confidence;
  const confFrac = confidenceFraction(confidence);
  const tags = pickTags(pick);
  const fresh = isFresh(pick.generated_at);

  return (
    <button
      type="button"
      className="pick-box"
      data-action={action}
      data-fresh={fresh ? "true" : "false"}
      data-visited={visited ? "true" : "false"}
      data-test="pick-box"
      data-symbol={pick.symbol ?? ""}
      onClick={() => onClick(pick.id)}
      aria-label={`${action.toUpperCase()} ${pick.symbol ?? "asset"}, confidence ${fmtConfidencePct(confidence)}${visited ? ", reviewed" : ""}. Open details.`}
    >
      <div className="pick-box-top">
        <span className="pick-action">{action}</span>
        {fresh && <span className="pick-fresh-pulse" aria-label="Fresh signal" />}
        <span className="pick-conf-pct">{fmtConfidencePct(confidence)}</span>
      </div>

      <div className="pick-box-symrow">
        <h3 className="pick-symbol">{pick.symbol ?? "—"}</h3>
        {price === undefined && <span className="pick-price-loading">…</span>}
        {price === null && <span className="pick-price-loading">—</span>}
        {price && (
          <span className="pick-price" title={new Date(price.ts).toLocaleString()}>
            {fmtPrice(price.close)}
          </span>
        )}
      </div>

      <p className="pick-explain">{plainExplain(pick)}</p>

      {(tags.length > 0 || eventBadge) && (
        <div className="pick-tags">
          {eventBadge && (
            <span className="pick-tag pick-tag-event" data-tone={eventBadge.tone}>{eventBadge.text}</span>
          )}
          {tags.map((t, i) => (
            <span key={i} className="pick-tag" data-tone={t.tone}>{t.text}</span>
          ))}
        </div>
      )}

      <div className="pick-box-bottom">
        <ConfidenceMeter fraction={confFrac} action={action} width={64} height={3} />
        <span className="pick-meta-time">{fmtRelTime(pick.generated_at)}</span>
        {rankingLabel && (
          <span className="pick-rank-pill" data-action={action}>{rankingLabel}</span>
        )}
      </div>

      <p className="pick-todo-hint">{actionGuidance(action)}</p>
    </button>
  );
}
