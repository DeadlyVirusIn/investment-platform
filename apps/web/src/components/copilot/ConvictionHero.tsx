// UX-10 Phase 10C — ConvictionHero component.
//
// Source of truth: docs/research/UX_10_CONVICTION_ENGINE.md
//   Section 6 (Overview hero rules — 3 sections)
//
// Three sections, vertical:
//   1. Regime ribbon (one line + supporting clause)
//   2. Your active positions (existing holdings, max 3)
//   3. What the engine believes more strongly (promotions, max 2)
//
// Quiet-day state replaces sections 2+3 with locked Gemini copy.

import type { ConvictionHeroData } from "@/lib/copilot/conviction_compose";
import ActionCard from "./ActionCard";


export interface ConvictionHeroProps {
  data: ConvictionHeroData;
  onCardReasoning?: (ticker: string) => void;
  onCardBear?: (ticker: string) => void;
  onCardSnooze?: (ticker: string) => void;
}


export default function ConvictionHero({
  data,
  onCardReasoning,
  onCardBear,
  onCardSnooze,
}: ConvictionHeroProps) {
  return (
    <section className="ux10-hero" data-test="ux10-hero">
      {/* Section 1: Regime ribbon */}
      <div className="ux10-regime" data-test="ux10-regime">
        <div className="ux10-regime-label">Market regime</div>
        <div className="ux10-regime-stance">{data.regime.stance}</div>
        <p className="ux10-regime-clause">{data.regime.clause}</p>
      </div>

      {/* Quiet day */}
      {data.isQuiet && (
        <div className="ux10-quiet" data-test="ux10-quiet">
          <strong>{data.quietCopy ?? "Quiet day. No new entries recommended."}</strong>
        </div>
      )}

      {/* Section 2: Your active positions */}
      {!data.isQuiet && (
        <div className="ux10-section" data-test="ux10-section-active">
          <div className="ux10-section-head">
            <h2 className="ux10-section-title">Your active positions</h2>
            <span className="ux10-section-count">
              {data.activePositions.length} holding
              {data.activePositions.filter(c => c.freshnessState === "Stale" || c.freshnessState === "Aging").length > 0 &&
                ` · ${data.activePositions.filter(c => c.freshnessState === "Stale" || c.freshnessState === "Aging").length} aging`}
            </span>
          </div>
          <div className="ux10-card-stack">
            {data.activePositions.length === 0 ? (
              <div className="ux10-quiet">No active positions today.</div>
            ) : (
              data.activePositions.slice(0, 3).map(card => (
                <ActionCard
                  key={card.ticker}
                  card={card}
                  onReasoningClick={() => onCardReasoning?.(card.ticker)}
                  onBearClick={() => onCardBear?.(card.ticker)}
                  onSnoozeClick={() => onCardSnooze?.(card.ticker)}
                />
              ))
            )}
          </div>
        </div>
      )}

      {/* Section 3: Promotions since last visit */}
      {!data.isQuiet && data.promotions.length > 0 && (
        <div className="ux10-section" data-test="ux10-section-promotions">
          <div className="ux10-section-head">
            <h2 className="ux10-section-title">What the engine believes more strongly</h2>
            <span className="ux10-section-count">
              {data.promotions.length} promoted since Friday
            </span>
          </div>
          <div className="ux10-card-stack">
            {data.promotions.slice(0, 2).map(card => (
              <ActionCard
                key={card.ticker}
                card={card}
                onReasoningClick={() => onCardReasoning?.(card.ticker)}
                onBearClick={() => onCardBear?.(card.ticker)}
                onSnoozeClick={() => onCardSnooze?.(card.ticker)}
              />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
