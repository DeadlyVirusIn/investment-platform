// Phase 6b-3-a — Options hero (calm research pulse).
//
// Composition:
//   * u-card-lg gradient surface (already themed dark/light)
//   * 4 px gradient accent bar on left (u-card-accent-l) tone-derived
//     from /analytics/integrity flag count
//   * Eyebrow: "RESEARCH PULSE · {date}"
//   * Calm sentence (28 px sentence-case) — single product voice
//   * 65/35 split: contracts/candidates  |  integrity rail
//   * Integrity rail uses two visual tiers per design refinement 2:
//     PRIMARY (loud)    coherent batch, freshness within bound
//     SECONDARY (quiet) universe closure, shadow log live
//   * Bottom metadata strip: last batch / next fire / provider
//
// Discipline:
//   * Read-only. NO mutation. NO trade buttons. NO "live" wording.
//   * All numbers tabular-num via u-mono.
//   * All colors via var(--*) tokens; dark/light auto.
//   * No keyframe animations; only the existing u-card-hover tween
//     (and we don't use it on the hero — hero is still by design).

import { useQuery } from "@tanstack/react-query";

import { useOptionsPipelineStatus } from "@/lib/options/hooks";
import { apiGet } from "@/lib/api";


// ──────────────────────────────────────────────────────────────
// Endpoint shapes
// ──────────────────────────────────────────────────────────────

interface IntegrityResponse {
  run_date: string;
  coherent_batch_present: boolean;
  provider_homogeneous: boolean;
  universe_closure_pass: boolean;
  freshness_bound_pass: boolean;
  shadow_persistence_active: boolean;
  active_batch: null | {
    snapshot_at_utc: string;
    provider: string;
    provider_version: string;
    age_seconds: number;
    age_hours: number;
  };
  today_underlying_count: number;
  today_out_of_universe_count: number;
  today_provider_version_count: number;
  thresholds: {
    max_run_chain_age_hours: number;
    production_providers: string[];
    run_universe: string[];
  };
}

interface DailyCountsResponse {
  days: number;
  count: number;
  series: Array<{
    run_date: string;
    total: number;
    would_trade: number;
    blocked: number;
    underlyings: number;
    strategies: number;
  }>;
}


// ──────────────────────────────────────────────────────────────
// Hooks
// ──────────────────────────────────────────────────────────────

