// optionsPresent — trader-facing presentation layer for options setups.
//
// Pure functions that translate engine vocabulary (rule_id, composite_score,
// bias, tiers) into language a trader reads in seconds — the same way the
// stock surfaces present a recommendation. NO operational metrics, NO
// fabricated economics.
//
// EXPLICITLY OUT OF SCOPE (Phase A): Max Profit, Max Risk, breakeven, POP.
// Those require complete spread legs the opportunity card does not carry
// (only the short leg is stored) and are deferred to a backend pass (Phase C).
// This module must never invent them.
//
// UI-only. No network, no mutation, no backend dependency.

import type { OptionsOpportunity } from './optionsLanes';

export type BiasTone = 'bull' | 'bear' | 'neutral' | 'vol';

interface StrategyMeta {
  name: string;
  tone: BiasTone;
  kind: 'income' | 'spread' | 'directional' | 'vol';
}

// Known v1 structures → human strategy name + directional tone + kind.
// Unknown rule_ids fall back to a title-cased label (never the raw id).
const STRATEGY_META: Record<string, StrategyMeta> = {
  SHORT_PUT_CREDIT_SPREAD:  { name: 'Put Credit Spread',  tone: 'bull',    kind: 'income' },
  SHORT_CALL_CREDIT_SPREAD: { name: 'Call Credit Spread', tone: 'bear',    kind: 'income' },
  IRON_CONDOR:              { name: 'Iron Condor',        tone: 'neutral', kind: 'income' },
  BULL_CALL_SPREAD:         { name: 'Bull Call Spread',   tone: 'bull',    kind: 'spread' },
  BEAR_PUT_SPREAD:          { name: 'Bear Put Spread',    tone: 'bear',    kind: 'spread' },
  LONG_CALL:                { name: 'Long Call',          tone: 'bull',    kind: 'directional' },
  LONG_PUT:                 { name: 'Long Put',           tone: 'bear',    kind: 'directional' },
  LONG_STRADDLE:            { name: 'Long Straddle',      tone: 'vol',     kind: 'vol' },
  LONG_STRANGLE:            { name: 'Long Strangle',      tone: 'vol',     kind: 'vol' },
};

