// UX-5B Phase B-1 — overview_derive unit coverage.
//
// Pure functions. Exercises the deterministic composition rules
// (per-block) and the locked refinements (R-A through R-H).

import { describe, it, expect } from "vitest";
import {
  deriveHoldingsSummary, deriveIdeaCard, deriveQuietDay, deriveRiskLine,
  deriveTodaysIdeas, deriveTodayLine, deriveWatch, deriveWhatChanged,
  greetingSlotFromHour, variantIndexFromYMD,
} from "@/lib/copilot/overview_derive";


// ---------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------

const YMD = "2026-05-08";


// ---------------------------------------------------------------------
// 0. Variant index + greeting slot
// ---------------------------------------------------------------------

describe("variantIndexFromYMD", () => {
  it("returns day-of-month modulo n for valid dates", () => {
    expect(variantIndexFromYMD("2026-05-08", 2)).toBe(0);  // 8 % 2 = 0
    expect(variantIndexFromYMD("2026-05-09", 2)).toBe(1);
    expect(variantIndexFromYMD("2026-05-08", 3)).toBe(2);  // 8 % 3 = 2
  });

  it("returns 0 for malformed dates", () => {
    expect(variantIndexFromYMD("garbage", 3)).toBe(0);
    expect(variantIndexFromYMD("", 3)).toBe(0);
    expect(variantIndexFromYMD("2026/05/08", 3)).toBe(0);
  });

  it("returns 0 when n <= 0", () => {
    expect(variantIndexFromYMD("2026-05-08", 0)).toBe(0);
    expect(variantIndexFromYMD("2026-05-08", -1)).toBe(0);
  });
});


describe("greetingSlotFromHour", () => {
  it("maps hour to slot", () => {
    expect(greetingSlotFromHour(0)).toBe("morning");
    expect(greetingSlotFromHour(11)).toBe("morning");
    expect(greetingSlotFromHour(12)).toBe("afternoon");
    expect(greetingSlotFromHour(17)).toBe("afternoon");
    expect(greetingSlotFromHour(18)).toBe("evening");
    expect(greetingSlotFromHour(23)).toBe("evening");
  });
});


// ---------------------------------------------------------------------
// 1. Block 1 — today line
// ---------------------------------------------------------------------

describe("deriveTodayLine", () => {
  it("renders greeting + system + market line for known regime", () => {
    const out = deriveTodayLine({
      todayYMD: YMD, localHour: 9, regimeLabel: "calm",
    });
    expect(out.greeting).toMatch(/morning|Morning/);
    expect(out.systemReviewed).toContain("system reviewed");
    expect(out.marketLine).toMatch(/calm|quiet/);
    expect(out.catchingUp).toBeNull();
  });

  it("rotates greeting variant by date", () => {
    const a = deriveTodayLine({
      todayYMD: "2026-05-08", localHour: 9, regimeLabel: "calm",
    });
    const b = deriveTodayLine({
      todayYMD: "2026-05-09", localHour: 9, regimeLabel: "calm",
    });
    expect(a.greeting).not.toBe(b.greeting);
  });

  it("rotates market-line variant by date for same regime", () => {
    const a = deriveTodayLine({
      todayYMD: "2026-05-08", localHour: 9, regimeLabel: "stress",
    });
    const b = deriveTodayLine({
      todayYMD: "2026-05-09", localHour: 9, regimeLabel: "stress",
    });
    expect(a.marketLine).not.toBe(b.marketLine);
  });

  it("emits null marketLine when regime unknown", () => {
    const out = deriveTodayLine({
      todayYMD: YMD, localHour: 9, regimeLabel: "unrecognised",
    });
    expect(out.systemReviewed).not.toBeNull();
    expect(out.marketLine).toBeNull();
  });

  it("replaces body with catching-up line when pipelineFailed", () => {
    const out = deriveTodayLine({
      todayYMD: YMD, localHour: 9, regimeLabel: "calm",
      pipelineFailed: true,
    });
    expect(out.systemReviewed).toBeNull();
    expect(out.marketLine).toBeNull();
    expect(out.catchingUp).toContain("catching up");
  });

  it("never emits banned engine vocabulary in rendered fields", () => {
    const banned = [
      "regime", "stress", "trending", "gate", "anomaly",
      "pipeline", "ingest", "scheduler", "advisory", "engine",
    ];
    for (const r of ["calm", "trending", "choppy", "stress"]) {
      const out = deriveTodayLine({
        todayYMD: YMD, localHour: 9, regimeLabel: r,
      });
      const blob = [
        out.greeting, out.systemReviewed, out.marketLine,
      ].filter(Boolean).join(" ").toLowerCase();
      for (const tok of banned) {
        expect(blob).not.toContain(tok);
      }
    }
  });
});


