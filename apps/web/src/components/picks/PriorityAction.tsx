// PriorityAction — single most-important recommendation, hero-sized.

import type { LatestPrice } from "@/lib/picks/api";
import { fmtConfidencePct, confidenceLabel, actionTitle } from "@/lib/picks/api";
import type { PriorityResult, PicksFilter } from "@/lib/picks/copilot";


export interface PriorityActionProps {
  priority: PriorityResult;
  price: LatestPrice | null | undefined;
  onOpenCockpit: (pickId: string) => void;
  onFilterChange: (filter: PicksFilter) => void;
}


function fmtPrice(p: number | null): string {
  if (p == null) return "—";
  if (p >= 1000) return `$${p.toFixed(0)}`;
  return `$${p.toFixed(2)}`;
}


export default function PriorityAction({ priority, price, onOpenCockpit, onFilterChange }: PriorityActionProps) {
  const { pick, reason, ctaSecondary, ctaSecondaryFilter } = priority;
  const action = pick.adjusted_action ?? pick.action;
  const confidence = pick.adjusted_confidence ?? pick.confidence;

  return (
    <section className="picks-priority" data-action={action} data-test="picks-priority">
      <div className="picks-priority-eyebrow">
        <span className="picks-priority-dot" data-action={action} />
        Top action today
      </div>

      <div className="picks-priority-row">
        <div className="picks-priority-left">
          <div className="picks-priority-action-row">
            <span className="picks-priority-action" data-action={action}>{action}</span>
            <h2 className="picks-priority-symbol">{pick.symbol ?? "—"}</h2>
            {price && (
              <span className="picks-priority-price">{fmtPrice(price.close)}</span>
            )}
          </div>
          <h3 className="picks-priority-title">{actionTitle(action)}</h3>
          <p className="picks-priority-why"><strong>Why this matters:</strong> {reason}</p>
        </div>

        <div className="picks-priority-right">
          <div className="picks-priority-conf">
            <span className="picks-priority-conf-label">{confidenceLabel(confidence)} confidence</span>
            <span className="picks-priority-conf-pct">{fmtConfidencePct(confidence)}</span>
          </div>
        </div>
      </div>

      <div className="picks-priority-actions">
        <button
          type="button"
          className="picks-priority-cta picks-priority-cta-primary"
          onClick={() => onOpenCockpit(pick.id)}
        >
          Open research cockpit →
        </button>
        {ctaSecondaryFilter && (
          <button
            type="button"
            className="picks-priority-cta picks-priority-cta-secondary"
            onClick={() => onFilterChange(ctaSecondaryFilter)}
          >
            {ctaSecondary}
          </button>
        )}
      </div>
    </section>
  );
}
