// UX-10 Phase 10B — ActionCard component.
//
// Source of truth: docs/research/UX_10_CONVICTION_ENGINE.md
//   Section 5 (ActionCard contract — refuses-to-render)
//   Section 5.3 (visual hierarchy: invalidation BEFORE target)
//
// Visual hierarchy top-to-bottom (locked):
//   1. Verb pill + tier-glyph + freshness chip
//   2. Ticker · thesis name
//   3. Decision sentence (the largest visual element)
//   4. INVALIDATION (FIRST — above target)
//   5. Driver / Counter / Catalyst thesis triplet
//   6. Target zone · horizon (LAST)
//   7. Reasoning · Bear · Snooze actions

import { useMemo } from "react";

import {
  type ActionCardData, validateActionCard, CardSchemaError,
} from "@/lib/copilot/conviction_card_schema";

import VerbPill from "./VerbPill";
import TierGlyph from "./TierGlyph";
import FreshnessChip from "./FreshnessChip";


export interface ActionCardProps {
  card: ActionCardData;
  onReasoningClick?: () => void;
  onBearClick?: () => void;
  onSnoozeClick?: () => void;
}


export default function ActionCard({
  card,
  onReasoningClick,
  onBearClick,
  onSnoozeClick,
}: ActionCardProps) {
  // Refuses-to-render: validation throws if any required field
  // missing or schema-invariant violated. Composer should have
  // caught this; if it didn't, we surface the failure inline so
  // it gets fixed.
  const validated = useMemo(() => {
    try {
      return validateActionCard(card);
    } catch (e) {
      if (e instanceof CardSchemaError) {
        // Render an inline error card so devs/QA can see exactly
        // which invariant failed. Production composer should never
        // produce a card that fails validation.
        return null;
      }
      throw e;
    }
  }, [card]);

  if (!validated) {
    return (
      <div
        className="ux10-card"
        data-test="ux10-card-error"
        style={{ borderColor: "var(--ux10-risk)" }}
      >
        <div className="ux10-card-header">
          <span style={{ color: "var(--ux10-risk)", fontFamily: "var(--ux10-font-mono)" }}>
            ActionCard refused to render — composer schema violation.
          </span>
        </div>
        <p className="ux10-card-decision" style={{ fontSize: 14 }}>
          {card.ticker || "(unknown ticker)"} · {card.thesisName || "(unknown thesis)"}
        </p>
      </div>
    );
  }

  const isStale = validated.freshnessState === "Stale";
  const isExpired = validated.freshnessState === "Expired";

  return (
    <article
      className="ux10-card"
      data-test="ux10-action-card"
      data-tier={validated.confidenceTier}
      data-freshness={validated.freshnessState}
      data-stale={isStale ? "true" : "false"}
      data-expired={isExpired ? "true" : "false"}
      data-ticker={validated.ticker}
    >
      {/* Header: verb · tier · freshness */}
      <header className="ux10-card-header">
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <VerbPill verb={validated.verb} />
          <TierGlyph tier={validated.confidenceTier} />
        </div>
        <FreshnessChip
          state={validated.freshnessState}
          lastReviewedAt={validated.lastReviewedAt}
          expiryCondition={validated.expiryCondition}
        />
      </header>

      {/* Ticker + thesis name */}
      <h3 className="ux10-card-title">
        <span style={{ color: "var(--ux10-fg-primary)", fontWeight: 600 }}>
          {validated.ticker}
        </span>
        {" · "}
        {validated.thesisName}
      </h3>

      {/* Decision sentence — THE LARGEST VISUAL ELEMENT */}
      <p className="ux10-card-decision">{validated.decisionSentence}</p>

      {/* Invalidation — ALWAYS FIRST (above target) */}
      <section>
        <h4 className="ux10-card-section-label">Invalidation</h4>
        <div className="ux10-invalidation">
          <p>{validated.invalidation}</p>
        </div>
      </section>

      {/* Driver / Counter / Catalyst */}
      <section>
        <h4 className="ux10-card-section-label">Driver · Counter · Catalyst</h4>
        <div className="ux10-thesis">
          <div className="ux10-thesis-side">
            <h4>Driver</h4>
            <p>{validated.thesis.driver}</p>
          </div>
          <div className="ux10-thesis-side">
            <h4>Counter</h4>
            <p>{validated.thesis.counter}</p>
          </div>
        </div>
        <p className="ux10-catalyst">{validated.thesis.catalyst}</p>
      </section>

      {/* Levels — ALWAYS LAST */}
      <footer className="ux10-levels">
        <span>
          Entry {validated.target.entry}
          {validated.target.t1 && ` · T1 ${validated.target.t1}`}
          {validated.target.t2 && ` · T2 ${validated.target.t2}`}
        </span>
        <span>{validated.horizon}</span>
      </footer>

      {/* Actions */}
      <div className="ux10-card-actions">
        <button onClick={onReasoningClick} data-test="ux10-card-reasoning">
          Reasoning ↓
        </button>
        <div style={{ display: "flex", gap: 8 }}>
          {validated.bearCaseGlyph && (
            <button onClick={onBearClick} data-test="ux10-card-bear" aria-label="See bear case">
              ⚖ Bear
            </button>
          )}
          <button onClick={onSnoozeClick} data-test="ux10-card-snooze">
            Snooze
          </button>
        </div>
      </div>
    </article>
  );
}