// ---------------------------------------------------------------------
// 2. Block 2 — holdings summary
// ---------------------------------------------------------------------

describe("deriveHoldingsSummary", () => {
  it("renders empty-state line when openCount is 0", () => {
    const out = deriveHoldingsSummary({ openCount: 0 });
    expect(out.countSentence).toContain("No open paper positions");
    expect(out.stateClause).toBeNull();
  });

  it("singular noun for exactly 1 position", () => {
    const out = deriveHoldingsSummary({ openCount: 1 });
    expect(out.countSentence).toBe("1 paper position.");
  });

  it("plural noun for N>1 positions", () => {
    const out = deriveHoldingsSummary({ openCount: 5 });
    expect(out.countSentence).toBe("5 paper positions.");
  });

  it("omits state-clause when state counts are null (mark not wired)", () => {
    const out = deriveHoldingsSummary({
      openCount: 3, approachingTargetCount: null,
      needsAttentionCount: null,
    });
    expect(out.stateClause).toBeNull();
  });

  it("renders 'one approaching target' state-clause when 1/3", () => {
    const out = deriveHoldingsSummary({
      openCount: 3, approachingTargetCount: 1, needsAttentionCount: 0,
    });
    expect(out.stateClause).toContain("approaching its target");
  });

  it("renders 'all stable' clause when 0/N approaching", () => {
    const out = deriveHoldingsSummary({
      openCount: 3, approachingTargetCount: 0, needsAttentionCount: 0,
    });
    expect(out.stateClause).toContain("quietly working");
  });

  it("escalates to 'needs attention' over approaching", () => {
    const out = deriveHoldingsSummary({
      openCount: 3, approachingTargetCount: 1, needsAttentionCount: 1,
    });
    expect(out.stateClause).toContain("needs attention");
  });

  it("link points at the brief portfolio view", () => {
    const out = deriveHoldingsSummary({ openCount: 1 });
    expect(out.linkHref).toBe("/portfolio?view=brief");
  });
});


// ---------------------------------------------------------------------
// 3. Block 3 — today's ideas (R-A locks)
// ---------------------------------------------------------------------

describe("deriveIdeaCard", () => {
  it("uses 'Today' temporal cue (R-H — never 'Day 0')", () => {
    const out = deriveIdeaCard({ symbol: "AAPL" });
    expect(out.temporal).toBe("Today");
  });

  it("renders a generic observational sentence when nothing matches", () => {
    const out = deriveIdeaCard({ symbol: "AAPL" });
    expect(out.observation).toBe("On the system's shortlist today.");
  });

  it("prefers sector strengthening when present", () => {
    const out = deriveIdeaCard({
      symbol: "XOM", sector: "Energy",
      sectorStrengthening: true, entryZoneReached: true,
    });
    expect(out.observation).toBe("Energy continued strengthening.");
  });

  it("falls back to entry-zone observation when no sector signal", () => {
    const out = deriveIdeaCard({
      symbol: "AAPL", entryZoneReached: true,
    });
    expect(out.observation).toBe("Entry zone reached.");
  });

  it("renders base-building with the moving-average window", () => {
    const out = deriveIdeaCard({
      symbol: "MSFT", baseAverageWindow: 50,
    });
    expect(out.observation).toBe(
      "Building a base near the 50-day average.",
    );
  });

  it("renders earnings observation when within 5 days", () => {
    const out = deriveIdeaCard({
      symbol: "MSFT", earningsDaysAway: 3,
    });
    expect(out.observation).toBe("Reports earnings later this week.");
  });

  it("never emits banned conviction vocabulary", () => {
    const banned = [
      "strong", "high-confidence", "high confidence",
      "best", "top pick", "ranked", "score", "conviction",
      "buy now", "act now", "hot",
    ];
    const samples = [
      deriveIdeaCard({ symbol: "AAPL" }),
      deriveIdeaCard({ symbol: "AAPL", entryZoneReached: true }),
      deriveIdeaCard({ symbol: "AAPL", recentlyMoved: true }),
      deriveIdeaCard({ symbol: "AAPL", baseAverageWindow: 200 }),
      deriveIdeaCard({ symbol: "AAPL", earningsDaysAway: 2 }),
      deriveIdeaCard({
        symbol: "AAPL", sector: "Tech", sectorStrengthening: true,
      }),
    ];
    for (const out of samples) {
      const lower = out.observation.toLowerCase();
      for (const tok of banned) {
        expect(lower).not.toContain(tok);
      }
    }
  });
});


