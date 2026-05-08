// UX-2 Phase B — derivePositionStory unit coverage.
//
// Pure function — no I/O, no DOM. We assert only on the
// deterministic string composition + provenance attribute. Anti-AI
// theater is enforced by the lint script, not here.

import { describe, it, expect } from "vitest";
import {
  derivePositionStory, derivePositionTemporal, formatHumanDate,
} from "@/lib/copilot/derive";


describe("formatHumanDate", () => {
  it("renders YYYY-MM-DD as MMM D, YYYY", () => {
    expect(formatHumanDate("2026-05-02")).toBe("May 2, 2026");
    expect(formatHumanDate("2026-12-31")).toBe("Dec 31, 2026");
    expect(formatHumanDate("2026-01-01")).toBe("Jan 1, 2026");
  });

  it("trims ISO timestamps to date portion", () => {
    expect(formatHumanDate("2026-05-02T13:45:00Z"))
      .toBe("May 2, 2026");
  });

  it("returns em-dash on null/undefined/empty", () => {
    expect(formatHumanDate(null)).toBe("—");
    expect(formatHumanDate(undefined)).toBe("—");
    expect(formatHumanDate("")).toBe("—");
  });

  it("returns input on parse failure", () => {
    expect(formatHumanDate("garbage")).toBe("garbage");
    expect(formatHumanDate("2026/05/02")).toBe("2026/05/02");
  });
});


describe("derivePositionStory", () => {
  const baseInput = {
    symbol: "AAPL",
    quantity: 5,
    avg_cost: 182.4,
    opened_at: "2026-05-02",
    source: "live" as const,
  };

  it("renders the glance line with shares + bought clause", () => {
    const story = derivePositionStory(baseInput);
    expect(story.glance).toBe("5 shares · Bought May 2, 2026 at $182.40");
  });

  it("uses singular share noun when quantity is 1", () => {
    const story = derivePositionStory({ ...baseInput, quantity: 1 });
    expect(story.glance).toContain("1 share ·");
    expect(story.detail).toContain("1 share.");
  });

  it("renders the detail body with the same observed facts", () => {
    const story = derivePositionStory(baseInput);
    expect(story.detail)
      .toBe("Bought on May 2, 2026 at $182.40 — 5 shares.");
  });

  it("flags replay-sourced positions as recovered", () => {
    const live = derivePositionStory(baseInput);
    const replay = derivePositionStory({
      ...baseInput, source: "replay",
    });
    expect(live.isRecovered).toBe(false);
    expect(replay.isRecovered).toBe(true);
  });

  it("emits an audit-trail dataSource that names every field", () => {
    const story = derivePositionStory(baseInput);
    expect(story.dataSource).toContain("paper_position:symbol");
    expect(story.dataSource).toContain("paper_position:quantity");
    expect(story.dataSource).toContain("paper_position:avg_cost");
    expect(story.dataSource).toContain("paper_position:opened_at");
    expect(story.dataSource).toContain("paper_position:source");
  });

  it("renders em-dash on null pricing/qty/date instead of NaN", () => {
    const story = derivePositionStory({
      symbol: "TSLA", quantity: null, avg_cost: null,
      opened_at: null, source: "live",
    });
    expect(story.glance).not.toMatch(/NaN/);
    expect(story.detail).not.toMatch(/NaN/);
    expect(story.boughtOnLabel).toBe("—");
    // Quantity em-dash flows through to the noun choice — plural is
    // safer than singular when quantity is unknown.
    expect(story.glance).toContain("— shares");
  });

  it("preserves the symbol verbatim", () => {
    const story = derivePositionStory({ ...baseInput, symbol: "BRK.B" });
    expect(story.symbol).toBe("BRK.B");
  });

  it("strips trailing zeros on fractional quantities", () => {
    const story = derivePositionStory({
      ...baseInput, quantity: 2.5,
    });
    expect(story.glance).toContain("2.5 shares");
  });

  it("temporal is null when today is not provided", () => {
    const story = derivePositionStory(baseInput);
    expect(story.temporal).toBeNull();
  });

  it("temporal renders 'Opened today' when opened_at == today", () => {
    const story = derivePositionStory(baseInput, "2026-05-02");
    expect(story.temporal).toBe("Opened today");
  });

  it("temporal renders 'Day N' for prior opens", () => {
    const story = derivePositionStory(baseInput, "2026-05-05");
    // 3 days elapsed → Day 4
    expect(story.temporal).toBe("Day 4");
  });
});


describe("derivePositionTemporal", () => {
  it("returns null when opened_at is missing", () => {
    expect(derivePositionTemporal({ opened_at: null }, "2026-05-08"))
      .toBeNull();
    expect(derivePositionTemporal({ opened_at: undefined as never }, "2026-05-08"))
      .toBeNull();
  });

  it("returns null when opened_at is malformed", () => {
    expect(derivePositionTemporal({ opened_at: "garbage" }, "2026-05-08"))
      .toBeNull();
    expect(derivePositionTemporal({ opened_at: "2026/05/02" }, "2026-05-08"))
      .toBeNull();
  });

  it("matches Opened today for same-day opens", () => {
    expect(
      derivePositionTemporal({ opened_at: "2026-05-08" }, "2026-05-08"),
    ).toBe("Opened today");
  });

  it("returns Day 2 for an open one day ago", () => {
    expect(
      derivePositionTemporal({ opened_at: "2026-05-07" }, "2026-05-08"),
    ).toBe("Day 2");
  });

  it("returns Day N for arbitrary positive day counts", () => {
    expect(
      derivePositionTemporal({ opened_at: "2026-04-29" }, "2026-05-08"),
    ).toBe("Day 10");
  });

  it("tolerates ISO timestamps in opened_at", () => {
    expect(
      derivePositionTemporal(
        { opened_at: "2026-05-07T18:30:00Z" }, "2026-05-08",
      ),
    ).toBe("Day 2");
  });

  it("returns null on negative day counts (clock skew defensiveness)", () => {
    // opened_at is in the future relative to today. We refuse to
    // render rather than say "Day -1". This protects against client
    // clock skew or stale fixtures.
    expect(
      derivePositionTemporal({ opened_at: "2026-05-10" }, "2026-05-08"),
    ).toBeNull();
  });

  it("returns null beyond the 1000-day guard", () => {
    expect(
      derivePositionTemporal({ opened_at: "2020-01-01" }, "2026-05-08"),
    ).toBeNull();
  });
});