function titleCase(s: string): string {
  return s
    .toLowerCase()
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

/** Human strategy name. Never returns the raw rule_id. */
export function strategyName(ruleId: string): string {
  return STRATEGY_META[ruleId]?.name ?? titleCase(ruleId);
}

/** Directional tone for color/dot. Falls back to the candidate's bias word. */
export function strategyTone(ruleId: string, bias?: string | null): BiasTone {
  const meta = STRATEGY_META[ruleId];
  if (meta) return meta.tone;
  const b = (bias ?? '').toLowerCase();
  if (b.includes('bull')) return 'bull';
  if (b.includes('bear')) return 'bear';
  if (b.includes('neutral')) return 'neutral';
  return 'neutral';
}

function biasWord(tone: BiasTone): string {
  switch (tone) {
    case 'bull': return 'Bullish';
    case 'bear': return 'Bearish';
    case 'neutral': return 'Neutral';
    case 'vol': return 'Volatility';
  }
}

/**
 * One-line plain-English descriptor under the strategy name, e.g.
 * "Bullish income · defined risk" / "Neutral income · defined risk" /
 * "Bullish directional".
 */
export function strategyDescriptor(
  ruleId: string,
  bias?: string | null,
  riskProfile?: string | null,
): string {
  const tone = strategyTone(ruleId, bias);
  const word = biasWord(tone);
  const defined = (riskProfile ?? '').toLowerCase() === 'defined';
  const kind = STRATEGY_META[ruleId]?.kind ?? 'directional';
  switch (kind) {
    case 'income':
      return defined ? `${word} income · defined risk` : `${word} income`;
    case 'spread':
      return defined ? `${word} · defined risk` : `${word} spread`;
    case 'vol':
      return 'Volatility · long premium';
    case 'directional':
    default:
      return `${word} directional`;
  }
}

/** Confidence on a 0–100 scale from the composite score (0–1). */
export function confidencePct(compositeScore: number): number {
  return Math.round((Number.isFinite(compositeScore) ? compositeScore : 0) * 100);
}

/** Coarse confidence word, mirroring the stock chip vocabulary. */
export function confidenceLabel(pct: number): 'High' | 'Medium' | 'Low' {
  if (pct >= 75) return 'High';
  if (pct >= 60) return 'Medium';
  return 'Low';
}

const PREMIUM_KNOWN = new Set(['rich', 'elevated', 'average', 'cheap']);
const LIQUIDITY_KNOWN = new Set(['good', 'fair', 'poor']);

/** "Rich premium" etc. Null when tier is unknown/absent — never fabricated. */
export function premiumLabel(tier?: string | null): string | null {
  const t = (tier ?? '').toLowerCase();
  return PREMIUM_KNOWN.has(t) ? `${titleCase(t)} premium` : null;
}

/** "Good liquidity" etc. Null when tier is unknown/absent. */
export function liquidityLabel(tier?: string | null): string | null {
  const t = (tier ?? '').toLowerCase();
  return LIQUIDITY_KNOWN.has(t) ? `${titleCase(t)} liquidity` : null;
}

/**
 * Catalyst chip text, e.g. "Earnings in 9 days" / "Earnings today".
 * Null when no named event sits inside the option's DTE window.
 */
export function catalystLabel(
  eventType?: string | null,
  daysAway?: number | null,
): string | null {
  if (!eventType) return null;
  const label = titleCase(eventType);
  if (daysAway == null) return label;
  if (daysAway <= 0) return `${label} today`;
  return `${label} in ${daysAway} day${daysAway === 1 ? '' : 's'}`;
}

// ── B.1: freshness / as-of ──────────────────────────────────────────────

// A short-leg quote older than this is treated as stale (chain refreshes
// at most daily; > 24h means it wasn't revalidated against fresh quotes).
export const STALE_QUOTE_SECONDS = 24 * 3600;

/** Humanized quote age, e.g. "12m old" / "3h old". Null when unknown. */
export function humanizeAge(seconds?: number | null): string | null {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return null;
  if (seconds < 90) return 'just now';
  const m = Math.round(seconds / 60);
  if (m < 60) return `${m}m old`;
  const h = Math.round(seconds / 3600);
  if (h < 48) return `${h}h old`;
  const d = Math.round(seconds / 86400);
  return `${d}d old`;
}

export interface Freshness {
  label: 'Fresh' | 'Stale' | 'Unknown';
  stale: boolean;
}

/** Fresh/Stale from the short-leg quote age. Unknown → treated as stale. */
export function quoteFreshness(seconds?: number | null): Freshness {
  if (seconds == null || !Number.isFinite(seconds)) {
    return { label: 'Unknown', stale: true };
  }
  return seconds > STALE_QUOTE_SECONDS
    ? { label: 'Stale', stale: true }
    : { label: 'Fresh', stale: false };
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Jun 1, 2026" from an ISO date. Null on missing/invalid. */
export function formatRunDate(iso?: string | null): string | null {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  if (mo < 1 || mo > 12) return null;
  return `${MONTHS[mo - 1]} ${d}, ${y}`;
}

// ── B.1: "What the engine is seeing" (ranking_breakdown) ─────────────────

export interface EngineViewRow {
  key: string;
  label: string;
  value: number; // 0–100
}

// Engine component → trader-friendly label. Mirrors stock "family scores".
const RANK_LABELS: ReadonlyArray<readonly [string, string]> = [
  ['score', 'Strategy fit'],
  ['freshness', 'Signal freshness'],
  ['liquidity', 'Liquidity'],
  ['iv_fit', 'IV fit'],
  ['event', 'Catalyst weight'],
];

/** Project ranking_breakdown into labelled 0–100 rows. Empty when absent. */
export function engineView(
  rb?: OptionsOpportunity['ranking_breakdown'],
): EngineViewRow[] {
  if (!rb) return [];
  const out: EngineViewRow[] = [];
  for (const [key, label] of RANK_LABELS) {
    const raw = (rb as Record<string, number | undefined>)[key];
    if (raw == null || !Number.isFinite(raw)) continue;
    out.push({ key, label, value: Math.round(raw * 100) });
  }
  return out;
}

// ── B.1: "Considered & rejected" (rejected_alternatives) ─────────────────

export interface RejectedAlternative {
  name: string;   // human strategy name (never raw rule_id)
  reason: string;
}

/** Map rejected_alternatives to {strategy name, reason}, dropping empties. */
export function rejectedList(
  arr?: OptionsOpportunity['rejected_alternatives'],
): RejectedAlternative[] {
  if (!arr || !Array.isArray(arr)) return [];
  const out: RejectedAlternative[] = [];
  for (const r of arr) {
    const reason = (r?.reason ?? '').trim();
    if (!reason) continue;
    out.push({
      name: r?.rule_id ? strategyName(r.rule_id) : 'Alternative',
      reason,
    });
  }
  return out;
}

/** One-line thesis. Prefers the engine's directional_view sentence. */
export function thesisLine(o: OptionsOpportunity): string | null {
  return (
    o.directional_view?.trim() ||
    o.strategy_fit_reason?.trim() ||
    o.why_emitted?.trim() ||
    null
  );
}

/**
 * "Why Arth likes this" bullet points. Prefers rationale_points; otherwise
 * assembles from the orthogonal fit reasons. De-duped, capped at `limit`.
 */
export function whyPoints(o: OptionsOpportunity, limit = 4): string[] {
  const fromRationale = (o.rationale_points ?? []).filter(Boolean);
  const points = fromRationale.length
    ? fromRationale
    : [
        o.strategy_fit_reason,
        o.iv_fit_reason,
        o.dte_fit_reason,
        o.liquidity_fit_reason,
      ].filter((x): x is string => !!x && x.trim().length > 0);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const p of points) {
    const k = p.trim();
    if (k && !seen.has(k)) {
      seen.add(k);
      out.push(k);
    }
    if (out.length >= limit) break;
  }
  return out;
}

// ── B.2 / Stage 2B: economics (from persisted legs, API-derived) ─────────

function fmtUsd(n: number, dp = 0): string {
  const v = Number.isFinite(n) ? n : 0;
  return `$${v.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp })}`;
}

function fmtStrike(n: number): string {
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const DT_MONTHS = MONTHS;

/** "Jun 2, 14:15" from an ISO datetime. Null on missing/invalid. */
export function formatPricedAsOf(iso?: string | null): string | null {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(iso);
  if (!m) return formatRunDate(iso);   // fall back to date-only
  const mo = Number(m[2]);
  if (mo < 1 || mo > 12) return null;
  return `${DT_MONTHS[mo - 1]} ${Number(m[3])}, ${m[4]}:${m[5]}`;
}

export interface PresentedEconomics {
  maxProfit: string;          // "$35"
  maxRisk: string;            // "$165"  (== "most you can lose", defined risk)
  capitalAtRisk: string;      // "$165"
  breakeven: string | null;   // "719.75" | "747.31 – 765.70"
  premium: string | null;     // "Credit $35" | "Debit $40"
  pricedAsOf: string | null;  // "Jun 2, 14:15"
  // Phase D — risk/reward framing. Null when profit/risk not both positive.
  riskRewardLine: string | null;  // "Risk $165 to make $35"
  rrRatio: string | null;         // "1 : 4.7"  (make : risk, 1 on smaller side)
  // Phase F2 — probability of profit (BS at expiry). Null when not derivable.
  pop: string | null;             // "76%"
  popConfidence: string | null;   // "High" | "Moderate" | "Low"
}

type EconRaw = NonNullable<OptionsOpportunity['economics']>;

/** Project the API economics object into display strings. Null in → null. */
export function presentEconomics(e?: EconRaw | null): PresentedEconomics | null {
  if (!e) return null;
  const lo = e.breakeven_lower;
  const hi = e.breakeven_upper;
  let breakeven: string | null = null;
  if (lo != null && hi != null) breakeven = `${fmtStrike(lo)} – ${fmtStrike(hi)}`;
  else if (lo != null) breakeven = fmtStrike(lo);
  else if (hi != null) breakeven = fmtStrike(hi);

  let premium: string | null = null;
  if (e.net_credit != null) premium = `Credit ${fmtUsd(e.net_credit)}`;
  else if (e.net_debit != null) premium = `Debit ${fmtUsd(e.net_debit)}`;

  // Risk/reward — arithmetic on existing economics only. Null (hidden) when
  // either side isn't a positive number — never a placeholder.
  const mp = e.max_profit;
  const mr = e.max_risk;
  let riskRewardLine: string | null = null;
  let rrRatio: string | null = null;
  if (Number.isFinite(mp) && Number.isFinite(mr) && mp > 0 && mr > 0) {
    riskRewardLine = `Risk ${fmtUsd(mr)} to make ${fmtUsd(mp)}`;
    rrRatio = mr >= mp
      ? `1 : ${(mr / mp).toFixed(1)}`
      : `${(mp / mr).toFixed(1)} : 1`;
  }

  return {
    maxProfit: fmtUsd(e.max_profit),
    maxRisk: fmtUsd(e.max_risk),
    capitalAtRisk: fmtUsd(e.capital_at_risk),
    breakeven,
    premium,
    pricedAsOf: formatPricedAsOf(e.priced_as_of),
    riskRewardLine,
    rrRatio,
    pop: e.pop != null ? `${e.pop}%` : null,
    popConfidence: e.pop_confidence ? titleCase(e.pop_confidence) : null,
  };
}

// ── Phase D — action directive (derived from existing state only) ────────

export type ActionTone = 'open' | 'consider' | 'watch' | 'skip';

export interface ActionDirective {
  label: 'Open' | 'Consider' | 'Watch' | 'Skip';
  tone: ActionTone;
}

/**
 * Plain action from existing qualification + confidence. No new scoring.
 * qualified (above the conviction floor) ⇒ Open; below floor, grade by
 * confidence. All four tiers reachable (qualified ⇒ conf high, so the
 * "qualified+mid" tier can't occur — qualified maps straight to Open).
 */
export function actionDirective(qualified: boolean, confidence: number): ActionDirective {
  if (qualified) return { label: 'Open', tone: 'open' };
  if (confidence >= 65) return { label: 'Consider', tone: 'consider' };
  if (confidence >= 50) return { label: 'Watch', tone: 'watch' };
  return { label: 'Skip', tone: 'skip' };
}

// ── Phase E — persisted legs + greeks (display, read-only) ───────────────

const ROLE_LABEL: Record<string, string> = {
  short_put: 'Short put',
  long_put: 'Long put',
  short_call: 'Short call',
  long_call: 'Long call',
};

export interface PresentedLeg {
  role: string;
  side: string;          // "Sell" | "Buy"
  optionType: string;    // "Put" | "Call"
  strike: string;        // "720.00"
  expiry: string | null; // "Jun 18, 2026"
  entryMid: string | null;   // "$6.82"
  delta: string | null;      // "-0.28"  (greeks — null hidden by callers)
  pricedAsOf: string | null; // "Jun 2, 14:15"
}

/** Project persisted legs for display. Empty when none. Nothing fabricated. */
export function presentLegs(legs?: OptionsOpportunity['legs']): PresentedLeg[] {
  if (!legs || !Array.isArray(legs)) return [];
  return legs.map((l) => ({
    role: l.role ? (ROLE_LABEL[l.role] ?? titleCase(l.role)) : '—',
    side: l.side ? titleCase(l.side) : '—',
    optionType: l.option_type ? titleCase(l.option_type) : '—',
    strike: l.strike != null ? fmtStrike(l.strike) : '—',
    expiry: formatRunDate(l.expiry),
    entryMid: l.entry_mid != null ? `$${l.entry_mid.toFixed(2)}` : null,
    delta: l.delta != null ? l.delta.toFixed(2) : null,
    pricedAsOf: formatPricedAsOf(l.priced_as_of),
  }));
}

// ── Phase F1 — assignment risk (display, read-only) ──────────────────────

export type AssignmentLevel = 'low' | 'moderate' | 'high';

export interface PresentedAssignment {
  level: AssignmentLevel;
  label: string;            // "High"
  reason: string;
  definedRiskNote: string;  // reassurance: loss capped by long wing
  dataCaveat: string;       // dividend/earnings not assessed
  showChip: boolean;        // chip on cards only for moderate|high
}

const _ASSIGN_DEFINED_RISK_NOTE =
  'Loss stays capped by the long leg even if the short leg is assigned.';
const _ASSIGN_DATA_CAVEAT =
  'Based on moneyness + days to expiry only. Dividend/earnings early-assignment ' +
  'is not assessed (that data is unavailable).';

/** Project the API assignment_risk object for display. Null in → null. */
export function presentAssignment(
  a?: OptionsOpportunity['assignment_risk'],
): PresentedAssignment | null {
  if (!a || !a.level) return null;
  const level = a.level;
  return {
    level,
    label: titleCase(level),
    reason: a.reason,
    definedRiskNote: _ASSIGN_DEFINED_RISK_NOTE,
    dataCaveat: _ASSIGN_DATA_CAVEAT,
    showChip: level !== 'low',
  };
}

export interface PresentedOption {
  observationId: number;
  underlying: string;
  ruleId: string;
  strategyName: string;
  descriptor: string;
  tone: BiasTone;
  confidence: number;          // 0–100
  confidenceLabel: 'High' | 'Medium' | 'Low';
  dte: number;
  expiry: string | null;            // ISO date the option expires
  premiumLabel: string | null;
  liquidityLabel: string | null;
  thesis: string | null;
  whyPoints: string[];
  catalyst: string | null;
  qualified: boolean;          // above the conviction floor
  family: OptionsOpportunity['family'];
  // B.1 trust/transparency
  runDate: string | null;            // "Jun 1, 2026" or null
  quoteAge: string | null;           // "3h old" or null
  freshness: Freshness;              // Fresh | Stale | Unknown
  engine: EngineViewRow[];           // "what the engine is seeing"
  rejected: RejectedAlternative[];   // considered & rejected
  economics: PresentedEconomics | null;  // Stage 2B — null when not derivable
  action: ActionDirective;           // Phase D — Open|Consider|Watch|Skip
  legs: PresentedLeg[];              // Phase E — persisted legs (empty when none)
  assignment: PresentedAssignment | null;  // Phase F1 — null when no short leg
}

/** Project one engine opportunity into a trader-facing view model. */
export function presentOption(o: OptionsOpportunity): PresentedOption {
  const confidence = confidencePct(o.composite_score);
  const tone = strategyTone(o.rule_id, o.bias);
  return {
    observationId: o.observation_id,
    underlying: o.underlying,
    ruleId: o.rule_id,
    strategyName: strategyName(o.rule_id),
    descriptor: strategyDescriptor(o.rule_id, o.bias, o.risk_profile),
    tone,
    confidence,
    confidenceLabel: confidenceLabel(confidence),
    dte: o.dte,
    expiry: o.expiry,
    premiumLabel: premiumLabel(o.premium_tier),
    liquidityLabel: liquidityLabel(o.liquidity_tier),
    thesis: thesisLine(o),
    whyPoints: whyPoints(o),
    catalyst: catalystLabel(o.earliest_event_type, o.event_days_away),
    qualified: !!o.above_floor,
    family: o.family,
    runDate: formatRunDate(o.run_date),
    quoteAge: humanizeAge(o.quote_age_seconds),
    freshness: quoteFreshness(o.quote_age_seconds),
    engine: engineView(o.ranking_breakdown),
    rejected: rejectedList(o.rejected_alternatives),
    economics: presentEconomics(o.economics),
    action: actionDirective(!!o.above_floor, confidence),
    legs: presentLegs(o.legs),
    assignment: presentAssignment(o.assignment_risk),
  };
}

/**
 * Rank engine setups for display: qualified (above-floor) first, then by
 * confidence descending. Stable, deterministic — no time/randomness.
 */
export function rankSetups(items: OptionsOpportunity[]): PresentedOption[] {
  return items
    .map(presentOption)
    .sort((a, b) => {
      if (a.qualified !== b.qualified) return a.qualified ? -1 : 1;
      return b.confidence - a.confidence;
    });
}

/** Strongest engine setup, or null when the list is empty. */
export function topSetup(items: OptionsOpportunity[]): PresentedOption | null {
  return rankSetups(items)[0] ?? null;
}
