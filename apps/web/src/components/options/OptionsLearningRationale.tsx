// Phase 6b-3-f — Why gates exist (methodological rationale).
//
// Pure-static explanatory section. Two paragraphs. Scientific tone.
// No motivational framing.

export default function OptionsLearningRationale() {
  return (
    <section
      className="u-card opt-learning-rationale"
      data-test="options-learning-rationale"
    >
      <header className="opt-card-header" style={{ marginBottom: 12 }}>
        <span className="opt-card-eyebrow">Why these gates exist</span>
      </header>

      <p
        className="u-body"
        style={{ marginBottom: 12, maxWidth: "72ch" }}
      >
        Each gate represents a methodological prerequisite the system
        must satisfy before it is permitted to make any calibrated
        claim about win rate, expected value, strategy-family
        performance, or rejection accuracy.
      </p>

      <p className="u-body" style={{ marginBottom: 16, maxWidth: "72ch" }}>
        Failing gates are not deficiencies. They are requirements
        not yet satisfied. The system is structurally prevented from
        producing predictive metrics until evidence accumulates past
        the thresholds above. The chronology beneath this section
        records that accumulation honestly.
      </p>

      <div
        style={{
          padding: "14px 16px",
          background: "var(--surface-1)",
          borderLeft: "2px solid var(--accent)",
          borderRadius: 6,
          fontSize: 13,
          lineHeight: "20px",
          color: "var(--fg-2)",
          maxWidth: "72ch",
        }}
      >
        When all gates pass AND the operator-only{" "}
        <code style={{
          fontFamily: "var(--mono)",
          fontSize: 12,
          color: "var(--fg)",
        }}>ML_OPTIONS_LEARNING_ENABLED</code>{" "}
        flag is set, this surface will additionally render: win
        rate per strategy with 95 % confidence interval, calibration
        plot (predicted vs realized in 5 bins), best/worst strategy
        contributors, and rejection-reason historical accuracy.
        Until both conditions hold, no such metric is computed or
        displayed.
      </div>
    </section>
  );
}