function useIntegrity() {
  return useQuery<IntegrityResponse>({
    queryKey: ["options", "analytics", "integrity"],
    queryFn: () => apiGet<IntegrityResponse>("/options/analytics/integrity"),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}

function useDailyCounts() {
  return useQuery<DailyCountsResponse>({
    queryKey: ["options", "analytics", "daily-counts", 1],
    queryFn: () => apiGet<DailyCountsResponse>(
      "/options/analytics/daily-counts?days=1"),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}


// ──────────────────────────────────────────────────────────────
// Pure helpers (no side effects)
// ──────────────────────────────────────────────────────────────

function _humanDate(iso: string): string {
  const d = new Date(iso + "T12:00:00Z");
  return d.toLocaleDateString(undefined, {
    weekday: "short", day: "numeric", month: "short", year: "numeric",
  });
}

function _humanDelta(secs: number): string {
  if (secs < 60) return `${Math.round(secs)} s ago`;
  if (secs < 3600) return `${Math.round(secs / 60)} m ago`;
  if (secs < 86400) {
    const h = Math.floor(secs / 3600);
    const m = Math.round((secs % 3600) / 60);
    return m === 0 ? `${h} h ago` : `${h} h ${m} m ago`;
  }
  const d = Math.floor(secs / 86400);
  return `${d} d ago`;
}

function _formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString();
}

/** Hero accent-bar tone: success when all 5 integrity flags pass;
 *  warning when 1-2 fail; danger when 3+ fail OR coherent_batch_present
 *  is false. (Matches the rule approved in design refinement 11.) */
function _heroTone(i: IntegrityResponse | undefined):
    "success" | "warning" | "danger" | "neutral" {
  if (!i) return "neutral";
  const flags = [
    i.coherent_batch_present,
    i.provider_homogeneous,
    i.universe_closure_pass,
    i.freshness_bound_pass,
    i.shadow_persistence_active,
  ];
  const failed = flags.filter(f => !f).length;
  if (!i.coherent_batch_present || failed >= 3) return "danger";
  if (failed >= 1) return "warning";
  return "success";
}

/** Build the calm sentence. Three-sentence template:
 *    1. observation status + counts
 *    2. integrity status (one phrase)
 *    3. paper-trade reality
 *  Adapts to dormant / out-of-bound / paper-active states honestly. */
function _calmSentence(args: {
  contracts: number | null;
  candidates: number | null;
  integrity: IntegrityResponse | undefined;
  paperTradeCount: number;
  shadowEvalEnabled: boolean;
}): string {
  const { contracts, candidates, integrity, paperTradeCount,
          shadowEvalEnabled } = args;

  // Sentence 1 — observation
  let s1: string;
  if (!shadowEvalEnabled) {
    s1 = "Engine is dormant; observation is paused.";
  } else if (contracts == null || contracts === 0) {
    s1 = "Engine is observing today's options chain; no contracts " +
         "evaluated yet.";
  } else {
    s1 = `Engine is observing today's options chain; ` +
         `${contracts.toLocaleString()} contracts evaluated, ` +
         `${(candidates ?? 0).toLocaleString()} candidates surfaced.`;
  }

  // Sentence 2 — integrity
  let s2: string;
  const tone = _heroTone(integrity);
  if (!integrity) {
    s2 = "";
  } else if (tone === "success") {
    s2 = "Dataset integrity within bounds.";
  } else if (tone === "warning") {
    const failed = [
      ["coherent batch",   integrity.coherent_batch_present],
      ["provider",         integrity.provider_homogeneous],
      ["universe",         integrity.universe_closure_pass],
      ["freshness",        integrity.freshness_bound_pass],
      ["shadow log",       integrity.shadow_persistence_active],
    ].filter(([, v]) => !v).map(([k]) => k);
    s2 = `Dataset showing ${failed.length} ` +
         `${failed.length === 1 ? "warning" : "warnings"} ` +
         `(${failed.join(", ")}).`;
  } else {
    s2 = "Dataset integrity below threshold; observation continues.";
  }

  // Sentence 3 — paper truth
  const s3 = paperTradeCount <= 1
    ? "No paper trades created."
    : `${paperTradeCount} paper trades observed.`;

  return [s1, s2, s3].filter(Boolean).join(" ");
}


// ──────────────────────────────────────────────────────────────
// Component
// ──────────────────────────────────────────────────────────────

export default function OptionsResearchPulseHero() {
  const { data: pipeline } = useOptionsPipelineStatus();
  const { data: integrity } = useIntegrity();
  const { data: daily }    = useDailyCounts();

  const today = daily?.series?.[0];
  const contracts = today?.total ?? null;
  const candidates = today?.would_trade ?? null;

  const tone = _heroTone(integrity);
  const eyebrow = `RESEARCH PULSE · ${
    integrity?.run_date ? _humanDate(integrity.run_date) : "today"}`;

  const sentence = _calmSentence({
    contracts,
    candidates,
    integrity,
    paperTradeCount: pipeline?.options_paper_trade_count ?? 0,
    shadowEvalEnabled: pipeline?.options_shadow_eval_enabled ?? false,
  });

  // Bottom metadata strip values
  const lastBatchAge = integrity?.active_batch
    ? _humanDelta(integrity.active_batch.age_seconds)
    : "—";
  const provider = integrity?.active_batch
    ? integrity.active_batch.provider
    : "—";

  return (
    <section
      className={`u-card-lg u-card-accent-l is-${tone}`}
      data-test="options-research-pulse-hero"
      data-tone={tone}
    >
      {/* Eyebrow */}
      <div className="u-label" style={{ marginBottom: 12 }}>
        {eyebrow}
      </div>

      {/* Calm sentence — the make-or-break headline */}
      <h1
        className="u-title-lg"
        style={{ marginBottom: 24, maxWidth: "62ch" }}
      >
        {sentence}
      </h1>

      {/* 65/35 split — contracts/candidates  |  integrity rail */}
      <div className="hero-split">
        {/* Left: counts */}
        <div className="hero-counts">
          <div className="hero-count-block">
            <div className="u-label-sm">CONTRACTS</div>
            <div className="hero-count-num hero-count-num-xl">
              {_formatNumber(contracts)}
            </div>
          </div>
          <div className="hero-count-block">
            <div className="u-label-sm">CANDIDATES</div>
            <div
              className="hero-count-num hero-count-num-lg"
              style={{ color: "var(--accent)" }}
            >
              {_formatNumber(candidates)}
            </div>
          </div>
        </div>

        {/* Right: integrity rail with 2-tier hierarchy */}
        <div className="hero-integrity">
          <div className="u-label-sm" style={{ marginBottom: 12 }}>
            DATASET
          </div>

          {/* PRIMARY tier — coherent batch + freshness */}
          <_IntegrityFlagPrimary
            ok={integrity?.coherent_batch_present ?? false}
            label="Coherent batch"
            value={integrity?.active_batch
              ? `${integrity.active_batch.provider} · ${
                  integrity.active_batch.provider_version
                    .replace("tradier-", "")}`
              : "no batch yet"}
          />
          <_IntegrityFlagPrimary
            ok={integrity?.freshness_bound_pass ?? false}
            label="Freshness"
            value={integrity?.active_batch
              ? `${integrity.active_batch.age_hours} h · within ` +
                `${integrity.thresholds.max_run_chain_age_hours} h bound`
              : "no batch"}
          />

          {/* SECONDARY tier — universe + shadow log (compact inline) */}
          <div className="hero-integrity-secondary">
            <_IntegrityFlagSecondary
              ok={integrity?.universe_closure_pass ?? false}
              text={`universe ${
                integrity?.universe_closure_pass ? "closed" : "drift"
              } (${integrity?.today_underlying_count ?? "—"}/${
                integrity?.thresholds?.run_universe?.length ?? 5})`}
            />
            <_IntegrityFlagSecondary
              ok={integrity?.shadow_persistence_active ?? false}
              text={
                integrity?.shadow_persistence_active
                  ? "shadow log live"
                  : "shadow log paused"
              }
            />
          </div>
        </div>
      </div>

      {/* Bottom metadata strip — single line */}
      <div className="hero-foot">
        <span>Last batch · {lastBatchAge}</span>
        <span className="hero-foot-sep">·</span>
        <span>Next fire · 21:30 UTC weekday</span>
        <span className="hero-foot-sep">·</span>
        <span>Provider · {provider}</span>
      </div>
    </section>
  );
}


// ──────────────────────────────────────────────────────────────
// Internal sub-components
// ──────────────────────────────────────────────────────────────

function _IntegrityFlagPrimary({
  ok, label, value,
}: { ok: boolean; label: string; value: string }) {
  return (
    <div
      className="hero-integrity-primary"
      data-ok={ok ? "true" : "false"}
    >
      <span
        className="hero-integrity-mark"
        aria-label={ok ? "ok" : "warn"}
      >
        {ok ? "✓" : "!"}
      </span>
      <span className="hero-integrity-label">{label}</span>
      <span className="hero-integrity-value">{value}</span>
    </div>
  );
}

function _IntegrityFlagSecondary({
  ok, text,
}: { ok: boolean; text: string }) {
  return (
    <span
      className="hero-integrity-secondary-item"
      data-ok={ok ? "true" : "false"}
    >
      <span className="hero-integrity-secondary-dot">·</span>
      {text}
    </span>
  );
}
