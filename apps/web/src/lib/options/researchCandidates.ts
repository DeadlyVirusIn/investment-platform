// Phase Opt-C1 Step 5+6+7 — Shared shadow-decision data hook.
//
// Wraps /api/options/shadow/runs (latest run summary) +
// /api/options/shadow/runs/{date} (per-decision detail).
//
// Discipline:
//   - Never represents stale data as "today's"
//   - Returns staleness signal so consumers can render honest empty states

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


export interface ShadowRunSummary {
  run_date: string;          // YYYY-MM-DD
  contracts_evaluated: number;
  would_trade_count: number;
  underlying_count: number;
}


export interface ShadowFilterResult {
  name: string;
  passed: boolean;
  observed?: Record<string, unknown>;
  threshold?: Record<string, unknown>;
}


export interface ShadowDecision {
  run_date: string;
  underlying_symbol: string;
  option_symbol: string;
  expiration: string;
  strike: string;
  option_type: "call" | "put" | string;
  side: "buy" | "sell" | string;
  strategy_name: string;
  would_trade: boolean;
  reason: string;
  score: string;
  filters: {
    liquidity: boolean;
    spread: boolean;
    open_interest: boolean;
    volume: boolean;
    greeks: boolean;
    iv_rank: boolean;
    risk: boolean;
  };
  diagnostics?: {
    filter_results?: ShadowFilterResult[];
  };
}


export interface ShadowRunDetail {
  run_date: string;
  decisions: ShadowDecision[];
}


export function useShadowRunsList() {
  return useQuery<{ runs: ShadowRunSummary[] }>({
    queryKey: ["options", "shadow", "runs"],
    queryFn: () =>
      apiGet<{ runs: ShadowRunSummary[] }>("/options/shadow/runs?limit=5"),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}


export function useShadowRunDetail(run_date: string | null) {
  return useQuery<ShadowRunDetail>({
    queryKey: ["options", "shadow", "runs", run_date],
    queryFn: () =>
      apiGet<ShadowRunDetail>(`/options/shadow/runs/${run_date}`),
    enabled: !!run_date,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}


/** Today's date in UTC ISO (YYYY-MM-DD). */
export function _todayIsoUTC(): string {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}


/** True when the run is from today (UTC). Used to gate
 *  "today's candidates" vs "last run was X days ago". */
export function isRunFromToday(run_date: string | null | undefined): boolean {
  if (!run_date) return false;
  return run_date === _todayIsoUTC();
}


/** Days between today (UTC) and a YYYY-MM-DD string. Negative for
 *  future dates (defensive — should never happen in practice). */
export function daysSince(run_date: string | null | undefined): number | null {
  if (!run_date) return null;
  const d = new Date(run_date + "T00:00:00Z").getTime();
  if (Number.isNaN(d)) return null;
  return Math.floor((Date.now() - d) / 86_400_000);
}


// ---------------------------------------------------------------------------
// Filter labels — novice-friendly translations
// ---------------------------------------------------------------------------

export const FILTER_LABELS: Record<string, string> = {
  liquidity:     "Quote liquidity",
  spread:        "Bid-ask spread",
  open_interest: "Open interest",
  volume:        "Volume",
  greeks:        "Greeks (delta/gamma)",
  iv_rank:       "Implied volatility rank",
  risk:          "Risk budget",
};

export const FILTER_FAIL_LABELS: Record<string, string> = {
  liquidity:     "Not enough trading activity",
  spread:        "Bid-ask spread too wide",
  open_interest: "Few existing positions on this contract",
  volume:        "Low volume today",
  greeks:        "Risk shape out of range (delta/gamma)",
  iv_rank:       "Implied volatility too elevated",
  risk:          "Risk would exceed budget",
};


/** Aggregate filter-fail counts from a list of decisions. Returns
 *  one entry per filter whose count > 0, sorted desc. */
export function aggregateRejectionReasons(
  decisions: ShadowDecision[],
): Array<{ name: string; label: string; failLabel: string; count: number }> {
  const counts: Record<string, number> = {};
  for (const d of decisions) {
    if (d.would_trade) continue;
    for (const [name, passed] of Object.entries(d.filters)) {
      if (!passed) {
        counts[name] = (counts[name] ?? 0) + 1;
      }
    }
  }
  return Object.entries(counts)
    .map(([name, count]) => ({
      name,
      label: FILTER_LABELS[name] ?? name,
      failLabel: FILTER_FAIL_LABELS[name] ?? name,
      count,
    }))
    .sort((a, b) => b.count - a.count);
}
