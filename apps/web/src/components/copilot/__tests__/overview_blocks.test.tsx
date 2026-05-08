// UX-5B Phase B-2 — block component smoke tests.
//
// Each component test asserts:
//   * renders without crashing for typical input
//   * returns null when its prop is null (R-E — empty
//     blocks collapse, no header alone)
//   * banned engine vocabulary absent from rendered HTML
//   * banned conviction language absent from idea cards (R-A)
//
// Uses react-dom/server.renderToStaticMarkup so the tests do
// not depend on @testing-library/react (not installed).
// Components rendered as static HTML strings; assertions happen
// against the resulting markup. Sufficient for content +
// data-test attribute checks.

import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

import TodayLine from "@/components/copilot/TodayLine";
import HoldingsSummary from "@/components/copilot/HoldingsSummary";
import IdeaCard from "@/components/copilot/IdeaCard";
import TodaysIdeas from "@/components/copilot/TodaysIdeas";
import WhatChangedBlock from "@/components/copilot/WhatChangedBlock";
import RiskLine from "@/components/copilot/RiskLine";
import WatchThisWeek from "@/components/copilot/WatchThisWeek";


// Decode the small set of HTML entities renderToStaticMarkup
// emits so substring assertions match natural copy
// ("Today's ideas" rather than "Today&#x27;s ideas").
function _decodeEntities(html: string): string {
  return html
    .replace(/&#x27;/g, "'")
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, "\"")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function renderToHtml(ui: ReactNode): string {
  return _decodeEntities(renderToStaticMarkup(<>{ui}</>));
}

function renderRoutedToHtml(ui: ReactNode): string {
  return _decodeEntities(
    renderToStaticMarkup(<MemoryRouter>{ui}</MemoryRouter>),
  );
}


// Universal banned-vocabulary check (UX-5 §3 + UX-5B locks).
const BANNED_IN_L1: ReadonlyArray<string> = [
  "signal", "batch", "regime", "gate", "anomaly", "pipeline",
  "ingest", "replay", "fill", "guard", "scheduler", "cron",
  "snapshot", "advisory", "engine", "pending", "cycle",
  "runner", "stage", "module", "as_of", "submitted_at",
  "Day 0",
];

function assertNoBannedVocab(html: string) {
  // Strip data-source / data-test attribute values which contain
  // engine-internal naming (paper_position:open_count etc.). The
  // user-facing rendered text is what we care about; data-*
  // attributes are audit-trail metadata.
  const visible = html
    .replace(/data-source="[^"]*"/g, "")
    .replace(/data-test="[^"]*"/g, "")
    .toLowerCase();
  for (const tok of BANNED_IN_L1) {
    expect(visible).not.toContain(tok.toLowerCase());
  }
}


// ---------------------------------------------------------------------
// 1. TodayLine
// ---------------------------------------------------------------------

describe("TodayLine", () => {
  it("renders greeting + body in the regime path", () => {
    const html = renderToHtml(
      <TodayLine
        data={{
          greeting: "Good morning.",
          systemReviewed: "The system reviewed today's market activity.",
          marketLine: "Markets are calm today.",
          catchingUp: null,
          dataSource: "regime:label,pipeline:status,as_of:2026-05-08",
        }}
      />,
    );
    expect(html).toContain("Good morning.");
    expect(html).toContain("Markets are calm today.");
    expect(html).toContain('data-test="copilot-today-greeting"');
    assertNoBannedVocab(html);
  });

  it("renders catching-up sentence in pipeline-failed path", () => {
    const html = renderToHtml(
      <TodayLine
        data={{
          greeting: "Good evening.",
          systemReviewed: null,
          marketLine: null,
          catchingUp: "We're catching up. See the working below for system status.",
          dataSource: "pipeline:status",
        }}
      />,
    );
    expect(html).toContain("catching up");
    // Note: the catching-up sentence intentionally references
    // "system status" — that's user-facing copy, not a banned
    // engine token. The banned list has "scheduler", "pipeline",
    // etc. — none appear in the rendered VISIBLE text.
    // Strip audit-trail data-source attributes before asserting
    // so machine-readable provenance (e.g. data-source="pipeline:
    // status") is excluded from the user-facing text check.
    const visible = html
      .replace(/data-source="[^"]*"/g, "")
      .replace(/data-test="[^"]*"/g, "")
      .toLowerCase();
    expect(visible).not.toContain("scheduler");
    expect(visible).not.toContain("pipeline");
  });

  it("omits body paragraph when both sentences are null", () => {
    const html = renderToHtml(
      <TodayLine
        data={{
          greeting: "Morning.",
          systemReviewed: null,
          marketLine: null,
          catchingUp: null,
          dataSource: "pipeline:status,as_of:2026-05-08",
        }}
      />,
    );
    expect(html).not.toContain('data-test="copilot-today-body"');
  });
});


// ---------------------------------------------------------------------
// 2. HoldingsSummary
// ---------------------------------------------------------------------

describe("HoldingsSummary", () => {
  it("appends state-clause as second sentence when present", () => {
    const html = renderRoutedToHtml(
      <HoldingsSummary
        data={{
          countSentence: "3 paper positions.",
          stateClause: "All quietly working",
          linkText: "See my holdings",
          linkHref: "/portfolio?view=brief",
          dataSource: "paper_position:open_count",
        }}
      />,
    );
    expect(html).toContain("3 paper positions. All quietly working.");
    assertNoBannedVocab(html);
  });

  it("renders only count sentence when state-clause null", () => {
    const html = renderRoutedToHtml(
      <HoldingsSummary
        data={{
          countSentence: "5 paper positions.",
          stateClause: null,
          linkText: "See my holdings",
          linkHref: "/portfolio?view=brief",
          dataSource: "paper_position:open_count",
        }}
      />,
    );
    expect(html).toContain("5 paper positions.");
    // state-clause text absent
    expect(html).not.toContain("quietly working");
  });

  it("link href targets the brief portfolio view", () => {
    const html = renderRoutedToHtml(
      <HoldingsSummary
        data={{
          countSentence: "1 paper position.",
          stateClause: null,
          linkText: "See my holdings",
          linkHref: "/portfolio?view=brief",
          dataSource: "paper_position:open_count",
        }}
      />,
    );
    expect(html).toMatch(/href="\/portfolio\?view=brief"/);
  });
});


// ---------------------------------------------------------------------
// 3. IdeaCard
// ---------------------------------------------------------------------

describe("IdeaCard", () => {
  it("renders symbol + Today temporal cue + observation", () => {
    const html = renderToHtml(
      <IdeaCard
        data={{
          symbol: "AAPL",
          temporal: "Today",
          observation: "Entry zone reached.",
          dataSource: "candidate_idea:entry_band",
        }}
      />,
    );
    expect(html).toContain("AAPL");
    expect(html).toContain("Today");
    expect(html).toContain("Entry zone reached.");
    assertNoBannedVocab(html);
  });

  it("never renders Day 0 cue (R-H lock)", () => {
    const html = renderToHtml(
      <IdeaCard
        data={{
          symbol: "AAPL",
          temporal: "Today",
          observation: "Entry zone reached.",
          dataSource: "test",
        }}
      />,
    );
    expect(html).not.toContain("Day 0");
  });

  it("never renders banned conviction vocabulary across template paths", () => {
    const observations = [
      "On the system's shortlist today.",
      "Entry zone reached.",
      "Pullback into support held.",
      "Building a base near the 50-day average.",
      "Reports earnings later this week.",
      "Recently moved.",
      "Energy continued strengthening.",
    ];
    const banned = [
      "strong", "high-confidence", "high confidence", "conviction",
      "best", "top pick", "ranked", "score", "buy now", "act now",
      "hot", "spicy",
    ];
    for (const obs of observations) {
      const html = renderToHtml(
        <IdeaCard
          data={{
            symbol: "AAPL", temporal: "Today",
            observation: obs, dataSource: "test",
          }}
        />,
      );
      const lower = html.toLowerCase();
      for (const tok of banned) {
        expect(lower).not.toContain(tok);
      }
    }
  });
});


// ---------------------------------------------------------------------
// 4. TodaysIdeas
// ---------------------------------------------------------------------

describe("TodaysIdeas", () => {
  it("returns null when data is null (R-E)", () => {
    const html = renderRoutedToHtml(<TodaysIdeas data={null} />);
    // MemoryRouter wrapper renders no DOM for null children;
    // the markup is empty.
    expect(html).toBe("");
  });

  it("renders header + cards + link when data present", () => {
    const html = renderRoutedToHtml(
      <TodaysIdeas
        data={{
          cards: [
            { symbol: "AAPL", temporal: "Today",
              observation: "Entry zone reached.",
              dataSource: "test" },
            { symbol: "NVDA", temporal: "Today",
              observation: "Building a base near the 50-day average.",
              dataSource: "test" },
          ],
        }}
      />,
    );
    expect(html).toContain("Today's ideas");
    expect(html).toContain("AAPL");
    expect(html).toContain("NVDA");
    expect(html).toContain("See all ideas");
    expect(html).toMatch(/href="\/ideas"/);
  });
});


// ---------------------------------------------------------------------
// 5. WhatChangedBlock
// ---------------------------------------------------------------------

describe("WhatChangedBlock", () => {
  it("returns null when data is null (R-E)", () => {
    const html = renderToHtml(<WhatChangedBlock data={null} />);
    expect(html).toBe("");
  });

  it("renders all sentences in order", () => {
    const html = renderToHtml(
      <WhatChangedBlock
        data={{
          sentences: [
            "One new idea appeared overnight.",
            "Two positions closed today.",
          ],
          dataSource: "test",
          isQuietFallback: false,
        }}
      />,
    );
    expect(html).toContain("One new idea appeared overnight.");
    expect(html).toContain("Two positions closed today.");
    assertNoBannedVocab(html);
  });

  it("renders quiet-fallback sentence when isQuietFallback=true", () => {
    const html = renderToHtml(
      <WhatChangedBlock
        data={{
          sentences: ["Today looks much like yesterday."],
          dataSource: "what_changed:quiet_fallback",
          isQuietFallback: true,
        }}
      />,
    );
    expect(html).toContain("looks much like yesterday");
  });
});


// ---------------------------------------------------------------------
// 6. RiskLine
// ---------------------------------------------------------------------

describe("RiskLine", () => {
  it("returns null when data is null (R-E + Strategic lock A)", () => {
    const html = renderToHtml(<RiskLine data={null} />);
    expect(html).toBe("");
  });

  it("renders header + sentences", () => {
    const html = renderToHtml(
      <RiskLine
        data={{
          sentences: [
            "The account is 7% below its peak this week.",
            "Markets remain unstable today.",
          ],
          dataSource: "test",
        }}
      />,
    );
    expect(html).toContain("What needs attention");
    expect(html).toContain("7% below its peak");
    expect(html).toContain("unstable today");
  });
});


// ---------------------------------------------------------------------
// 7. WatchThisWeek
// ---------------------------------------------------------------------

describe("WatchThisWeek", () => {
  it("returns null when data is null (R-E)", () => {
    const html = renderToHtml(<WatchThisWeek data={null} />);
    expect(html).toBe("");
  });

  it("renders watch lines", () => {
    const html = renderToHtml(
      <WatchThisWeek
        data={{
          lines: [
            "Inflation data arrives Wed.",
            "AAPL reports Thu.",
          ],
          dataSource: "test",
        }}
      />,
    );
    expect(html).toContain("What to watch this week");
    expect(html).toContain("Inflation data arrives Wed.");
    expect(html).toContain("AAPL reports Thu.");
  });

  it("never surfaces raw event codes (R-D)", () => {
    const html = renderToHtml(
      <WatchThisWeek
        data={{
          lines: [
            "Inflation data arrives Wed.",
            "The Fed meets Thu.",
          ],
          dataSource: "test",
        }}
      />,
    );
    expect(html).not.toContain("CPI");
    expect(html).not.toContain("FOMC");
  });
});
