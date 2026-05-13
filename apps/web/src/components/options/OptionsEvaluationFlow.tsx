// Phase Opt-C1 Step 2 — How the engine evaluates setups.
//
// 6-step illustrated flow. Pure CSS, no data dependency. Visible
// in dormant mode + as collapsible reference in active mode.
//
// Discipline: educational, not aspirational. Explains the actual
// pipeline path; no claims about win rates or expected returns.


const STEPS: Array<{ n: number; title: string; body: string }> = [
  {
    n: 1,
    title: "Collect chains",
    body: "ThetaData EOD chains for the watchlist universe. Strike, "
        + "expiry, bid/ask, IV, OI, delta/gamma/theta/vega.",
  },
  {
    n: 2,
    title: "Score candidates",
    body: "Per-strategy formula evaluates every (symbol, expiry) "
        + "for setup quality.",
  },
  {
    n: 3,
    title: "Apply 7 quality checks",
    body: "Liquidity · spread · open interest · volume · greeks · "
        + "IV rank · risk budget. Plus earnings-window guard.",
  },
  {
    n: 4,
    title: "Rank survivors",
    body: "Top candidates per day surfaced for paper trading. "
        + "Rejected setups remain visible for audit.",
  },
  {
    n: 5,
    title: "Paper exec writes",
    body: "T+1 next-bar fill. Sole-writer service enforces dedup. "
        + "Never same-bar. Paper-only, structurally locked.",
  },
  {
    n: 6,
    title: "Lifecycle tracked",
    body: "PROPOSED → OPEN → CLOSED / EXPIRED / ASSIGNED. Every "
        + "transition emits an audit event.",
  },
];


export default function OptionsEvaluationFlow() {
  return (
    <section className="u-card opt-card" data-test="options-evaluation-flow">
      <header className="opt-card-header">
        <span className="opt-card-eyebrow">How the engine evaluates setups</span>
        <span className="opt-card-meta">6 steps · paper-only</span>
      </header>

      <ol className="opt-flow">
        {STEPS.map((s) => (
          <li key={s.n} className="opt-flow-step">
            <div className="opt-flow-num">{s.n}</div>
            <div className="opt-flow-text">
              <div className="opt-flow-title">{s.title}</div>
              <div className="opt-flow-body">{s.body}</div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
