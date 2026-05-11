// Phase 15e.2 — Overview returning-user continuity layer.
//
// Lightweight localStorage-only memory of the last Overview snapshot
// the user saw. Compared on next visit to derive an honest one-line
// "what changed since your last visit" diff. No backend memory; no
// fabricated history; no long-term awareness implied.
//
// Per Phase 15d/15e discipline:
//  - REAL detectable changes only — derived from current vs prior
//    snapshot, both sourced from canonical /api/paper/summary +
//    fetchPicks data the page already has.
//  - No prior snapshot? Honest fallback line "No prior session
//    comparison available yet."
//  - Stale snapshot (>7 days)? "First visit this week" line so the
//    diff doesn't lie about a continuity that effectively reset.
//  - Empty diff? "Same picture as your last visit." (presence
//    without manufactured delta).

const KEY = "pi-overview-last-snapshot";
const STALE_MS = 7 * 24 * 60 * 60 * 1000; // 7 days


export interface OverviewSnapshot {
  ts: number;                  // unix ms when this snapshot was captured
  nav: number | null;          // commandBar.totalNav (canonical paper-summary equity)
  picksCount: number;          // sortedPicks.length
  buy: number;
  sell: number;
  trim: number;
  hold: number;
  posture: string;             // briefing.posture (e.g. "constructive")
  riskCount: number;
}


export type DiffStatus =
  | { kind: "no-prior" }                           // first visit, no localStorage entry
  | { kind: "stale"; daysAgo: number }              // prior snapshot too old to reason about
  | { kind: "no-change" }                           // prior exists, fresh, but nothing material moved
  | { kind: "diff"; parts: string[] };              // one or more honest deltas


export function readOverviewSnapshot(): OverviewSnapshot | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as OverviewSnapshot;
    if (typeof parsed.ts !== "number") return null;
    return parsed;
  } catch {
    return null;
  }
}


export function writeOverviewSnapshot(s: OverviewSnapshot): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}


// Derive the diff status. Pure function — no side effects, no IO.
// "Material" deltas are tuned to avoid noisy signal:
//   - NAV change > $5 (anything smaller = rounding / overnight cash sweep)
//   - Pick count change >= 1
//   - Posture string change
//   - Risk-flag change >= 1
//   - Action-distribution change in any cell >= 1
export function deriveOverviewDiff(
  prior: OverviewSnapshot | null,
  curr: OverviewSnapshot,
): DiffStatus {
  if (!prior) return { kind: "no-prior" };

  const ageMs = curr.ts - prior.ts;
  if (ageMs > STALE_MS) {
    return { kind: "stale", daysAgo: Math.round(ageMs / (24 * 60 * 60 * 1000)) };
  }

  const parts: string[] = [];

  // NAV delta — only when both ends have a real number AND the
  // change is large enough to be meaningful.
  if (prior.nav != null && curr.nav != null) {
    const navDelta = curr.nav - prior.nav;
    if (Math.abs(navDelta) >= 5) {
      const sign = navDelta >= 0 ? "+" : "−";
      const abs = Math.abs(navDelta);
      const formatted = abs >= 1000
        ? `$${(abs / 1000).toFixed(1)}k`
        : `$${abs.toFixed(0)}`;
      parts.push(`NAV ${sign}${formatted}`);
    }
  }

  // Picks count delta.
  const picksDelta = curr.picksCount - prior.picksCount;
  if (picksDelta > 0) {
    parts.push(`+${picksDelta} new pick${picksDelta === 1 ? "" : "s"}`);
  } else if (picksDelta < 0) {
    const dropped = -picksDelta;
    parts.push(`${dropped} pick${dropped === 1 ? "" : "s"} dropped`);
  }

  // Posture shift.
  if (prior.posture && curr.posture && prior.posture !== curr.posture) {
    parts.push(`posture: ${prior.posture} → ${curr.posture}`);
  }

  // Risk-flag delta.
  const riskDelta = curr.riskCount - prior.riskCount;
  if (riskDelta > 0) {
    parts.push(`+${riskDelta} risk-flagged`);
  } else if (riskDelta < 0) {
    parts.push(`${-riskDelta} fewer risk-flagged`);
  }

  // Action-distribution shifts (only if NOT already covered by picks
  // count delta — to avoid double-counting the same news).
  if (picksDelta === 0) {
    const buyD  = curr.buy  - prior.buy;
    const sellD = curr.sell - prior.sell;
    const trimD = curr.trim - prior.trim;
    if (buyD  !== 0) parts.push(`${buyD  > 0 ? "+" : ""}${buyD} buy`);
    if (sellD !== 0) parts.push(`${sellD > 0 ? "+" : ""}${sellD} sell`);
    if (trimD !== 0) parts.push(`${trimD > 0 ? "+" : ""}${trimD} trim`);
  }

  if (parts.length === 0) return { kind: "no-change" };
  return { kind: "diff", parts };
}


// One-line copy for each diff status. Calm institutional voice; no
// hype, no exclamation, no encouragement-talk.
export function diffSentence(status: DiffStatus): string {
  switch (status.kind) {
    case "no-prior":
      return "No prior session comparison available yet.";
    case "stale":
      return `First visit this week — last seen ${status.daysAgo}d ago.`;
    case "no-change":
      return "Same picture as your last visit.";
    case "diff":
      return `Since your last visit: ${status.parts.join(" · ")}.`;
  }
}
