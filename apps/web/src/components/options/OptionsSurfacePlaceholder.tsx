// Phase 6b-3-b — Placeholder shell for the new Options workspace surfaces.
//
// Renders a calm "this surface ships in 6b-3-{x}" page. Used by all 6
// new top-nav destinations (Research, Journal, Learning, Lab, Ops,
// Settings) until their proper pages land in subsequent sub-commits.
//
// Discipline:
//   * Read-only. NO mutation. NO trade buttons.
//   * No backend calls — pure static shell.
//   * Editorial tone matches the rest of the workspace; no error feel.
//   * data-test selector stable so 6b-3-{c..i} can replace bodies
//     without re-wiring tests.

interface Props {
  surface:        string;       // "Research" / "Journal" / etc.
  question:       string;       // single product question this surface answers
  shipsIn:        string;       // "6b-3-d" etc.
  one_liner:      string;       // calm one-line description
  willContain:    string[];     // 3-5 items the surface will host
}

export default function OptionsSurfacePlaceholder({
  surface, question, shipsIn, one_liner, willContain,
}: Props) {
  return (
    <section
      className="u-card u-card-accent-l is-accent"
      data-test={`options-surface-placeholder-${surface.toLowerCase()}`}
      style={{ padding: 24 }}
    >
      <div className="u-label" style={{ marginBottom: 10 }}>
        OPTIONS · {surface.toUpperCase()}
      </div>

      <h2 className="u-title-lg" style={{ marginBottom: 8, maxWidth: "52ch" }}>
        {question}
      </h2>

      <p
        className="u-body"
        style={{ maxWidth: "62ch", color: "var(--fg-2)" }}
      >
        {one_liner}
      </p>

      <div
        style={{
          marginTop: 24,
          paddingTop: 16,
          borderTop: "1px solid var(--border-subtle)",
        }}
      >
        <div
          className="u-label-sm"
          style={{ marginBottom: 8 }}
        >
          THIS SURFACE WILL CONTAIN
        </div>
        <ul
          style={{
            margin: 0,
            paddingLeft: 18,
            color: "var(--fg-2)",
            fontSize: 14,
            lineHeight: "22px",
          }}
        >
          {willContain.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>

      <div
        className="u-caption-2"
        style={{
          marginTop: 18,
          color: "var(--fg-3)",
          fontFamily: "var(--mono)",
        }}
      >
        ships in {shipsIn} · placeholder shell during 6b-3-b routing
        skeleton
      </div>
    </section>
  );
}
