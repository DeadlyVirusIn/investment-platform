// UX-10 Phase 10B — OptionsStructureCard component.
//
// Source of truth: docs/research/UX_10_CONVICTION_ENGINE.md
//   Section 8 (Options UX)
//
// Hard rules enforced here:
//   - STRUCTURE is the only top-level options verb
//   - Loss named first, larger than max gain
//   - POP visible adjacent to reward/risk
//   - Risk graph slot always visible (never collapsed)
//   - Linked to underlying equity thesis (required)
//   - No "Buy now" CTA — only "[ See plan ]"

export type OptionsIntent =
  | "defined-risk bullish"
  | "defined-risk bearish"
  | "hedge"
  | "income (covered)"
  | "advanced (premium-sell)"
  | "advanced (naked directional)";


export interface OptionsStructureData {
  ticker: string;
  intent: OptionsIntent;
  structureType: string;        // e.g., "Long call vertical"
  strikes: string;              // e.g., "$175 / $190"
  expiry: string;               // e.g., "Jun 21"
  maxLoss: number;              // dollars
  maxGain: number;              // dollars
  breakeven: string;            // e.g., "$179.20"
  ivRank: number;               // 0–100
  popEstPct: number;            // 0–100
  underlyingThesisLabel: string; // e.g., "NVDA equity thesis: Semis cycle continuation"
  riskGraphSlot?: React.ReactNode;
  onSeePlanClick?: () => void;
}


function fmtMoney(n: number): string {
  return `$${n.toFixed(2)}`;
}


export default function OptionsStructureCard({
  ticker,
  intent,
  structureType,
  strikes,
  expiry,
  maxLoss,
  maxGain,
  breakeven,
  ivRank,
  popEstPct,
  underlyingThesisLabel,
  riskGraphSlot,
  onSeePlanClick,
}: OptionsStructureData) {
  const rewardRiskRatio = maxGain / maxLoss;

  return (
    <article
      className="ux10-card"
      data-test="ux10-options-structure-card"
      data-ticker={ticker}
      style={{ gap: 20 }}
    >
      {/* Header: STRUCTURE verb pill + intent sub-label */}
      <header className="ux10-card-header">
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span className="ux10-verb" data-verb="STRUCTURE" data-test="ux10-options-verb">
            STRUCTURE
          </span>
          <span style={{
            fontSize: "var(--ux10-fs-meta)",
            color: "var(--ux10-fg-secondary)",
            letterSpacing: "0.04em",
          }}>
            {intent} · {ticker}
          </span>
        </div>
      </header>

      {/* Structure name */}
      <p className="ux10-card-decision" style={{ fontSize: "var(--ux10-fs-h2)" }}>
        {structureType} · {strikes} · {expiry}
      </p>

      {/* Loss FIRST — visually larger than gain */}
      <section style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 16,
        alignItems: "baseline",
      }}>
        <div data-test="ux10-options-maxloss">
          <h4 className="ux10-card-section-label" style={{ color: "var(--ux10-risk)" }}>
            Max loss
          </h4>
          <p style={{
            margin: 0,
            fontSize: 28,
            fontFamily: "var(--ux10-font-mono)",
            fontWeight: 500,
            color: "var(--ux10-risk)",
            letterSpacing: "-0.01em",
          }}>
            {fmtMoney(maxLoss)}
          </p>
        </div>
        <div data-test="ux10-options-maxgain">
          <h4 className="ux10-card-section-label">Max gain</h4>
          <p style={{
            margin: 0,
            fontSize: 18,
            fontFamily: "var(--ux10-font-mono)",
            color: "var(--ux10-fg-secondary)",
          }}>
            {fmtMoney(maxGain)}
          </p>
        </div>
      </section>

      {/* Stats row — POP adjacent to reward/risk */}
      <div style={{
        display: "flex",
        gap: 24,
        flexWrap: "wrap",
        fontSize: "var(--ux10-fs-meta)",
        color: "var(--ux10-fg-tertiary)",
        fontFamily: "var(--ux10-font-mono)",
        paddingTop: 12,
        borderTop: "1px solid var(--ux10-border-card)",
      }}>
        <span>Breakeven {breakeven}</span>
        <span>IV rank {ivRank}</span>
        <span data-test="ux10-options-pop">POP est. {popEstPct}%</span>
        <span>R/R {rewardRiskRatio.toFixed(2)}x</span>
      </div>

      {/* Risk graph slot — ALWAYS VISIBLE */}
      <div style={{
        background: "var(--ux10-bg-elev)",
        border: "1px solid var(--ux10-border-card)",
        borderRadius: "var(--ux10-card-radius)",
        padding: 16,
        minHeight: 96,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "var(--ux10-fg-tertiary)",
        fontSize: "var(--ux10-fs-meta)",
        fontFamily: "var(--ux10-font-mono)",
      }} data-test="ux10-options-riskgraph">
        {riskGraphSlot ?? "[ Risk graph — P&L by spot at expiry ]"}
      </div>

      {/* Underlying thesis link — REQUIRED */}
      <div style={{
        fontSize: "var(--ux10-fs-meta)",
        color: "var(--ux10-fg-secondary)",
        borderTop: "1px solid var(--ux10-border-card)",
        paddingTop: 12,
      }}>
        Linked to {underlyingThesisLabel}
      </div>

      {/* Actions — only [See plan], NEVER "Buy now" */}
      <div className="ux10-card-actions">
        <button onClick={onSeePlanClick} data-test="ux10-options-seeplan">
          See plan →
        </button>
      </div>
    </article>
  );
}