describe("deriveTodaysIdeas", () => {
  it("returns null when no ideas (R-E — block absent)", () => {
    const out = deriveTodaysIdeas({ ideas: [] });
    expect(out).toBeNull();
  });

  it("caps at 3 cards (R-F — 30s scan target)", () => {
    const ideas = ["A", "B", "C", "D", "E"]
      .map((symbol) => ({ symbol }));
    const out = deriveTodaysIdeas({ ideas });
    expect(out!.cards.length).toBe(3);
    expect(out!.truncatedFrom).toBe(5);
  });

  it("preserves order and renders Today cue on each card", () => {
    const out = deriveTodaysIdeas({
      ideas: [
        { symbol: "AAPL" },
        { symbol: "NVDA" },
      ],
    });
    expect(out!.cards.map((c) => c.symbol)).toEqual(["AAPL", "NVDA"]);
    for (const c of out!.cards) {
      expect(c.temporal).toBe("Today");
    }
  });
});


// ---------------------------------------------------------------------
// 4. Block 4 — what changed (R-C: ≤ 3 sentences, ≤ 80 chars each)
// ---------------------------------------------------------------------

describe("deriveWhatChanged", () => {
  it("returns null when nothing changed AND quiet fallback suppressed", () => {
    const out = deriveWhatChanged({}, /* suppressQuietFallback */ true);
    expect(out).toBeNull();
  });

  it("renders quiet-fallback sentence by default when nothing changed", () => {
    const out = deriveWhatChanged({});
    expect(out!.sentences).toEqual(["Today looks much like yesterday."]);
    expect(out!.isQuietFallback).toBe(true);
  });

  it("renders singular new-idea line for exactly 1 new", () => {
    const out = deriveWhatChanged({ newIdeas24h: 1 });
    expect(out!.sentences[0]).toBe("One new idea appeared overnight.");
    expect(out!.isQuietFallback).toBe(false);
  });

  it("renders plural new-ideas line with count", () => {
    const out = deriveWhatChanged({ newIdeas24h: 3 });
    expect(out!.sentences[0]).toBe("3 new ideas appeared overnight.");
  });

  it("caps at 3 sentences total", () => {
    const out = deriveWhatChanged({
      newIdeas24h: 2,
      positionsApproachingTarget: 1,
      positionsClosedToday: 4,
      regimePrev: "calm", regimeNow: "stress",
    });
    expect(out!.sentences.length).toBe(3);
  });

  it("each sentence is <= 80 chars (R-C)", () => {
    const out = deriveWhatChanged({
      newIdeas24h: 999, positionsApproachingTarget: 999,
      positionsClosedToday: 999,
      regimePrev: "trending", regimeNow: "stress",
    });
    for (const s of out!.sentences) {
      expect(s.length).toBeLessThanOrEqual(80);
    }
  });

  it("renders calm regime-shift phrase, not raw words", () => {
    const out = deriveWhatChanged({
      regimePrev: "calm", regimeNow: "stress",
    });
    const joined = out!.sentences.join(" ");
    expect(joined).toContain("Markets shifted from calm to unsettled");
    expect(joined.toLowerCase()).not.toContain("stress");
  });

  it("never emits banned engine vocabulary", () => {
    const banned = ["regime", "gate", "anomaly", "pipeline", "engine"];
    const out = deriveWhatChanged({
      newIdeas24h: 2, positionsClosedToday: 1,
      regimePrev: "calm", regimeNow: "trending",
    });
    const blob = out!.sentences.join(" ").toLowerCase();
    for (const tok of banned) {
      expect(blob).not.toContain(tok);
    }
  });
});


// ---------------------------------------------------------------------
// 5. Block 5 — risk line (conditional)
// ---------------------------------------------------------------------

describe("deriveRiskLine", () => {
  it("returns null when no triggers (R-E)", () => {
    expect(deriveRiskLine({})).toBeNull();
    expect(deriveRiskLine({ drawdownFromPeak: -0.02 })).toBeNull();
    expect(deriveRiskLine({ pausedStrategiesToday: 0 })).toBeNull();
  });

  it("renders drawdown sentence when dd <= -0.05", () => {
    const out = deriveRiskLine({ drawdownFromPeak: -0.072 });
    expect(out!.sentences[0]).toBe(
      "The account is 7% below its peak this week.",
    );
  });

  it("appends stress sentence when stressRegime + drawdown both trip", () => {
    const out = deriveRiskLine({
      drawdownFromPeak: -0.06, stressRegime: true,
    });
    expect(out!.sentences.length).toBe(2);
    expect(out!.sentences[1]).toBe("Markets remain unstable today.");
  });

  it("caps at 2 sentences", () => {
    const out = deriveRiskLine({
      drawdownFromPeak: -0.10, stressRegime: true,
      pausedStrategiesToday: 2,
    });
    expect(out!.sentences.length).toBe(2);
  });

  it("renders singular paused line for 1", () => {
    const out = deriveRiskLine({ pausedStrategiesToday: 1 });
    expect(out!.sentences[0]).toBe("One strategy paused itself today.");
  });
});


