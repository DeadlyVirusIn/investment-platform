// UX-11 Phase 11B — AIReadHero component.
//
// Source of truth: docs/research/UX_11_INTERACTIVE_COPILOT.md
//   Section 4 (AIReadHero spec)
//
// Single sentence, 64–110 chars, third-person AI voice.
// Label "TODAY'S AI READ" is the only persistent surface where
// "AI" appears as page chrome.

export interface AIReadHeroProps {
  text: string;          // composed via composeHeroFromGrammar() OR QUIET_DAY_HERO
  isQuiet?: boolean;     // hide AI READ label when quiet day
}


export default function AIReadHero({ text, isQuiet = false }: AIReadHeroProps) {
  return (
    <section className="ux11-airead-block" data-test="ux11-airead">
      {!isQuiet && (
        <div className="ux11-airead-label" aria-hidden="false">
          Today's AI Read
        </div>
      )}
      <p className="ux11-airead-text">{text}</p>
    </section>
  );
}