// ---------------------------------------------------------------------
// 6. Block 6 — watch this week (R-D)
// ---------------------------------------------------------------------

describe("deriveWatch", () => {
  it("returns null when no events", () => {
    expect(deriveWatch([])).toBeNull();
  });

  it("translates known macro codes via the locked map", () => {
    const out = deriveWatch([{ code: "CPI", day: "Wed" }]);
    expect(out!.lines).toEqual(["Inflation data arrives Wed."]);
  });

  it("translates earnings code with symbol", () => {
    const out = deriveWatch([
      { code: "EARNINGS", symbol: "AAPL", day: "Thu" },
    ]);
    expect(out!.lines).toEqual(["AAPL reports Thu."]);
  });

  it("omits unknown codes silently", () => {
    const out = deriveWatch([
      { code: "MYSTERY", day: "Mon" },
      { code: "FOMC", day: "Wed" },
    ]);
    expect(out!.lines).toEqual(["The Fed meets Wed."]);
  });

  it("dedupes repeated macro codes", () => {
    const out = deriveWatch([
      { code: "CPI", day: "Wed" },
      { code: "CPI", day: "Wed" },
      { code: "FOMC", day: "Thu" },
    ]);
    expect(out!.lines.length).toBe(2);
    expect(out!.lines[0]).toContain("Inflation");
    expect(out!.lines[1]).toContain("Fed");
  });

  it("does NOT dedupe earnings (multiple symbols may report same day)", () => {
    const out = deriveWatch([
      { code: "EARNINGS", symbol: "AAPL", day: "Thu" },
      { code: "EARNINGS", symbol: "MSFT", day: "Thu" },
    ]);
    expect(out!.lines.length).toBe(2);
  });

  it("caps at 3 lines (R-F)", () => {
    const events = ["CPI", "FOMC", "NFP", "GDP"].map((code) => ({
      code, day: "Wed",
    }));
    const out = deriveWatch(events);
    expect(out!.lines.length).toBe(3);
  });

  it("never emits raw event codes in rendered text", () => {
    const codes = ["CPI", "FOMC", "NFP", "ECI", "GDP", "ECB", "BOJ"];
    const events = codes.map((code) => ({ code, day: "Wed" }));
    const out = deriveWatch(events);
    const joined = out!.lines.join(" ");
    for (const c of codes) {
      // The rendered phrase must NOT contain the raw code.
      expect(joined).not.toContain(c);
    }
  });
});


// ---------------------------------------------------------------------
// 7. Quiet day (R-B — first-class, rotates by date)
// ---------------------------------------------------------------------

describe("deriveQuietDay", () => {
  it("returns greeting + body for any date", () => {
    const out = deriveQuietDay({ todayYMD: YMD, localHour: 9 });
    expect(out.greeting).toMatch(/morning|Morning/);
    expect(out.body.length).toBeGreaterThan(0);
  });

  it("rotates body across consecutive days", () => {
    const a = deriveQuietDay({ todayYMD: "2026-05-08", localHour: 9 });
    const b = deriveQuietDay({ todayYMD: "2026-05-09", localHour: 9 });
    const c = deriveQuietDay({ todayYMD: "2026-05-10", localHour: 9 });
    // Across 3 distinct days we should see at least 2 distinct
    // body sentences (2 of 3 are different).
    const distinct = new Set([a.body, b.body, c.body]).size;
    expect(distinct).toBeGreaterThanOrEqual(2);
  });

  it("never emits engine vocabulary in any variant", () => {
    const banned = [
      "signal", "batch", "regime", "gate", "anomaly",
      "pipeline", "ingest", "scheduler", "engine",
    ];
    for (const day of [1, 5, 10, 15, 20, 25, 30]) {
      const ymd = `2026-05-${String(day).padStart(2, "0")}`;
      const out = deriveQuietDay({ todayYMD: ymd, localHour: 9 });
      const blob = `${out.greeting} ${out.body}`.toLowerCase();
      for (const tok of banned) {
        expect(blob).not.toContain(tok);
      }
    }
  });
});
